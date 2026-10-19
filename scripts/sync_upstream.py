#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Merge upstream main without rewriting history or importing SDK4 changes."""
import argparse
import json
from pathlib import Path
import re
import subprocess

UPSTREAM = "https://github.com/ArduPilot/plotjuggler-apbin-plugins.git"
FORK_URL = "https://github.com/reliable-ly0411/plotjuggler-apbin-plugins.git"
RECORD = "docs/upstream-sync.json"
MANAGED = frozenset({RECORD, "FORK.md", "scripts/sync_upstream.py",
                     "tests/test_sync_upstream.py", ".github/workflows/upstream-sync.yml"})


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check,
                          capture_output=True, text=True)


def sha(repo, ref):
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()


def ancestor(repo, older, newer):
    result = git(repo, "merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip())
    return result.returncode == 0


def changed(repo, old, new):
    return set(git(repo, "diff", "--name-only", "-z", old, new).stdout.rstrip("\0").split("\0")) - {""}


def synchronize(repo, upstream_url=UPSTREAM, push=False, expected_origin=FORK_URL):
    repo = Path(repo).resolve()
    if git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() != "main":
        raise RuntimeError("Synchronization is restricted to the upstream-following main branch")
    if git(repo, "status", "--porcelain").stdout:
        raise RuntimeError("Worktree is not clean; no synchronization was attempted")
    if push:
        origin = git(repo, "remote", "get-url", "origin").stdout.strip()
        acceptable = {expected_origin}
        if expected_origin == FORK_URL:
            acceptable.add("git@github.com:reliable-ly0411/plotjuggler-apbin-plugins.git")
        if origin not in acceptable:
            raise RuntimeError("origin is not the intended user fork; refusing to push")
    record_file = repo / RECORD
    record = json.loads(record_file.read_text(encoding="utf-8"))
    baseline = record["last_upstream_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise RuntimeError("Invalid recorded upstream commit")
    old_head = sha(repo, "HEAD")
    if not ancestor(repo, baseline, old_head):
        raise RuntimeError("Recorded upstream commit is not an ancestor of main")
    unexpected = changed(repo, baseline, old_head) - MANAGED
    if unexpected:
        raise RuntimeError("main contains product changes; review before synchronization: " + ", ".join(sorted(unexpected)))
    git(repo, "fetch", "--no-tags", upstream_url, "refs/heads/main")
    upstream_head = sha(repo, "FETCH_HEAD")
    if not ancestor(repo, baseline, upstream_head):
        raise RuntimeError("Upstream history diverged from the recorded baseline; refusing to rewrite it")
    if upstream_head == baseline:
        return "Already synchronized at " + baseline
    collisions = changed(repo, baseline, upstream_head) & MANAGED
    if collisions:
        raise RuntimeError("Upstream now changes fork-maintenance paths; manual review required: " + ", ".join(sorted(collisions)))
    result = git(repo, "merge", "--no-ff", "--no-edit", upstream_head, check=False)
    if result.returncode:
        git(repo, "merge", "--abort", check=False)
        raise RuntimeError("Upstream merge failed; main was not pushed: " + result.stderr.strip())
    record["last_upstream_commit"] = upstream_head
    record_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    git(repo, "add", "--", RECORD)
    git(repo, "commit", "-m", "chore(sync): record upstream " + upstream_head[:12])
    if changed(repo, upstream_head, "HEAD") - MANAGED:
        raise RuntimeError("Post-merge product tree differs from upstream; refusing to push")
    if not ancestor(repo, old_head, "HEAD"):
        raise RuntimeError("Synchronization did not preserve the previous main head")
    if push:
        # A normal non-forced push rejects concurrent main updates. There is no
        # fallback to force/force-with-lease and no push to the SDK4 branch.
        git(repo, "push", "origin", "HEAD:refs/heads/main")
    return "Merged upstream " + upstream_head + (" and pushed main" if push else " locally (not pushed)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--push", action="store_true", help="Push the verified merge to origin/main without force")
    args = parser.parse_args()
    try:
        print(synchronize(args.repo, push=args.push))
    except (RuntimeError, subprocess.CalledProcessError, KeyError, ValueError) as exc:
        parser.exit(1, f"Synchronization stopped: {exc}\n")


if __name__ == "__main__":
    main()
