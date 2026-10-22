"""Readback of an NDU saved by JRSNAP: is it the NDU we wrote? (CONTEXT.md NDUの受入記録)

JRSNAP reads an NDU record by record and writes every record again from what it read, so a saved copy that has the
same records, in the same order, with the same values shows the native reader took in what we wrote. A field is
the same when its text is identical or when both texts are the same decimal number (JRSNAP writes GanmaA 1.2 as
1.20); the second kind is reported as normalized. A blank (one space), an empty field and a bare key are text and
must be identical. Reading back is not an analysis.

This module only parses and compares; running JRSNAP is scripts/accept_jrsnap_ndu.py.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict

Record = tuple[str, tuple[str, ...] | None]  # None: a bare key line
ENCODING = "cp932"
# Declared counts and the numbered records they count.
COUNTS = {"JointNum": "JointXY", "MemberNum": "MemberInfo", "ElementNum": "ElementInfo", "LoadNum": "LoadTitle",
          "MLoadNum": "MLoadInfo", "JLoadNum": "JLoadInfo", "SNAPConbNum": "SNAPConb", "ConbNum": "ConbAlpf"}


class ReadbackError(ValueError):
    """The saved NDU is not the NDU that was written."""


@dataclass(frozen=True)
class Normalized:
    """A field JRSNAP wrote as the same number in another format."""

    key: str
    index: int
    written: str
    saved: str


class Summary(TypedDict):
    counts: dict[str, int]
    combinations: list[list[str]]  # the fields of each SNAPConb


@dataclass(frozen=True)
class Readback:
    records: int
    normalized: tuple[Normalized, ...]


def parse_records(data: bytes) -> tuple[Record, ...]:
    """The records of an NDU: CP932, every record ended by CRLF, no empty line."""
    try:
        text = data.decode(ENCODING)
    except UnicodeDecodeError as exc:
        raise ReadbackError(f"CP932 として読めません: {exc}") from exc
    if not text:
        raise ReadbackError("NDU が空です")
    if not text.endswith("\r\n"):
        raise ReadbackError("最後のレコードが CRLF で終わっていません")
    lines = text[:-2].split("\r\n")
    records: list[Record] = []
    for number, line in enumerate(lines, 1):
        if "\r" in line or "\n" in line:
            raise ReadbackError(f"{number}行目: 改行が CRLF ではありません")
        if not line:
            raise ReadbackError(f"{number}行目: 空の行があります")
        key, separator, body = line.partition("=")
        records.append((key, tuple(body.split(",")) if separator else None))
    return tuple(records)


def _number(text: str) -> Decimal | None:
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() and text.strip() == text else None


def compare_readback(written: bytes, saved: bytes) -> Readback:
    """Compare a saved NDU with the one written; raise ``ReadbackError`` at the first difference."""
    ours, theirs = parse_records(written), parse_records(saved)
    if len(ours) != len(theirs):
        raise ReadbackError(f"レコードの数が異なります（書いた {len(ours)}、保存 {len(theirs)}）")
    normalized: list[Normalized] = []
    for number, ((key, fields), (saved_key, saved_fields)) in enumerate(zip(ours, theirs), 1):
        if key != saved_key:
            raise ReadbackError(f"{number}行目: {key} の位置に {saved_key} があります")
        if fields is None or saved_fields is None:
            if fields != saved_fields:
                raise ReadbackError(f"{key}: 値のないキーと値のあるキーが異なります")
            continue
        if len(fields) != len(saved_fields):
            raise ReadbackError(f"{key}: 欄の数が異なります（書いた {len(fields)}、保存 {len(saved_fields)}）")
        for index, (field, saved_field) in enumerate(zip(fields, saved_fields)):
            if field == saved_field:
                continue
            value, saved_value = _number(field), _number(saved_field)
            if value is None or saved_value is None or value != saved_value:
                raise ReadbackError(f"{key} の {index + 1} 欄目が異なります（書いた {field!r}、保存 {saved_field!r}）")
            normalized.append(Normalized(key, index, field, saved_field))
    return Readback(records=len(ours), normalized=tuple(normalized))


def summarize(records: tuple[Record, ...]) -> Summary:
    """The declared counts, each checked against its numbered records, and the SNAPConb rows."""
    values = {key: fields for key, fields in records}
    counts: dict[str, int] = {}
    for key, prefix in COUNTS.items():
        fields = values.get(key)
        if not fields:
            raise ReadbackError(f"{key} がありません")
        declared = int(fields[0])
        present = sum(1 for name, _ in records if re.fullmatch(re.escape(prefix) + r"\d+", name))
        if present != declared:
            raise ReadbackError(f"{key} = {declared} に対して {prefix} が {present} 件あります")
        counts[key] = declared
    combinations = [list(values[f"SNAPConb{index}"] or ()) for index in range(1, counts["SNAPConbNum"] + 1)]
    return {"counts": counts, "combinations": combinations}


# The declared counts and the fields of DataInputTool.mdlGlobal that JRSNAP 5.2-L03 reads them into.
STATE_COUNTS = {"JointNum": "G_intJointNum", "MemberNum": "G_intMemberNum", "ElementNum": "G_intElementNum",
                "LoadNum": "G_intLoadNum", "MLoadNum": "G_intMLoadNum", "JLoadNum": "G_intJLoadNum",
                "SNAPConbNum": "G_intConbNum"}


def _same_number(field: str, value: float | int) -> bool:
    number = _number(field)
    return number is not None and number == Decimal(repr(value))


def compare_state(records: tuple[Record, ...], state: Mapping[str, Any]) -> None:
    """Compare what JRSNAP holds after reading (scripts/jrsnap_state_probe.cs) with the records we wrote.

    *state* is the probe's JSON: the read code, the counts, and each combination's ρm, αf, direction (0 正向,
    1 逆向), load cases and coefficients. SNAPConb is ρm, αf, the direction, a zero, a coefficient per load case (blank
    for the unused slots), two zeros.
    """
    if state["read_code"] != 0:
        raise ReadbackError(f"JRSNAP の読込みの戻り値 {state['read_code']}")
    summary = summarize(records)
    counts, held = summary["counts"], state["counts"]
    for key, name in STATE_COUNTS.items():
        if held[name] != counts[key]:
            raise ReadbackError(f"{key} = {counts[key]} に対して JRSNAP は {held[name]}（{name}）")
    combinations, written = state["combinations"], summary["combinations"]
    if len(combinations) != len(written):
        raise ReadbackError(f"組合せの数が異なります（書いた {len(written)}、JRSNAP {len(combinations)}）")
    cases = list(range(1, counts["LoadNum"] + 1))
    for number, (fields, combination) in enumerate(zip(written, combinations), 1):
        if not _same_number(fields[0], combination["rho_m"]):
            raise ReadbackError(f"組合せ {number} の ρm が異なります（書いた {fields[0]}、JRSNAP {combination['rho_m']}）")
        if not _same_number(fields[1], combination["alpha_f"]):
            raise ReadbackError(f"組合せ {number} の αf が異なります（書いた {fields[1]}、JRSNAP {combination['alpha_f']}）")
        if not _same_number(fields[2], combination["direction"]):
            raise ReadbackError(f"組合せ {number} の載荷の向きが異なります（書いた {fields[2]}、JRSNAP {combination['direction']}）")
        if combination["cases"] != cases:
            raise ReadbackError(f"組合せ {number} の荷重ケースが異なります（JRSNAP {combination['cases']}）")
        coefficients = fields[4:4 + len(cases)]
        held_coefficients = combination["coefficients"]
        if len(held_coefficients) != len(cases) or not all(
                _same_number(field, value) for field, value in zip(coefficients, held_coefficients)):
            raise ReadbackError(f"組合せ {number} の係数が異なります（書いた {coefficients}、JRSNAP {held_coefficients}）")
