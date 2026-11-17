# SDK 1.0.1 compatibility candidate

This is a source compatibility candidate based on APBIN
`fc6065fd64305479946552a757d78e6afdd2c506`, not a new plugin release.
The application dependency pins, `VERSION`, `release.json`, existing tags and
release workflows are unchanged. APBIN issues #16–19 are outside this change.

## Locked sources

- SDK 1.0.1: `ffd749ab343c3211b5100f124f6c873667b82629`.
  On 2026-11-17 this is both the upstream `main` HEAD and fork `main` HEAD.
  Upstream annotated tag `v1.0.1` is
  `b0e73ef290b1ab590041cde047b7ceadda4360c4`; its peeled commit is the SHA above.
  The source `VERSION` reads `1.0.1`. The tag name alone was not used as evidence.
- SDK comparison baseline: `4d59e7de81455afe73a77051075e8fb4b9f6b0fd`
  (`VERSION` 0.34.1).
- SDK 1.0.0: `f9390f7a5d94c377247e38680a6dbd52b43319f2`.
  The 1.0.1 diff changes only VERSION, changelog and SDK test sources (#245);
  headers and runtime libraries are unchanged. Unicode loader diagnostics
  fix #226 is already an ancestor of 1.0.0 and 1.0.1.
- Public BIN: `tests/logs/00000001.BIN`, retained from the existing upstream
  APBIN source, SHA-256
  `28dcbac522ceb75eee10f6af37b0d6e342c1dc79e2be1a9f766fe18a14336766`.
- Build dependencies: nlohmann_json 3.12.0, fmt 12.1.0, fast_float 8.1.0,
  resolved from the exact SDK recipe. Existing license texts and notices remain.

## Minimal changes

`APBIN_SDK_SOURCE_DIR` accepts an explicitly checked-out SDK 1.0.1 in addition
to 0.34.1. The installed-package default remains EXACT 0.34.1. No parser or
source implementation changes were needed. The exported boot ABI remains 5
and data-source protocol remains 4.

The manifest retains `min_sdk_required: 0.34.1`. Its redundant
`suggested_sdk_version: 0.34.1` was removed: SDK 1.0.1 requires a degraded-host
`floor_test` for that optional field, which is unnecessary when the suggested
and minimum versions are identical. The 1.0.1 feature-floor checker passes
and recognizes `setDatasetMetadata`. The release validator accepts the absent
optional field without relaxing the minimum version, license or release gates.

The ABI regression adds two simultaneously live source instances with different
configs and hosts. It verifies isolation of config, writes and progress cleanup.
This is not a concurrent-thread test.

The manual-only `sdk101-compat.yml` locks the exact SDK commit and runs native
Linux/Windows ABI tests, plus Linux ASan/UBSan instrumentation of the parser,
plugin and SDK. It uploads test logs only. It cannot publish or promote packages.
The existing release job and final-ZIP validation gates remain intact.
A source-build version stamp prevents the 0.34.1 release packager from labeling
an explicitly selected 1.0.1 compatibility build as an old-SDK package.

## Reproduction

With SDK checked out at the exact SHA above:

```sh
conan profile detect --force
conan install /path/to/sdk -of build/deps -s build_type=Release \
  -s compiler.cppstd=20 -c tools.cmake.cmaketoolchain:generator=Ninja \
  -o with_tests=False --build=missing
cmake -S sdk4 -B build/compat -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DAPBIN_BUILD_PLUGIN=ON -DAPBIN_SDK_SOURCE_DIR=/path/to/sdk \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/build/deps/conan_toolchain.cmake" \
  -DPJ_WARNINGS_AS_ERRORS=ON -DPJ_BUILD_EXPERIMENTAL=OFF
cmake --build build/compat --target ardupilot_parser_test ardupilot_source_test --parallel 2
ctest --test-dir build/compat --output-on-failure -V
python /path/to/sdk/tools/feature_floors/feature_floor_check.py \
  --table /path/to/sdk/pj_base/feature_floors.json \
  --manifest sdk4/manifest.json --sources sdk4/src
```

The compatibility workflow contains the full sanitizer configure command.

## Executed results

Cloud Debian 13 x86_64, GCC 14.2, CMake 4.4.5, Ninja 1.13.2:

| Check | Result |
| --- | --- |
| Dependency-free parser Debug | PASS: 2,147 checks |
| Parser Debug ASan + UBSan | PASS |
| SDK 1.0.1 Release, SDK warnings fatal | PASS: parser + actual DSO host tests, 2/2 CTest |
| SDK 1.0.1 parser + DSO + SDK ASan/UBSan | PASS: 2/2 CTest; leak detection and halt-on-error enabled |
| Dynamic SDK ABI | PASS: 121 checks, exported ABI 5; ELF allowlist: no GNU unique symbols |
| Public BIN across real DSO | PASS: 1,940 series, 444,443 samples; known truncated tail retained |
| TimeUS, TimeMS, GPS | PASS: exact integer/nanosecond conversions, mixed-clock precedence, exclusions and overflow rejection |
| Instances, cancellation and errors | PASS: live-instance isolation, Stop/Keep prefixes, pre-cancel, malformed/missing input and config, host write/metadata failures, Unicode input path |
| SDK 0.34.1 local rebuild | PASS: 2/2 CTest; documented GCC14 warning workaround `PJ_WARNINGS_AS_ERRORS=OFF` used for SDK baseline only |
| 0.34.1 host loads 1.0.1-built plugin | PASS: 121 ABI checks |
| 1.0.1 host loads 0.34.1-built plugin | PASS: 121 ABI checks |
| SDK 1.0.1 feature-floor check | PASS after removing redundant suggested version |
| Release/sync/policy regressions | PASS: 10 + 16 + 39 tests |

The initial manifest check failed because `suggested_sdk_version` lacked
`floor_test`; that candidate defect is corrected. The initial tool setup needed
a writable virtualenv and Ninja on PATH; both were corrected. No source change
was made to work around a runtime test failure.

## Integration boundary

Before changing the application pin, use this candidate's source commit and the
exact SDK commit above; run the application's targeted loader integration and
Windows native checks. This report does not claim whole-application/GUI testing,
Windows/macOS/ARM/WebAssembly execution, a broad real-flight corpus, simultaneous
multithreaded imports, or SDK-wide sanitizer coverage. The test-only workflow
has not been executed on GitHub Actions during this audit. No 1.0.1 release ZIP
was created or validated; current release packaging still targets 0.34.1.
A new release requires its own version/package mapping and the existing complete
native and final-archive gates. Do not use this compatibility result to publish
another artifact under the existing release tag.
