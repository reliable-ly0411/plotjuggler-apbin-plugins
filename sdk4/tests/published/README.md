# Published Windows packages against SDK 1.0.1

This supplementary harness builds only SDK host-side test executables. It never
builds, repacks or publishes an APBIN DLL. `scripts/verify_published_sdk4.py`
downloads the immutable 1.2.0-pj4.rc.1 and 1.3.0-pj4.rc.1 Windows ZIPs, verifies
their pinned byte counts and SHA-256 digests, checks source/ABI/license metadata,
and extracts the original libraries without modification.

The 1.2.0 test is the original test source from release commit
`0cc7cc10a25af3cb2ab122861b9be4fc01c99da5` (102 checks). The 1.3.0 test is from
compatibility candidate `90afd65ca21c452d1c1ab87e19d4057f9dfe60e8` (121 checks,
including TimeMS and simultaneous live-instance isolation). Both test source
files are downloaded by immutable commit and checked against pinned SHA-256.
Both executables use SDK `ffd749ab343c3211b5100f124f6c873667b82629` (1.0.1).
The original packages themselves were built against SDK 0.34.1.

The registered `sdk4.yml` manual entry offers `sdk101_packages=true`. Leave
`sdk101_compat=false`: the original-package test, source compatibility test and
release build are separate jobs. The package job runs Windows only; Linux
original-package tests can use the already-built SDK1.0.1 host executable.
No automatic trigger, release or product-pin update is added.

CTest names are `PublishedSDK101_1.2.0-pj4.rc.1` and
`PublishedSDK101_1.3.0-pj4.rc.1`. The evidence artifact contains the verified
package metadata/digests and the actual `LastTest.log`. Passing these tests is
an SDK loader/ABI and parser-data result, not full PlotJuggler GUI, marketplace
installation, every application build, or final-package release certification.
