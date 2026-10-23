"""The 基礎照査連携用データ (.sdr) SOIL-JR returns: the design limits of the pile foundation, read as tables.

The file is CP932 text of a header (the version, the title and the pile in one line of names and one of values) and, for
each direction (``(1)橋軸方向``) and each condition (``地震時以外``, ``地震時``), tables: a ``【title】`` line, a line of column names and
rows up to a blank line; a table of the 地震時 has a line of group names above its column names (杭先端支持力,,,杭周面支持力,,,鉛直支持力), which is kept
as ``groups``. They are read as they are, by their names, without choosing among them: the stages that use the
limits (0612, 0622, the Aggre-SE check) take the table and the column they need (references/sdr-format.md of the skill
structural-jrsnap-soil). A cell is a number when it reads as one, else its text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ENCODING = "cp932"
_DIRECTION = re.compile(r"^\((\d+)\)(.+)$")


class SdrError(ValueError):
    """The file is not a .sdr of SOIL-JR 5.2."""


@dataclass(frozen=True)
class SdrTable:
    direction: str | None  # 橋軸方向, 直角方向; None before the first
    condition: str | None  # 地震時以外, 地震時 …; None before the first
    title: str  # the title of the table, without 【】
    columns: tuple[str, ...]
    groups: tuple[tuple[str, ...], ...]  # the lines of group names above the column names
    rows: tuple[tuple[float | str, ...], ...]


@dataclass(frozen=True)
class SdrFile:
    version: str  # Ver.5.2.3
    title: str
    pile: dict[str, float | str]  # the header's names and values (フーチング有無, 杭種, 杭長, …)
    tables: tuple[SdrTable, ...]

    def table(self, direction: str, condition: str, title: str) -> SdrTable:
        """The table *title* of the *condition* in the *direction*."""
        for table in self.tables:
            if (table.direction, table.condition, table.title) == (direction, condition, title):
                return table
        raise SdrError(f"{direction}・{condition} に【{title}】がありません")


def _cell(text: str) -> float | str:
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        return text


def _cells(line: str) -> tuple[float | str, ...]:
    return tuple(_cell(part) for part in line.split(","))


def parse_sdr(data: bytes) -> SdrFile:
    try:
        lines = data.decode(ENCODING).replace("\r\n", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise SdrError(f".sdr を CP932 として読めません（{exc}）") from exc
    if len(lines) < 5 or not lines[0].startswith("Ver.5.2"):
        raise SdrError("SOIL-JR 5.2 の .sdr ではありません（先頭が Ver.5.2 ではありません）")
    names, values = lines[2].split(","), _cells(lines[3])
    if len(names) != len(values):
        raise SdrError("杭の見出しの項目数と値の数が違います")
    tables: list[SdrTable] = []
    direction = condition = None
    index = 4
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if line.startswith("【"):
            if index >= len(lines) or not line.endswith("】"):
                raise SdrError(f"表の見出しが不正です: {line}")
            block = []
            while index < len(lines) and lines[index].strip():
                block.append(tuple(part.strip() for part in lines[index].split(",")))
                index += 1
            if not block:
                raise SdrError(f"【{line[1:-1]}】に見出しがありません")
            # the rows have as many cells as the column names, the last line's count; the lines above them with fewer
            # cells name groups of columns
            start = next(position for position, cells in enumerate(block) if len(cells) == len(block[-1]))
            if any(len(cells) != len(block[start]) for cells in block[start:]):
                raise SdrError(f"【{line[1:-1]}】の列の数が見出しと違います")
            tables.append(SdrTable(direction, condition, line[1:-1], block[start], tuple(block[:start]),
                                   tuple(tuple(_cell(cell) for cell in cells) for cells in block[start + 1:])))
        elif match := _DIRECTION.match(line):
            direction, condition = match.group(2), None
        else:
            condition = line
    if not tables:
        raise SdrError(".sdr に表がありません")
    return SdrFile(version=lines[0].strip(), title=lines[1], pile={name.strip(): value for name, value in zip(names, values)},
                   tables=tuple(tables))
