"""0612 / 0622 基礎の照査 of a pile foundation: the design limits SOIL-JR returned (decision 89, ADR-0013).

The 基礎照査連携用データ (.sdr) of 0500 holds the design limits of each 性能項目 in a table per direction. They are read
as they are printed: the 設計鉛直支持力 of 長期支持性能, 短期支持性能 and 安定(地震時以外) (the base values Rk, pt and fr that make it
too), the 設計引き抜き抵抗力 and the limits of the horizontal displacement and of the rotation (``calc.pile_check``
checks the responses of the frame against them).
"""

from __future__ import annotations

from collections.abc import Mapping

from ..calc.foundation_check import Requirement
from ..calc.pile_check import REQUIREMENTS, SDR_DIRECTION, Direction, Limits
from ..core.printed import Precision, Printed
from ..export.soiljr import SdrError, SdrFile, SdrTable

CONDITION = "地震時以外"
_FORCE, _FRACTION = Precision(1, "kN"), Precision(3, "")
_DISPLACEMENT, _ROTATION = Precision(3, "mm"), Precision(5, "rad")
_MILLI = 1000.0


def _row(table: SdrTable, name: str) -> tuple[float | str, ...]:
    for row in table.rows:
        if row[0] == name:
            return row
    raise SdrError(f"{table.direction}・{table.condition} の【{table.title}】に「{name}」の行がありません")


def _cell(table: SdrTable, name: str, prefix: str) -> float:
    """The number under the column of *table* whose name starts with *prefix*, in the row *name*."""
    row = _row(table, name)
    for index, column in enumerate(table.columns):
        if column.startswith(prefix):
            value = row[index]
            if isinstance(value, str):
                raise SdrError(f"【{table.title}】の「{name}」の{prefix}が数値ではありません（{value}）")
            return value
    raise SdrError(f"【{table.title}】に{prefix}の列がありません")


def limits(found: SdrFile, direction: Direction) -> dict[Requirement, Limits]:
    """The limits of the three requirements in *direction*."""
    name = SDR_DIRECTION[direction.turned]
    vertical = found.table(name, CONDITION, "設計鉛直支持力の算定")
    pull = found.table(name, CONDITION, "設計引き抜き抵抗力の算定")
    horizontal = found.table(name, CONDITION, "水平変位の照査")
    rotation = found.table(name, CONDITION, "回転角の照査")
    result = {}
    for requirement, item, _, _, _ in REQUIREMENTS:
        indicator = _row(horizontal, item)[2]
        if not isinstance(indicator, str):
            raise SdrError(f"【水平変位の照査】の「{item}」の設計限界値の指標が文字ではありません")
        result[requirement] = Limits(
            rk=_FORCE(_cell(vertical, item, "基準支持力Rk")), pt=_FRACTION(_cell(vertical, item, "先端支持力比")),
            fr=_FRACTION(_cell(vertical, item, "地盤抵抗係数fr")), rvd=_FORCE(_cell(vertical, item, "設計鉛直支持力Rvd")),
            rud=_FORCE(_cell(pull, item, "設計引き抜き抵抗力")),
            delta=_DISPLACEMENT(_cell(horizontal, item, "設計限界値δL")), indicator=indicator,
            theta=_ROTATION(_cell(rotation, item, "設計限界値θL") / _MILLI))
    return result
