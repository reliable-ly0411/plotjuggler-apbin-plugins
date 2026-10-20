#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-only
"""Compile upstream XML descriptions into a Qt-free, deterministic lookup table."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def generate(source: Path, target: Path) -> None:
    """Merge in filename order, matching the original loader's last-document wins rule."""
    descriptions: dict[tuple[str, str], str] = {}
    for path in sorted(source.glob("*.xml")):
        root = ET.parse(path).getroot()
        for message in root.findall("logformat"):
            name = message.attrib["name"]
            descriptions[name, ""] = (message.findtext("description") or "").strip()
            for field in message.findall("fields/field"):
                descriptions[name, field.attrib["name"]] = (field.findtext("description") or "").strip()
    rows = []
    for (message, field), description in sorted(descriptions.items()):
        if description:
            rows.append("  {" + ", ".join(json.dumps(value, ensure_ascii=True)
                                          for value in (message, field, description)) + "},")
    text = ("// SPDX-License-Identifier: LGPL-3.0-only\n"
            "// Generated from upstream DataLoadAPBin/LogMessageDescriptions/*.xml.\n"
            "#pragma once\n#include <array>\n#include <string_view>\n"
            "struct LogDescription { std::string_view message, field, text; };\n"
            f"inline constexpr std::array<LogDescription, {len(rows)}> kLogDescriptions = {{{{\n"
            + "\n".join(rows) + "\n}};\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
