"""What the JRSNAP model of a pile foundation takes of the 解析連携データ (.sdc) (decision 93).

The frame of 0610 and 0620 reads the long-term and the linear short-term springs (``sdc.parse_sdc``). The model of 0710 and
0720 reads the other tables: b) the 短期(非線形) horizontal spring, c) the effective resistance earth pressure (of the
case that is not the response displacement method), d) and e) the vertical shear springs and the bearing capacity of the
pile surface and f) and g) what is at the tip. SOIL-JR 5.2 prints one table of d) and e) for each side (``Ver.5.2``: the
ones of 地震時); SOIL-JR 5.3 prints two (安定レベル1 and 安定レベル2・3, L1 and L2) and the model takes the last, the L2
one. Both name the part of a layer that has the spring (⊿l).

Only a layout that lists the pile rows (``N列目``, K_FLG = 1) is read: the rows of the model take their columns by number.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...calc.pile_springs import SeismicDirection, SeismicLayer, SeismicSprings, SeismicTip, SurfaceSide
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


def _direction(name: str, lines: list[str]) -> SeismicDirection:
    sections = _sections(lines)
    for key in "abcdefg":
        if key not in sections:
            raise SdcError(f"{name}: {key}）がありません")
    rows, depth, inverse, listed = _arrangement(sections["a"])
    columns = _columns(sections["b"])
    if not all(_ROW_COLUMN.match(column) for column in columns) or len(columns) != rows or len(listed) != rows:
        raise SdcError(f"{name}: 杭の列を並べた配置（1列目、2列目、…）だけに対応します（{','.join(columns)}）")
    count = len(columns)
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
        if len(values) != 2 + 3 * count or len(pressure) != 2 + 2 * count:
            raise SdcError(f"{name}: b）または c）の層 {h[0]} の項目数が違います")
        layers.append(SeismicLayer(
            number=int(values[0]), thickness=values[1], horizontal=values[2 + 2 * count:],
            pressure_upper=pressure[2::2], pressure_lower=pressure[3::2],
            push=_side(push_spring[index], push_strength[index], count, f"{name}: d）押込み側"),
            pull=_side(pull_spring[index], pull_strength[index], count, f"{name}: d）引抜き側")))
    first, second = _group(sections["f"], "杭先端の鉛直", 3, count, f"{name}: f）")[1:]
    horizontal = _group(sections["f"], "杭先端の水平", 2, count, f"{name}: f）")[1]
    rotation = _group(sections["f"], "杭先端の回転", 2, count, f"{name}: f）")[1]
    yield_load, ultimate = _group(sections["g"], "地震時：杭先端の鉛直", 2, count, f"{name}: g）")
    return SeismicDirection(name=name, rows=rows, columns=columns, depth_piles=piles, inverse_beta=inverse,
                            layers=tuple(layers),
                            tip=SeismicTip(first=first, second=second, yield_load=yield_load, ultimate=ultimate,
                                           horizontal=horizontal, rotation=rotation))


def parse_seismic(data: bytes) -> SeismicSprings:
    """The seismic ground springs of a .sdc of SOIL-JR 5.2 or 5.3."""
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
                          directions=tuple(_direction(name, body) for name, body in blocks))
