# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

# Importing the local script must not dirty the checkout before its clean-tree guard.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_upstream", ROOT / "scripts/sync_upstream.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, name, text):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-m", name)
    return git(repo, "rev-parse", "HEAD")


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.fork = self.root / "fork"
        self.upstream.mkdir()
        git(self.upstream, "init", "--initial-branch=main")
        git(self.upstream, "config", "user.name", "Test")
        git(self.upstream, "config", "user.email", "test@example.invalid")
        self.baseline = commit(self.upstream, "product.cpp", "original\n")
        subprocess.run(["git", "clone", str(self.upstream), str(self.fork)], check=True, capture_output=True)
        git(self.fork, "config", "user.name", "Test")
        git(self.fork, "config", "user.email", "test@example.invalid")
        commit(self.fork, sync.RECORD, json.dumps({"last_upstream_commit": self.baseline}) + "\n")
        self.old_head = git(self.fork, "rev-parse", "HEAD")

    def run_sync(self, **kwargs):
        return sync.synchronize(self.fork, str(self.upstream), **kwargs)

    def test_noop_has_no_commit(self):
        self.assertIn("Already synchronized", self.run_sync())
        self.assertEqual(self.old_head, git(self.fork, "rev-parse", "HEAD"))

    def test_merge_keeps_both_histories_and_records_upstream(self):
        new = commit(self.upstream, "product.cpp", "upstream update\n")
        self.run_sync()
        self.assertTrue(sync.ancestor(self.fork, self.old_head, "HEAD"))
        self.assertTrue(sync.ancestor(self.fork, new, "HEAD"))
        self.assertEqual("upstream update\n", (self.fork / "product.cpp").read_text())
        self.assertEqual(new, json.loads((self.fork / sync.RECORD).read_text())["last_upstream_commit"])
        parents = git(self.fork, "rev-list", "--parents", "-1", "HEAD~1").split()
        self.assertEqual(3, len(parents))
        head = git(self.fork, "rev-parse", "HEAD")
        self.run_sync()
        self.assertEqual(head, git(self.fork, "rev-parse", "HEAD"))

    def test_product_divergence_stops_without_changes(self):
        head = commit(self.fork, "product.cpp", "fork product change\n")
        with self.assertRaisesRegex(RuntimeError, "product changes"):
            self.run_sync()
        self.assertEqual(head, git(self.fork, "rev-parse", "HEAD"))

    def test_dirty_worktree_stops(self):
        (self.fork / "product.cpp").write_text("uncommitted\n")
        with self.assertRaisesRegex(RuntimeError, "not clean"):
            self.run_sync()
        self.assertEqual(self.old_head, git(self.fork, "rev-parse", "HEAD"))

    def test_sdk_branch_is_never_synchronized(self):
        git(self.fork, "checkout", "-b", "plotjuggler-4.x-sdk")
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            self.run_sync()

    def test_rewritten_upstream_stops(self):
        git(self.upstream, "checkout", "--orphan", "replacement")
        commit(self.upstream, "product.cpp", "unrelated history\n")
        git(self.upstream, "branch", "-M", "main")
        with self.assertRaisesRegex(RuntimeError, "diverged"):
            self.run_sync()
        self.assertEqual(self.old_head, git(self.fork, "rev-parse", "HEAD"))

    def test_upstream_maintenance_collision_stops(self):
        commit(self.upstream, "FORK.md", "new upstream file\n")
        with self.assertRaisesRegex(RuntimeError, "maintenance paths"):
            self.run_sync()
        self.assertEqual(self.old_head, git(self.fork, "rev-parse", "HEAD"))

    def test_wrong_push_destination_stops(self):
        with self.assertRaisesRegex(RuntimeError, "intended user fork"):
            self.run_sync(push=True)
        self.assertEqual(self.old_head, git(self.fork, "rev-parse", "HEAD"))

    def test_checkout_https_origin_without_git_suffix_is_accepted(self):
        git(self.fork, "remote", "set-url", "origin", sync.FORK_URL.removesuffix(".git"))
        # The no-op path verifies the destination and fetches the local test
        # upstream, then returns before any push. No external repository call.
        self.assertIn("Already synchronized", self.run_sync(push=True))

    def test_normal_push_does_not_touch_sdk_branch(self):
        remote = self.root / "remote.git"
        subprocess.run(["git", "clone", "--bare", str(self.fork), str(remote)], check=True, capture_output=True)
        git(self.fork, "remote", "set-url", "origin", str(remote))
        git(remote, "branch", "plotjuggler-4.x-sdk", self.old_head)
        new = commit(self.upstream, "product.cpp", "upstream update\n")
        self.run_sync(push=True, expected_origin=str(remote))
        self.assertEqual(git(self.fork, "rev-parse", "HEAD"), git(remote, "rev-parse", "main"))
        self.assertEqual(self.old_head, git(remote, "rev-parse", "plotjuggler-4.x-sdk"))
        self.assertTrue(sync.ancestor(self.fork, new, "HEAD"))


if __name__ == "__main__":
    unittest.main()
