# SPDX-License-Identifier: LGPL-3.0-only
"""Reproduce the manufactured DataFlash test logs; no recorded flight data."""
from pathlib import Path
import struct

root = Path(__file__).resolve().parent
sizes = {"B": 1, "h": 2, "H": 2, "I": 4, "Q": 8, "f": 4, "d": 8, "N": 16, "Z": 64}


def fmt(message_id, name, schema, labels, length=None):
    length = length if length is not None else 3 + sum(sizes[code] for code in schema)
    return b"\xa3\x95\x80" + struct.pack("<BB4s16s64s", message_id, length,
                                            name.encode(), schema.encode(), labels.encode())


def record(message_id, schema, *values):
    return b"\xa3\x95" + bytes([message_id]) + struct.pack("<" + schema, *values)


log = (fmt(129, "FMTU", "QBNN", "TimeUS,FmtType,UnitIds,MultIds") +
       fmt(130, "UNIT", "QBZ", "TimeUS,Id,Label") +
       fmt(131, "MULT", "QBd", "TimeUS,Id,Mult") +
       fmt(140, "TST", "QBh", "TimeUS,I,Value"))
for key, label in (("s", "s"), ("v", "V")):
    log += record(130, "QB64s", 0, ord(key), label.encode())
for key, multiplier in (("F", 1e-6), ("-", 1), ("B", 0.01)):
    log += record(131, "QBd", 0, ord(key), multiplier)
log += record(129, "QB16s16s", 0, 140, b"s#v", b"F-B")
for timestamp, instance, value in ((1000000, 0, 123), (2000000, 1, 234), (3000000, 200, 345)):
    log += record(140, "QBh", timestamp, instance, value)
log += (fmt(141, "PARM", "QNf", "TimeUS,Name,Value") +
        record(141, "Q16sf", 1500000, b"TEST_PARAM", 7.5))
(root / "synthetic.BIN").write_bytes(log)

gps = log + fmt(142, "GPS", "QBIHB", "TimeUS,I,GMS,GWk,NSats")
gps += record(131, "QBd", 0, ord("C"), 0.001)
gps += record(129, "QB16s16s", 0, 142, b"s#s--", b"F-C--")
# The first sample has no resolved week and must not anchor the log to 1980.
gps += record(142, "QBIHB", 1000000, 0, 1000, 0, 8)
gps += record(142, "QBIHB", 2000000, 0, 345600000, 2000, 8)
(root / "gps.BIN").write_bytes(gps)
(root / "second.BIN").write_bytes(fmt(140, "TST", "Qf", "TimeUS,Value") +
                                  record(140, "Qf", 4000000, 2.5))
(root / "invalid.BIN").write_bytes(b"\xa3\x95\x80truncated")
(root / "invalid_fmt.BIN").write_bytes(fmt(140, "TST", "Qf", "TimeUS,Value", length=255))
(root / "invalid_fmtu.BIN").write_bytes(fmt(129, "FMTU", "QB", "TimeUS,FmtType") +
                                        record(129, "QB", 0, 140))
