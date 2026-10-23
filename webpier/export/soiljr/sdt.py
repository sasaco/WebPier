"""The .sdt text of SOIL-JR 5.2.3 (Common.DataFileWrite): CP932, CRLF after every line including the last.

The layout is the one the screen saves (the skill structural-jrsnap-soil, references/sdt-format.md §12): the 基本条件, a
フーチング形状 without values (the footing is there but its front is not counted on), the 杭条件, the pile columns, the
rows of the ground (the ground above the pile head, then the layers along the pile), the 地盤抵抗係数 as the empty
mark so that SOIL-JR finds them itself, the 液状化の低減係数 and the empty 連携 section.

A number in a comma-separated line is the shortest decimal that reads back as it is (19, 0.785398); a number alone on
its line follows Visual Basic's ``Print``: a space before a non-negative number and one after every number (`` 8 ``).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ...calc.pile_ground import PileColumn, PileGroundResult, SoilRow
from ...core.printed import Printed

ENCODING = "cp932"
NEWLINE = "\r\n"
SOIL_JR_VERSION = "Ver.5.2.3.T08"  # SOIL-JR 5.2.3 writes "Ver.<assembly version>.T08"
EMPTY = "-123456789.123457"  # SOIL-JR's mark of a value not entered (DBL_EMP)
TITLE_BYTES = 128  # SOIL-JR's limit of the title
DESCRIPTION_BYTES = 512  # and of the description


def number(value: Printed | float | int | Decimal) -> str:
    """The number as SOIL-JR writes one in a comma-separated line."""
    raw = Decimal(repr(value.value)) if isinstance(value, Printed) else (
        value if isinstance(value, Decimal) else Decimal(repr(value)))
    text = format(raw.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def spaced(value: Printed | float | int) -> str:
    """A number alone on its line, as Visual Basic prints it."""
    text = number(value)
    return text + " " if text.startswith("-") else " " + text + " "


def zone(first: Printed | float | int, second: Printed | float | int) -> str:
    """Two numbers on one line as Visual Basic prints them: the first fills a zone of 14 characters."""
    return spaced(first).ljust(14) + spaced(second)


def _row(values: Sequence[str]) -> str:
    return ",".join(values)


def _check_text(text: str, limit: int, what: str) -> str:
    try:
        size = len(text.encode(ENCODING))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{what}を Shift-JIS で書けません: {text!r}") from exc
    if size > limit or "\r" in text.replace("\r\n", "") or "\x00" in text:
        raise ValueError(f"{what}は{limit}バイト以内の文字列にしてください（{size}バイト）")
    return text


def _layer_row(row: SoilRow) -> str:
    # Ex = Ed, ρgE = γgE = 1: SOIL-JR then takes Ed as it is (decision 80); qsuk from the N value for a sand or gravel
    # and from the cohesion for a clay (decision 80, SOIL-JR's default of each)
    modulus = number(row.deformation_modulus)
    return _row([number(row.thickness), str(row.kind), number(row.n_value), number(row.cohesion),
                 number(row.friction_angle), number(row.unit_weight_wet), number(row.unit_weight_submerged), modulus,
                 "1", "1", modulus, "0" if row.kind == 2 else "1", "0"])


def _columns(columns: Sequence[PileColumn]) -> list[str]:
    return [_row([str(column.count), number(column.distance)]) for column in columns]


def build_sdt(result: PileGroundResult, *, title: str, description: str) -> bytes:
    """The .sdt of *result*. *title* and *description* are SOIL-JR's タイトル and 説明 (free text, on its report)."""
    title = _check_text(title, TITLE_BYTES, "タイトル")
    lines = description.split("\r\n") if description else [""]
    description = _check_text("\r\n".join(lines), DESCRIPTION_BYTES, "説明")
    section, rows, head = result.section, result.rows, result.head
    empty = EMPTY
    out = [SOIL_JR_VERSION, "●基本条件●", title, spaced(len(lines)), *lines,
           spaced(1), "1,1", spaced(rows.piles), "", "●フーチング形状●", _row([empty] * 5), "", "●杭条件●",
           _row([str(rows.pattern), str(len(rows.along)), str(len(rows.across)), number(rows.spacing_along),
                 number(rows.spacing_across), *map(number, rows.lm), *map(number, rows.ln), str(section.kind),
                 str(section.method), "0", "0", str(section.construction), "0", "0"]),
           _row([number(result.length), "0", number(section.minimum_embedment), number(result.water_depth),
                 empty if section.es is None else number(section.es), empty if section.ec is None else number(section.ec),
                 number(section.diameter), empty if section.inner_diameter is None else number(section.inner_diameter),
                 empty if section.thickness is None else number(section.thickness), empty,
                 empty if section.corrosion is None else number(section.corrosion), number(section.area),
                 number(section.second_moment), number(section.unit_weight)]),
           "", spaced(1 if rows.rows_written else 0), "橋軸方向", *_columns(rows.along), "直角方向",
           *_columns(rows.across), "", spaced(len(rows.removed)),
           *(_row([str(across), str(along)]) for across, along in rows.removed), "",
           "●地盤条件●", _row([str(len(result.layers)), "0"]),
           _row([number(head.thickness), "0", "0", "0", "0", number(head.unit_weight_wet),
                 number(head.unit_weight_submerged), "0", "0", "0", "0", "2", "0"]),
           *(_layer_row(row) for row in result.layers),
           zone(0, 0), spaced(0), "", "●地盤抵抗係数",
           *([_row([empty] * 11 + ["0"])] * 5), _row([empty, empty, "0"]), "●液状化の低減係数",
           spaced(1 if result.liquefaction else 0),
           *(_row([str(index), number(1 if row.reduction is None else row.reduction)])
             for index, row in enumerate(result.layers, 1)),
           "", "", _row(["0", "2", "1", "0"])]
    return "".join(line + NEWLINE for line in out).encode(ENCODING, errors="strict")
