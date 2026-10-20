# ArduPilot DataFlash SDK4 port provenance

This directory is a separately built **LGPL-3.0-only** plugin. It is not
linked into PlotJuggler's MPL-2.0 application binary.

- Original repository: <https://github.com/ArduPilot/plotjuggler-apbin-plugins>
- Original default branch: `main`
- Original source checkpoint: `3e2f9253adc2d41e17b2f0fec74f4b2487c42fb0`
  (`Update parser to decode new MSG format`)
- Local 3.x integration reference:
  <https://github.com/reliable-ly0411/PlotJuggler-zh-CN/tree/766a88d8e689c7803f32acb315ac872a0a67a57b/plotjuggler_plugins/DataLoadAPBin>
- `tests/*.BIN` and `tests/generate_fixtures.py` are manufactured regressions
  copied from that exact integration checkpoint. They contain no recorded
  flight or personal data.
- The original repository's existing `tests/logs/00000001.BIN` is also tested
  in place, without copying or altering it. Its SHA-256 is
  `28dcbac522ceb75eee10f6af37b0d6e342c1dc79e2be1a9f766fe18a14336766`.
- The description XML remains in its original
  `DataLoadAPBin/LogMessageDescriptions/` directory, unchanged at this port's
  starting checkpoint. The build compiles it into a deterministic lookup table.
- SDK source used for build and ABI verification:
  <https://github.com/PlotJuggler/plotjuggler_sdk/tree/4d59e7de81455afe73a77051075e8fb4b9f6b0fd>
  (tag `v0.34.1`). SDK code is Apache-2.0; its license is in `LICENSE.APACHE2`.

The original parser authors are Pierre Kancir and Jonas Withelm (IAV GmbH).
The original source also credits Dronekit-La for parsing logic and ArduPilot's
`AP_Logger/LogStructure.h` for the DataFlash wire layout/type definitions.
Those credits and the original LGPL license remain applicable to the port.

### License-version evidence

The upstream change to LGPL is commit
[`ec4524b49f0cb837ebacd348781b5d9657e86ba3`](https://github.com/ArduPilot/plotjuggler-apbin-plugins/commit/ec4524b49f0cb837ebacd348781b5d9657e86ba3).
It installed the LGPL version 3 text; `package.xml` explicitly says `LGPLv3`.
No project-specific permission to choose later versions was found at the pinned
upstream checkpoint. The manifest and derived-file SPDX identifiers therefore
record `LGPL-3.0-only`. Earlier port metadata incorrectly said `or-later`;
correcting it is not a new license grant or a relicensing of upstream authors'
work. The original LGPLv3 and incorporated GPLv3 texts remain unmodified.

The Qt5 plugin and PJ3 C++ ABI are **not** reused. `DataFlashParser` translates
the original record handling into a Qt-free parsing core; `ArduPilotSource`
implements SDK 0.34.1 `FileSourceBase`, built as a replaceable shared library.
The host boundary is the SDK C ABI (boot ABI 5, data-source protocol 4).

The 3.x integration's safety fixes are preserved: bounded FMT/FMTU parsing,
fresh per-file state, legacy parameter records, valid-week GPS anchoring and
GPS GMS scaling after synchronization. Additional hardening rejects duplicate
labels, incompatible schema redefinition, invalid required field types,
non-finite multipliers and unrepresentable timestamps. Multi-byte fields are
decoded without unaligned pointer casts. Timestamp arithmetic remains integral
until the SDK nanosecond boundary. See `docs/PORT_AUDIT.md` for behavior and gaps.

When distributing binaries, retain `LICENSE` (LGPL3), `COPYING.GPL3`,
`LICENSE.APACHE2`, this provenance file, and provide the corresponding source
for the exact plugin revision. Keep the plugin replaceable and do not restrict
debugging/reverse engineering of modifications. Static embedding is refused by
this CMake integration. This file describes the chosen delivery architecture;
it is not a legal opinion about unrelated distributions.

## SDK implementation dependencies

The separately built SDK/plugin uses `fmt` 12.1.0, `nlohmann_json` 3.12.0 and
`fast_float` 8.1.0. Their copyright/permission notices are retained in
`licenses/` (MIT for JSON and fast_float; the original fmt license including
its optional compiled-object exception). The directory also retains the
SDK 0.34.1 per-module copyright/license mapping. It is installed and included
in each binary ZIP; the full Apache-2.0 text remains `LICENSE.APACHE2`.

Sources: <https://github.com/fmtlib/fmt/tree/12.1.0>,
<https://github.com/nlohmann/json/tree/v3.12.0>,
<https://github.com/fastfloat/fast_float/tree/v8.1.0>. These versions match the
pinned SDK's Conan requirements.
