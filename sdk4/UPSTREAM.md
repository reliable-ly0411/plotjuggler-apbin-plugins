# ArduPilot DataFlash SDK4 port provenance

This directory is a separately built **LGPL-3.0-or-later** plugin. It is not
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
