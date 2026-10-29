"""What the JRSNAP model of a pile foundation takes of the 解析連携データ (.sdc) (decision 93).

The frame of 0610 and 0620 reads the long-term and the linear short-term springs (``sdc.parse_sdc``). The model of 0710 and
0720 reads the other tables: b) the 短期(非線形) horizontal spring, c) the effective resistance earth pressure (of the
case that is not the response displacement method), d) and e) the vertical shear springs and the bearing capacity of the
pile surface and f) and g) what is at the tip. SOIL-JR 5.2 prints one table of d) and e) for each side (``Ver.5.2``: the
ones of 地震時); SOIL-JR 5.3 prints two (安定レベル1 and 安定レベル2・3, L1 and L2) and the model takes the last, the L2
one. Both name the part of a layer that has the spring (⊿l).

A layout that lists the pile rows (``N列目``, K_FLG = 1) gives each row its column by number. A layout that does not (K_FLG 0,
a regular grid or a staggered one, decision 122) has one column for every row (``全列``) or one for the odd rows and one for
the even rows in b) and d)〜g), and in c) the pressures of the 1列目, the 2列目 and the rows after (``3列目以降``, or
``3列目以降奇数列`` and ``4列目以降偶数列``) from the front of the push; it is read as a listed layout whose row *n* has the
springs of its column and the pressures of its place, with no distances (the rows are not listed).

The .sdc for the liquefaction (``<名前>(液状化時用).sdc``, decision 95) has the same tables, with 液状化時 where the
short-term nonlinear one and 地震時 are (b) and the effective resistance earth pressure, d) and e), g)); ``liquefied``
reads it, and it is told apart by the title of g) (``液状化時：杭先端の鉛直…``, else ``地震時：…``).
"""

from __future__ import annotations

from collections.abc import Iterable

from ...calc.pile_springs import (
    ALL, EVEN, ODD, SeismicDirection, SeismicLayer, SeismicSprings, SeismicTip, SurfaceSide,
)
from .sdc import (
    _DIRECTION, _ROW_COLUMN, ENCODING, SdcError, _arrangement, _columns, _header, _is_row, _numbers, _sections,
)

PUSH, PULL = "【押込み側】", "【引抜き側】"


def _runs(lines: Iterable[str]) -> list[list[list[str]]]:
    """The runs of rows of numbers in *lines*, in order: a run ends at a line that is not a row."""
    runs: list[list[list[str]]] = []
    inside = False
    for line in lines:
        cells = [cell.strip() for cell in line.split(",")]
        if _is_row(cells):
            if not inside:
                runs.append([])
            runs[-1].append(cells)
            inside = True
        else:
            inside = False
    return runs


def _sides(lines: list[str], what: str) -> tuple[list[list[str]], list[list[str]]]:
    """The last table of the push side and of the pull side of d) or e)."""
    try:
        push_at = lines.index(PUSH)
        pull_at = lines.index(PULL)
    except ValueError:
        raise SdcError(f"{what}に{PUSH}または{PULL}がありません") from None
    found = []
    for region in (lines[push_at:pull_at], lines[pull_at:]):
        runs = _runs(region)
        if not runs:
            raise SdcError(f"{what}に層の表がありません")
        found.append(runs[-1])
    return found[0], found[1]


def _side(spring: list[str], strength: list[str], columns: int, what: str) -> SurfaceSide:
    spring_values, strength_values = _numbers(spring), _numbers(strength)
    if len(spring_values) == 3 + 4 * columns:  # 5.2: layer, thickness, 長期, 短期, ⊿l, 第1勾配, 第2勾配
        length, first = spring_values[2 + 2 * columns], spring_values[3 + 2 * columns:3 + 3 * columns]
        second = spring_values[3 + 3 * columns:]
    elif len(spring_values) == 2 + 2 * columns:  # 5.3, L2: layer, ⊿l, 第1勾配, 第2勾配
        length, first, second = spring_values[1], spring_values[2:2 + columns], spring_values[2 + columns:]
    else:
        raise SdcError(f"{what}の層 {spring[0]} の項目数が違います（{len(spring_values)}）")
    if len(strength_values) != 3 + 2 * columns:
        raise SdcError(f"{what}（杭周面の支持力）の層 {strength[0]} の項目数が違います（{len(strength_values)}）")
    if abs(strength_values[2] - length) > 1e-9:
        raise SdcError(f"{what}の層 {spring[0]} の⊿l がばねの表（{length}）と支持力の表（{strength_values[2]}）で違います")
    return SurfaceSide(length=length, first=first, second=second,
                       yield_load=strength_values[3:3 + columns], ultimate=strength_values[3 + columns:])


def _group(lines: list[str], title: str, groups: int, columns: int, what: str) -> tuple[tuple[float, ...], ...]:
    """The line of numbers below *title*, split into *groups* of *columns* (f) and g))."""
    at = next((index for index, line in enumerate(lines) if line.startswith(title)), None)
    if at is None:
        raise SdcError(f"{what}に{title}がありません")
    values = next((_numbers(line.split(",")) for line in lines[at + 1:]
                   if line.split(",")[0].strip().replace(".", "", 1).isdigit()), None)
    if values is None or len(values) != groups * columns:
        raise SdcError(f"{what}の{title}の項目数が違います")
    return tuple(values[group * columns:(group + 1) * columns] for group in range(groups))


def _direction(name: str, lines: list[str], tip: str) -> SeismicDirection:
    sections = _sections(lines)
    for key in "abcdefg":
        if key not in sections:
            raise SdcError(f"{name}: {key}）がありません")
    rows, depth, inverse, listed = _arrangement(sections["a"])
    columns = _columns(sections["b"])
    if all(_ROW_COLUMN.match(column) for column in columns) and len(columns) == rows == len(listed):
        return _listed(name, sections, rows, columns, inverse, listed, tip)
    if columns not in ((ALL,), (ODD, EVEN)):
        raise SdcError(f"{name}: 杭の列の配置（{','.join(columns)}）に対応していません")
    places = _places(sections["c"], name)
    direction = _listed(name, sections, rows, columns, inverse, (), tip, pressures=places)
    by_row = [0 if columns == (ALL,) or row % 2 == 1 else 1 for row in range(1, rows + 1)]
    place = _place_of(places, rows, name)

    def spread(values: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(values[column] for column in by_row)

    def side(found: SurfaceSide) -> SurfaceSide:
        return SurfaceSide(length=found.length, first=spread(found.first), second=spread(found.second),
                           yield_load=spread(found.yield_load), ultimate=spread(found.ultimate))

    layers = tuple(SeismicLayer(number=layer.number, thickness=layer.thickness, horizontal=spread(layer.horizontal),
                                pressure_upper=tuple(layer.pressure_upper[at] for at in place),
                                pressure_lower=tuple(layer.pressure_lower[at] for at in place),
                                push=side(layer.push), pull=side(layer.pull)) for layer in direction.layers)
    t = direction.tip
    return SeismicDirection(name=name, rows=rows, columns=tuple(f"{row}列目" for row in range(1, rows + 1)),
                            depth_piles=tuple(depth[column] for column in by_row), inverse_beta=inverse, distances=(),
                            layers=layers, tip=SeismicTip(first=spread(t.first), second=spread(t.second),
                                                          yield_load=spread(t.yield_load), ultimate=spread(t.ultimate),
                                                          horizontal=spread(t.horizontal), rotation=spread(t.rotation)))


def _places(lines: list[str], name: str) -> tuple[str, ...]:
    """The names of the columns of the first table of c) of a layout that does not list its rows."""
    header = next((line for line in lines if line.startswith(",,") and "列目" in line), None)
    if header is None:
        raise SdcError(f"{name}: c）に列の見出しがありません")
    return tuple(cell.strip() for cell in header.split(",") if cell.strip())


def _place_of(places: tuple[str, ...], rows: int, name: str) -> list[int]:
    """The column of c) of each row from the front: its own, or the one of the rows after the second (by parity when the odd
    and the even rows have their own)."""
    found = []
    for row in range(1, rows + 1):
        names = (f"{row}列目", "3列目以降", "3列目以降奇数列" if row % 2 == 1 else "4列目以降偶数列")
        at = next((places.index(title) for title in names if title in places), None)
        if at is None:
            raise SdcError(f"{name}: c）に杭列 {row} の列がありません（{','.join(places)}）")
        found.append(at)
    return found


def _listed(name: str, sections: dict[str, list[str]], rows: int, columns: tuple[str, ...], inverse: float,
            listed: tuple, tip: str, pressures: tuple[str, ...] | None = None) -> SeismicDirection:
    """The direction with the columns *columns* of b) and d)〜g); c) has the columns *pressures* (the same when None)."""
    count = len(columns)
    pressure_count = count if pressures is None else len(pressures)
    piles = tuple(row.piles for row in listed)
    b_rows = _runs(sections["b"])
    c_rows = _runs(sections["c"])
    if not b_rows or not c_rows:
        raise SdcError(f"{name}: b）または c）に層の表がありません")
    push_spring, pull_spring = _sides(sections["d"], f"{name}: d）")
    push_strength, pull_strength = _sides(sections["e"], f"{name}: e）")
    if not (len(b_rows[0]) == len(c_rows[0]) == len(push_spring) == len(pull_spring) == len(push_strength)
            == len(pull_strength)):
        raise SdcError(f"{name}: b）〜e）の層の数が違います")
    layers = []
    for index, h in enumerate(b_rows[0]):
        values, pressure = _numbers(h), _numbers(c_rows[0][index])
        if len(values) != 2 + 3 * count or len(pressure) != 2 + 2 * pressure_count:
            raise SdcError(f"{name}: b）または c）の層 {h[0]} の項目数が違います")
        layers.append(SeismicLayer(
            number=int(values[0]), thickness=values[1], horizontal=values[2 + 2 * count:],
            pressure_upper=pressure[2::2], pressure_lower=pressure[3::2],
            push=_side(push_spring[index], push_strength[index], count, f"{name}: d）押込み側"),
            pull=_side(pull_spring[index], pull_strength[index], count, f"{name}: d）引抜き側")))
    first, second = _group(sections["f"], "杭先端の鉛直", 3, count, f"{name}: f）")[1:]
    horizontal = _group(sections["f"], "杭先端の水平", 2, count, f"{name}: f）")[1]
    rotation = _group(sections["f"], "杭先端の回転", 2, count, f"{name}: f）")[1]
    yield_load, ultimate = _group(sections["g"], tip, 2, count, f"{name}: g）")
    return SeismicDirection(name=name, rows=rows, columns=columns, depth_piles=piles, inverse_beta=inverse,
                            distances=tuple(row.distance for row in listed), layers=tuple(layers),
                            tip=SeismicTip(first=first, second=second, yield_load=yield_load, ultimate=ultimate,
                                           horizontal=horizontal, rotation=rotation))


def parse_seismic(data: bytes, *, liquefied: bool = False) -> SeismicSprings:
    """The seismic ground springs of a .sdc of SOIL-JR 5.2 or 5.3, or with *liquefied* of the one for the liquefaction."""
    try:
        lines = data.decode(ENCODING).replace("\r\n", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise SdcError(f".sdc を CP932 として読めません（{exc}）") from exc
    if len(lines) < 10 or lines[0].strip() != "【バージョン情報】" or not lines[1].startswith(("Ver.5.2", "Ver.5.3")):
        raise SdcError("SOIL-JR 5.2・5.3 の .sdc ではありません")
    try:
        start = lines.index("【解析用地盤ばね値】")
    except ValueError:
        raise SdcError(".sdc に【解析用地盤ばね値】がありません") from None
    blocks: list[tuple[str, list[str]]] = []
    for line in lines[start + 1:]:
        if match := _DIRECTION.match(line):
            blocks.append((match.group(1).strip(), []))
        elif blocks:
            blocks[-1][1].append(line)
    if not blocks:
        raise SdcError(".sdc に方向（（１）橋軸方向）がありません")
    return SeismicSprings(version=lines[1].strip(), title=lines[4], pile=_header(lines[:start], "杭情報"),
                          directions=tuple(_direction(name, body, "液状化時：杭先端の鉛直" if liquefied else "地震時：杭先端の鉛直")
                                           for name, body in blocks))
