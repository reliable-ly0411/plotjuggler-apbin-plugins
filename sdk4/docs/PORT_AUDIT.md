# SDK4 port audit

Reference: `plotjuggler_plugins/DataLoadAPBin/dataload_apbin.cpp` at
PlotJuggler-zh-CN `766a88d8e689c7803f32acb315ac872a0a67a57b` (original upstream
`3e2f9253adc2d41e17b2f0fec74f4b2487c42fb0`). Line ranges below refer to the 3.x
integration reference; original upstream differs slightly.

| Original feature | Original location | SDK4 status and location |
| --- | --- | --- |
| `.bin` file discovery | Constructor / `compatibleFileExtensions`, lines 59–70 | `manifest.json`, embedded and validated by SDK helper |
| Fresh state for every input | `readDataFromFile`, lines 73–105 | `parse()` owns all state locally; new source instances are ABI-tested |
| FMT schemas, header resynchronization | Main loop, lines 132–258 | `readFormat` and `parse`; bounded schema validation |
| FMTU, instance `#` grouping | Main loop, lines 280–326 | Deferred metadata application also handles late FMTU |
| UNIT/MULT values and units in curve paths | Lines 329–386, `get_unit`, `apply_multipliers` | `parse`, `displayUnit`; multiplier scaling occurs once |
| TimeUS timestamps | Lines 522–526 | Integer microseconds; `ArduPilotSource` uses SDK checked nanosecond conversion |
| GPS week/time anchoring | `gps_to_unix_time`, `apply_timesync` | Same first-instance valid-fix policy and 18-second offset; GMS scaled afterward |
| All numeric wire codes | `handle_message_received`, lines 881–984 | `numericValue`, little-endian and alignment-safe |
| Skip ISBD/ISBH, arrays and ordinary string fields | Lines 396–409, 659–663 | Same omission in `parse`; explicit in README |
| Legacy and current MSG | Lines 410–436 | Field-name-driven `MSG` decode, timeline and message-log paths |
| Legacy PARM and Default labels | Lines 438–466; 802–808 | Field-name-driven `PARM` decode, default-value formatting |
| Message text slash escaping | Lines 819–838 | `parse` replaces every slash before curve naming |
| Descriptions from Copter/Plane XML | `load_log_messages`, lines 1099–1167 | Original XML preserved; deterministic generator; dataset metadata includes descriptions |
| Scalar per-field hover tooltips | Lines 700–730 | **SDK GAP:** SDK0.34.1 has no scalar field-tooltip setter. Requires a generic SDK/host extension for complete hover parity; metadata exposure is not claimed as hover parity |
| Optional servo function labels | `LABEL_RCOU_FUNCTION`, lines 468–488 and 680–696 | Disabled by source 3.x integration build; remains disabled |
| Qt5 plugin lifecycle | `DataLoadAPBIN`/`Q_PLUGIN_METADATA` | Replaced with SDK `FileSourceBase`, C ABI, isolated shared library; no binary compatibility claim |
| Loading diagnostics and stop | Loading counters / debug output | SDK report/progress, parse-before-publish errors, Keep/Discard-compatible stopping |

## Deliberate hardening

- Duplicate field labels, invalid required metadata field types, conflicting
  same-ID schema redefinitions and malformed FMTU lengths are rejected rather
  than allowing stale offsets or out-of-bounds reads.
- Native pointer casts are replaced with little-endian, bounded reads. Integer
  instances retain their full width, including 8-bit values above 127.
- Timestamps retain microsecond precision through GPS alignment. Both parser
  and host SDK range checks precede publication.
- Truncated tails and skipped bytes are surfaced as incomplete data, while a
  file containing no usable samples is rejected.
- Unit denominators are rendered with bounded superscript conversion, including
  repeated denominators such as `m/s/s`, without indexing a fixed-size exponent
  table beyond its end.

## Verification scope

`ardupilot_parser_test` is a dependency-free regression runner covering the six
original synthetic fixtures plus malformed fields, truncation, repeated loads,
numeric decoding, late metadata, current/legacy messages and cancellation.
Every byte-truncation boundary of the synthetic log and 1,000 deterministic
mutated logs are exercised. The public upstream `00000001.BIN` fixture is
checked for 1,940 series, 444,443 numeric samples and its known 51-byte truncated
tail; it also verifies the real signed-byte UNIT/MULT identifiers.
`ardupilot_source_test` loads the actual DSO through SDK0.34.1, binds C ABI host
services, verifies numeric/time values, metadata, failed writes, malformed
config/input, Stop, Unicode paths and the same complete upstream log. Passing
these tests does not constitute complete PlotJuggler GUI, broad real-flight
corpus or Windows runtime validation.
