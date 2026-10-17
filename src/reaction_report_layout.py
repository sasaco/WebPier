"""The bundled 0600 worksheet data and its Excel-compatible number formats.

The template keeps static captions, source cell IDs, formulas and number
formats as pure data for the display evaluation. Formula caches are absent,
and no paper coordinates or rules are used for rendering.
"""

from __future__ import annotations

from functools import lru_cache
from fractions import Fraction
import json
from pathlib import Path
import re
from typing import Any

from .reaction_math import excel_round


@lru_cache(maxsize=1)
def load_layout() -> dict:
    return json.loads((Path(__file__).parent / "assets/reaction_report_layout.json").read_text(encoding="utf-8"))


def format_value(value: Any, number_format: str) -> str:
    """Format the numeric patterns used by the original engineering workbook."""
    if value is None:
        return ""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        if "@" in number_format:
            before, after = number_format.split("@", 1)
            return before.replace('"', '') + str(value) + after.replace('"', '')
        return str(value)
    sections = number_format.split(";")
    pattern = sections[1] if value < 0 and len(sections) > 1 else sections[2] if value == 0 and len(sections) > 2 else sections[0]
    pattern = re.sub(r"\[[^]]*\]", "", pattern)
    if pattern.lower() == "general":
        return f"{value:g}"
    if "/" in pattern and "?" in pattern:
        fixed = re.search(r"/([1-9][0-9]*)", pattern)
        fraction = Fraction(value).limit_denominator(int(fixed[1]) if fixed else 100)
        if fraction.denominator == 1:
            return str(fraction.numerator)
        whole = int(value)
        remainder = fraction - whole
        return (f"{whole} " if whole else "") + f"{abs(remainder.numerator) if whole else remainder.numerator}/{remainder.denominator}"
    if not re.search(r"[0#?]", pattern):
        return pattern.replace('"', '').replace("\\", "")
    # Bracketed grouping such as #,##0 is rendered with the source's comma.
    decimal = re.search(r"\.([0#?]+)", pattern)
    decimals = len(decimal.group(1)) if decimal else 0
    number = value * 100 if "%" in pattern else value
    number = excel_round(number, decimals)
    space_grouping = "#\\ ##0" in pattern
    text = f"{number:,.{decimals}f}" if "," in pattern or space_grouping else f"{number:.{decimals}f}"
    if space_grouping:
        text = text.replace(",", " ")
    if decimal and "#" in decimal.group(1):
        text = text.rstrip("0").rstrip(".")
    if "%" in pattern:
        text += "%"
    literals = re.findall(r'"([^"]*)"', pattern)
    if literals:
        text += "".join(literals)
    return text
