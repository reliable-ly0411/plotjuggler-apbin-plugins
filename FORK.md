# Fork branches and upstream synchronization

This is a fork of [ArduPilot/plotjuggler-apbin-plugins](https://github.com/ArduPilot/plotjuggler-apbin-plugins).
The original LGPL-3.0 licensing and Git history are preserved.

- `main` follows the original upstream main branch. Product source is kept
  identical to the recorded upstream commit. Five documented maintenance files
  provide this policy, the synchronization workflow/script/test, and its baseline
  record. Consequently, `main` is not an exact-SHA mirror.
- `plotjuggler-4.x-sdk` carries the independent SDK4 port under `sdk4/`. Its
  ancestry starts at the real upstream main commit, retaining the original
  Qt5 plugin sources for comparison. It is not a published plugin release.
- Incorporate future main changes into the SDK4 branch through reviewed,
  non-squashed merge commits/PRs and rerun the parser/SDK regression suites.
  The automatic job never updates the adaptation branch.

The upstream baseline is recorded in [docs/upstream-sync.json](docs/upstream-sync.json).
The default-branch workflow checks upstream daily at 04:17 UTC and on demand.
It uses only the repository's short-lived `GITHUB_TOKEN`, with repository-content
write permission to push an ordinary merge; no personal access token is needed.
A fork's Actions workflows must be enabled for schedules to run. GitHub may delay
scheduled jobs or disable public-repository schedules after prolonged inactivity;
the Actions run history is the evidence that synchronization has actually run.

Before every merge, the script requires a clean main branch, the recorded
upstream ancestry, and a product tree identical to that baseline. It refuses
rewritten/diverged upstream history, unexpected product edits, and upstream
changes to the reserved maintenance paths. Merge conflicts stop the run.
A concurrent push is rejected by Git's normal fast-forward protection. Nothing
force-pushes, deletes branches, creates releases, or changes historical tags.

To inspect locally, run `python3 tests/test_sync_upstream.py -v`, then
`python3 scripts/sync_upstream.py` on a clean main checkout. The latter makes
local merge/bookkeeping commits only. Add `--push` to publish the verified main
merge. Review failed runs rather than weakening these checks.
