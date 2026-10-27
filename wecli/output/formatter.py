# SPDX-License-Identifier: Apache-2.0
# Derived from wechat-cli: https://github.com/huohuoer/wechat-cli
# Modified and maintained for wecli by Staaaaaaaaar, 2026.
# Changes include project adaptation and/or source formatting; see docs/provenance.md.

"""Plain-text and explicit JSON output without terminal escape sequences."""

import json
import sys
import unicodedata


def output_json(data, file=None):
    file = file or sys.stdout
    json.dump(data, file, ensure_ascii=False, indent=2)
    file.write("\n")
    file.flush()


def output_text(text, file=None):
    file = file or sys.stdout
    file.write(text)
    if not text.endswith("\n"):
        file.write("\n")
    file.flush()


def readable(data, indent=0):
    """Render structured details as readable fields, never implicit JSON."""
    prefix = " " * indent
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            label = key.replace("_", " ").capitalize()
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{label}:\n{readable(value, indent + 2)}")
            else:
                lines.append(f"{prefix}{label}: {readable(value)}")
        return "\n".join(lines) or prefix + "None"
    if isinstance(data, list):
        return (
            "\n".join(prefix + "- " + readable(item, indent + 2).lstrip() for item in data)
            or prefix + "None"
        )
    if data is None:
        return prefix + "None"
    if isinstance(data, bool):
        return prefix + ("Yes" if data else "No")
    return prefix + str(data)


def output(data, fmt="text", file=None):
    if fmt == "json":
        output_json(data, file)
    elif fmt == "text":
        output_text(data if isinstance(data, str) else readable(data), file)
    else:
        raise ValueError(f"Unsupported output format: {fmt}")


def _cell(value):
    # Keep tables on one line and prevent stored data from injecting terminal controls.
    return " ".join(
        "".join(
            c if not unicodedata.category(c).startswith("C") else " " for c in str(value)
        ).split()
    )


def _width(value):
    return sum(
        0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        for c in value
    )


def _clip(value, width):
    if _width(value) <= width:
        return value
    text = ""
    for char in value:
        if _width(text + char) > width - 1:
            break
        text += char
    return text + "…"


def table(headers, rows, max_widths):
    """Render a compact table with Unicode-aware widths and bounded cells."""
    rows = [[_clip(_cell(value), limit) for value, limit in zip(row, max_widths)] for row in rows]
    widths = (
        [max(_width(header), *(_width(row[i]) for row in rows)) for i, header in enumerate(headers)]
        if rows
        else list(map(_width, headers))
    )

    def line(row):
        return "  ".join(
            value + " " * (width - _width(value)) for value, width in zip(row, widths)
        ).rstrip()

    return "\n".join([line(headers)] + [line(row) for row in rows])
