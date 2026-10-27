"""The 鉄筋 section: reinforcement of the beam, the column and the footing (lengths in mm).

Parsing checks the form only (decisions 17, 19): every key is required, digits, choices and unknown keys.
A blank (null) is a value the editor has not been given yet. Nothing is filled in here or later: the column
layout (calc.column_rebar) and the JRSNAP export ask for the values they use and report a blank as an input
error naming its path. The concrete strengths of this section are read into ``Materials`` (parse.py).

Column coordinates: origin at the upper-left corner, X across the track (W6), Y along it (B6). A 線路 row
lies on the two faces normal to Y, a 直角 row on the two faces normal to X (CONTEXT.md 柱の軸方向鉄筋).
A direction's layers inside layer 1 take only their 片面本数 and clear gap; changes made in the 方向別の鉄筋配置表
are kept per table, keyed by the generated centre and size (decision 68). A beam face likewise has one size,
layer 1 and the layers inside it; the side bars are null when there are none. A footing face holds both
directions, each with layer 1 and the layers inside it, and names the direction outside.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.printed import Printed
from ..core.reader import AbsentAsBlank, Reader
from . import choices
from .fields import LENGTH_MM, PILE_HOOP_ZONES, PILE_MEMBER, read

__all__ = ["LENGTH_MM", "PILE_LOWER_HOOPS", "RebarInput", "parse_rebar"]  # the digits come from the field table
REBAR_VERSION = 3
PILE_LOWER_HOOPS = 3  # the zones of hoops below the 2D zone of a cast-in-place pile (decision 87)


@dataclass(frozen=True)
class SteelMaterials:
    """The steels of a member: the main bars' (and the side bars'), and the transverse bars' (hoops, stirrups)."""

    main: str | None
    transverse: str | None


@dataclass(frozen=True)
class Distribution:
    """How the bars of one column face are spaced along the face."""

    mode: str | None  # choices.DISTRIBUTION_MODES
    edge_center: Printed | None  # centre of an end bar from the side face
    pitch: Printed | None


@dataclass(frozen=True)
class InnerLayer:
    """A layer inside layer 1 of a column direction: its 片面本数 and the clear gap to the layer outside it (the size
    and the distribution are layer 1's)."""

    per_face_count: int | None
    clear_gap: Printed | None


@dataclass(frozen=True)
class ColumnMainBars:
    """The main bars of one direction on its two opposite faces: layer 1 in full, then the layers inside it."""

    diameter: Printed | None
    per_face_count: int | None  # 片面本数 of layer 1
    cover_mode: str | None  # 自動: the pure cover + the enclosing hoop + half the bar; 指定: center
    center: Printed | None  # 主鉄筋の芯かぶり of layer 1 when 指定
    endpoints: str | None  # 等分: whether the end positions carry a bar
    distribution: Distribution
    inner_layers: tuple[InnerLayer, ...]


@dataclass(frozen=True)
class TableOverride:
    """A change made in the 方向別の鉄筋配置表: the bars generated at source_center (from the reference face of the
    direction) with source_diameter take center and/or diameter instead."""

    source_center: Printed
    source_diameter: Printed
    center: Printed | None
    diameter: Printed | None


@dataclass(frozen=True)
class HoopRow:
    """帯鉄筋の方向別有効本数: the hoop legs effective for one shear direction (not a shape)."""

    direction: str | None
    diameter: Printed | None
    effective_legs: int | None
    pitch: Printed | None
    start: Printed | None  # from the column base
    end: Printed | None


@dataclass(frozen=True)
class ColumnHoops:
    enclosing_diameter: Printed | None  # the outer hoop around the main bars (純かぶり → 芯かぶり)
    rows: tuple[HoopRow, ...]


@dataclass(frozen=True)
class ColumnBars:
    materials: SteelMaterials
    pure_cover: Printed | None  # 純かぶり
    main_bars: dict[str, ColumnMainBars]  # by direction, choices.REBAR_DIRECTIONS
    overrides: dict[str, tuple[TableOverride, ...]]  # by the direction of the table
    hoops: ColumnHoops
    aggregate_max: Printed | None  # 粗骨材最大寸法 Dmax, mm (decision 48)


@dataclass(frozen=True)
class BeamLayer:
    """A layer inside layer 1 of a beam face: its count and the clear gap to the layer outside it (one size per
    face)."""

    count: int | None
    clear_gap: Printed | None


@dataclass(frozen=True)
class BeamFace:
    """The main bars of one face of the beam: layer 1 in full, then the layers inside it."""

    diameter: Printed | None
    count: int | None  # layer 1
    bar_type: str | None  # the upper face's shape; the lower bars are straight and have none
    cover_mode: str | None  # 自動: the pure cover + the stirrup + half the bar; 指定: center
    center: Printed | None
    inner_layers: tuple[BeamLayer, ...]


@dataclass(frozen=True)
class BeamSideBars:
    diameter: Printed | None
    per_face_count: int | None
    start: Printed | None  # centre of the first bar from the upper face
    pitch: Printed | None
    stirrup_position: str | None  # 内側: inside the stirrups; 外側: outside
    cover_mode: str | None  # 自動: the pure cover (+ the stirrup when inside) + half the bar; 指定: center
    center: Printed | None  # from the side face


@dataclass(frozen=True)
class BeamStirrups:
    diameter: Printed | None
    effective_legs: int | None
    pitch: Printed | None


@dataclass(frozen=True)
class BeamBars:
    materials: SteelMaterials
    pure_cover: Printed | None
    faces: dict[str, BeamFace]  # by face, choices.BEAM_FACES
    side: BeamSideBars | None  # None: no side bars (null)
    stirrups: BeamStirrups
    aggregate_max: Printed | None  # 粗骨材最大寸法 Dmax of the beam concrete, mm (decision 59)


@dataclass(frozen=True)
class FootingLayer:
    """A layer inside layer 1 of a footing direction: its pitch and the clear gap to the previous layer of the
    direction (the size is layer 1's)."""

    pitch: Printed | None
    clear_gap: Printed | None


@dataclass(frozen=True)
class FootingMainBars:
    """The main bars of one direction on one face of the footing: layer 1 in full, then the layers inside it."""

    diameter: Printed | None
    pitch: Printed | None
    cover_mode: str | None  # 自動: the pure cover and the outer direction's layer 1 under it; 指定: center
    center: Printed | None  # from the face
    inner_layers: tuple[FootingLayer, ...]


@dataclass(frozen=True)
class FootingFace:
    outer_direction: str | None  # the direction whose layer 1 lies against the face
    bars: dict[str, FootingMainBars]  # by direction, choices.REBAR_DIRECTIONS


@dataclass(frozen=True)
class FootingStirrups:
    diameter: Printed | None
    pitch: Printed | None  # along the overhang
    width_mode: str | None  # across the width: by spacing (width_pitch) or by the bars per metre (density)
    width_pitch: Printed | None
    density: Printed | None


@dataclass(frozen=True)
class FootingBars:
    materials: SteelMaterials
    pure_cover: Printed | None
    faces: dict[str, FootingFace]  # by face, choices.BEAM_FACES
    stirrups: dict[str, FootingStirrups]  # by direction
    aggregate_max: Printed | None  # 粗骨材最大寸法 Dmax of the footing concrete, mm (decision 60)


@dataclass(frozen=True)
class PileHoop:
    """The hoops of one zone of a 場所打ち杭: size, 組 (a closed circular hoop is one 組, which crosses the section twice)
    and pitch."""

    diameter: Printed | None
    sets: int | None
    pitch: Printed | None


@dataclass(frozen=True)
class PileLowerHoop:
    length: Printed | None  # 区間長, m
    hoop: PileHoop


@dataclass(frozen=True)
class PileHoops:
    footing: PileHoop  # the part inside the footing
    zone_2d: PileHoop  # the 2D zone from the head (D: the pile diameter), the one the pile body check uses
    lower: tuple[PileLowerHoop, ...]  # the zones below it, at most PILE_LOWER_HOOPS


@dataclass(frozen=True)
class PileCutoff:
    """The cut-off of the bars of a 場所打ち杭 (decision 87): the section after it, the lengths and the rules. There is none
    while its main bars are blank. The 杭頭定着長 is calculated, not entered (decision 98: calc.detailing.pile)."""

    main_diameter: Printed | None
    main_count: int | None
    hoop: PileHoop
    cutoff_length: Printed | None  # 段落し長, mm
    cutoff_anchorage: Printed | None  # 段落し定着長, mm
    joint_reduction: Printed | None  # 継手低減係数
    margin: Printed | None  # 設計余裕長, mm
    no_joint_from_head: Printed | None  # 継ぎ手を設けない範囲: from the head, mm
    no_joint_above: Printed | None  # from the cut-off point, upward, mm
    no_joint_below: Printed | None  # from the cut-off point, downward, mm
    margin_moment: Printed | None  # 余裕率: bending moment
    margin_shear: Printed | None  # 余裕率: shear force


@dataclass(frozen=True)
class PileBars:
    """The reinforcement of a 場所打ち杭 (decisions 87 and 92); its f'ck, diameter and construction condition are the
    杭基礎's."""

    materials: SteelMaterials
    pure_cover: Printed | None  # 純かぶり
    aggregate_max: Printed | None  # 粗骨材最大寸法 Dmax, mm
    main_diameter: Printed | None  # 主鉄筋 (all along the pile)
    main_count: int | None  # all round the pile
    hoops: PileHoops
    cutoff: PileCutoff


@dataclass(frozen=True)
class RebarInput:
    beam: BeamBars
    column: ColumnBars
    footing: FootingBars
    pile: PileBars


def _value(node: Reader, key: str):
    """A rebar value through the field table; every one may stay blank (None) while it is being entered."""
    return read(node.at(key))


def _ordered(node: Reader, start: Printed | None, end: Printed | None) -> None:
    if start is not None and end is not None and end.value < start.value:
        raise node.at("end_mm").error("開始位置以上が必要です")


def _materials(node: Reader) -> SteelMaterials:
    node.only("main", "transverse")
    return SteelMaterials(main=_value(node, "main"), transverse=_value(node, "transverse"))


def _column_bars(node: Reader) -> ColumnMainBars:
    node.only("diameter_mm", "per_face_count", "cover_mode", "center_mm", "endpoints", "distribution", "inner_layers")
    spacing = node.at("distribution").only("mode", "edge_center_mm", "pitch_mm")
    inner = []
    for layer in node.at("inner_layers").items():
        layer.only("per_face_count", "clear_gap_mm")
        inner.append(InnerLayer(per_face_count=_value(layer, "per_face_count"),
                                clear_gap=_value(layer, "clear_gap_mm")))
    bars = ColumnMainBars(
        diameter=_value(node, "diameter_mm"), per_face_count=_value(node, "per_face_count"),
        cover_mode=_value(node, "cover_mode"), center=_value(node, "center_mm"), endpoints=_value(node, "endpoints"),
        distribution=Distribution(mode=_value(spacing, "mode"), edge_center=_value(spacing, "edge_center_mm"),
                                  pitch=_value(spacing, "pitch_mm")),
        inner_layers=tuple(inner))
    if bars.distribution.mode == choices.EDGE_AND_PITCH and bars.per_face_count == 1:
        raise node.at("per_face_count").error(f"{choices.EDGE_AND_PITCH}の配列は2本以上が必要です")
    return bars


def _overrides(node: Reader) -> tuple[TableOverride, ...]:
    """The changes of one table. A change whose generated bars no longer exist is the layout's to report (a warning in
    the editor); a change of nothing, or two changes of one generated row, cannot be applied."""
    found: list[TableOverride] = []
    for row in node.items():
        row.only("source_center_mm", "source_diameter_mm", "center_mm", "diameter_mm")
        override = TableOverride(source_center=_value(row, "source_center_mm"),
                                 source_diameter=_value(row, "source_diameter_mm"),
                                 center=_value(row, "center_mm"), diameter=_value(row, "diameter_mm"))
        if override.center is None and override.diameter is None:
            raise row.error("芯位置か径の変更が必要です")
        if any((other.source_center, other.source_diameter) == (override.source_center, override.source_diameter)
               for other in found):
            raise row.error("同じ元の芯位置・径の変更がほかの行にあります")
        found.append(override)
    return tuple(found)


def _hoops(node: Reader) -> ColumnHoops:
    node.only("enclosing_diameter_mm", "direction_rows")
    rows = []
    for row in node.at("direction_rows").items():
        row.only("direction", "diameter_mm", "effective_legs", "pitch_mm", "start_mm", "end_mm")
        start, end = _value(row, "start_mm"), _value(row, "end_mm")
        _ordered(row, start, end)
        rows.append(HoopRow(direction=_value(row, "direction"), diameter=_value(row, "diameter_mm"),
                            effective_legs=_value(row, "effective_legs"),
                            pitch=_value(row, "pitch_mm"), start=start, end=end))
    return ColumnHoops(enclosing_diameter=_value(node, "enclosing_diameter_mm"), rows=tuple(rows))


def _column(node: Reader) -> ColumnBars:
    node.only("materials", "concrete_strength_mpa", "aggregate_max_mm", "pure_cover_mm", "main_bars", "table_overrides",
              "column_hoops")
    bars = node.at("main_bars").only(*choices.REBAR_DIRECTIONS)
    overrides = node.at("table_overrides").only(*choices.REBAR_DIRECTIONS)
    return ColumnBars(
        materials=_materials(node.at("materials")), pure_cover=_value(node, "pure_cover_mm"),
        main_bars={direction: _column_bars(bars.at(direction)) for direction in choices.REBAR_DIRECTIONS},
        overrides={direction: _overrides(overrides.at(direction)) for direction in choices.REBAR_DIRECTIONS},
        hoops=_hoops(node.at("column_hoops")), aggregate_max=_value(node, "aggregate_max_mm"))


def _beam_face(node: Reader, *, shaped: bool) -> BeamFace:
    node.only("diameter_mm", "count", "cover_mode", "center_mm", "inner_layers", *(("bar_type",) if shaped else ()))
    inner = []
    for layer in node.at("inner_layers").items():
        layer.only("count", "clear_gap_mm")
        inner.append(BeamLayer(count=_value(layer, "count"), clear_gap=_value(layer, "clear_gap_mm")))
    return BeamFace(diameter=_value(node, "diameter_mm"), count=_value(node, "count"),
                    bar_type=_value(node, "bar_type") if shaped else None, cover_mode=_value(node, "cover_mode"),
                    center=_value(node, "center_mm"), inner_layers=tuple(inner))


def _beam_side(node: Reader) -> BeamSideBars | None:
    if node.is_null:
        return None
    node.only("diameter_mm", "per_face_count", "start_mm", "pitch_mm", "stirrup_position", "cover_mode", "center_mm")
    return BeamSideBars(
        diameter=_value(node, "diameter_mm"), per_face_count=_value(node, "per_face_count"),
        start=_value(node, "start_mm"), pitch=_value(node, "pitch_mm"),
        stirrup_position=_value(node, "stirrup_position"), cover_mode=_value(node, "cover_mode"),
        center=_value(node, "center_mm"))


def _beam(node: Reader) -> BeamBars:
    node.only("materials", "concrete_strength_mpa", "aggregate_max_mm", "pure_cover_mm", "faces", "side_bars",
              "stirrups")
    faces = node.at("faces").only(*choices.BEAM_FACES)
    stirrups = node.at("stirrups").only("diameter_mm", "effective_legs", "pitch_mm")
    return BeamBars(
        materials=_materials(node.at("materials")), pure_cover=_value(node, "pure_cover_mm"),
        faces={face: _beam_face(faces.at(face), shaped=face == choices.BEAM_FACES[0]) for face in choices.BEAM_FACES},
        side=_beam_side(node.at("side_bars")),
        stirrups=BeamStirrups(diameter=_value(stirrups, "diameter_mm"),
                              effective_legs=_value(stirrups, "effective_legs"), pitch=_value(stirrups, "pitch_mm")),
        aggregate_max=_value(node, "aggregate_max_mm"))


def _footing_bars(node: Reader) -> FootingMainBars:
    node.only("diameter_mm", "pitch_mm", "cover_mode", "center_mm", "inner_layers")
    inner = []
    for layer in node.at("inner_layers").items():
        layer.only("pitch_mm", "clear_gap_mm")
        inner.append(FootingLayer(pitch=_value(layer, "pitch_mm"), clear_gap=_value(layer, "clear_gap_mm")))
    return FootingMainBars(diameter=_value(node, "diameter_mm"), pitch=_value(node, "pitch_mm"),
                           cover_mode=_value(node, "cover_mode"), center=_value(node, "center_mm"),
                           inner_layers=tuple(inner))


def _footing_face(node: Reader) -> FootingFace:
    node.only("outer_direction", *choices.REBAR_DIRECTIONS)
    return FootingFace(outer_direction=_value(node, "outer_direction"),
                       bars={direction: _footing_bars(node.at(direction)) for direction in choices.REBAR_DIRECTIONS})


def _footing_stirrups(node: Reader) -> FootingStirrups:
    node.only("diameter_mm", "pitch_mm", "distribution_mode", "width_pitch_mm", "density_per_m")
    return FootingStirrups(diameter=_value(node, "diameter_mm"), pitch=_value(node, "pitch_mm"),
                           width_mode=_value(node, "distribution_mode"), width_pitch=_value(node, "width_pitch_mm"),
                           density=_value(node, "density_per_m"))


def _footing(node: Reader) -> FootingBars:
    node.only("materials", "concrete_strength_mpa", "aggregate_max_mm", "pure_cover_mm", "faces", "stirrups")
    faces = node.at("faces").only(*choices.BEAM_FACES)
    stirrups = node.at("stirrups").only(*choices.REBAR_DIRECTIONS)
    return FootingBars(
        materials=_materials(node.at("materials")), pure_cover=_value(node, "pure_cover_mm"),
        faces={face: _footing_face(faces.at(face)) for face in choices.BEAM_FACES},
        stirrups={direction: _footing_stirrups(stirrups.at(direction)) for direction in choices.REBAR_DIRECTIONS},
        aggregate_max=_value(node, "aggregate_max_mm"))


def _pile_hoop(node: Reader) -> PileHoop:
    return PileHoop(diameter=_value(node, "diameter_mm"), sets=_value(node, "sets"), pitch=_value(node, "pitch_mm"))


def _pile_lower(node: Reader) -> tuple[PileLowerHoop, ...]:
    rows = list(node.items())
    if len(rows) > PILE_LOWER_HOOPS:
        raise node.error(f"区間は{PILE_LOWER_HOOPS}つまでです")
    found = []
    for row in rows:
        row.only("length_m", "diameter_mm", "sets", "pitch_mm")
        found.append(PileLowerHoop(length=_value(row, "length_m"), hoop=_pile_hoop(row)))
    return tuple(found)


def _pile_cutoff(node: Reader) -> PileCutoff:
    node.only("main_bars", "hoops", "cutoff_length_mm", "cutoff_anchorage_mm", "joint_reduction", "margin_mm",
              "no_joint", "margin_ratio")
    bars = node.at("main_bars").only("diameter_mm", "count")
    no_joint = node.at("no_joint").only("from_head_mm", "above_mm", "below_mm")
    ratio = node.at("margin_ratio").only("moment", "shear")
    return PileCutoff(
        main_diameter=_value(bars, "diameter_mm"), main_count=_value(bars, "count"),
        hoop=_pile_hoop(node.at("hoops").only("diameter_mm", "sets", "pitch_mm")),
        cutoff_length=_value(node, "cutoff_length_mm"),
        cutoff_anchorage=_value(node, "cutoff_anchorage_mm"), joint_reduction=_value(node, "joint_reduction"),
        margin=_value(node, "margin_mm"), no_joint_from_head=_value(no_joint, "from_head_mm"),
        no_joint_above=_value(no_joint, "above_mm"), no_joint_below=_value(no_joint, "below_mm"),
        margin_moment=_value(ratio, "moment"), margin_shear=_value(ratio, "shear"))


def _pile(node: Reader) -> PileBars:
    node.only("materials", "pure_cover_mm", "aggregate_max_mm", "main_bars", "hoops", "cutoff")
    bars = node.at("main_bars").only("diameter_mm", "count")
    hoops = node.at("hoops").only(*PILE_HOOP_ZONES, "lower")
    return PileBars(
        materials=_materials(node.at("materials")), pure_cover=_value(node, "pure_cover_mm"),
        aggregate_max=_value(node, "aggregate_max_mm"), main_diameter=_value(bars, "diameter_mm"),
        main_count=_value(bars, "count"),
        hoops=PileHoops(footing=_pile_hoop(hoops.at("footing").only("diameter_mm", "sets", "pitch_mm")),
                        zone_2d=_pile_hoop(hoops.at("zone_2d").only("diameter_mm", "sets", "pitch_mm")),
                        lower=_pile_lower(hoops.at("lower"))),
        cutoff=_pile_cutoff(node.at("cutoff")))


def _uses_piles(root: Reader) -> bool:
    """Whether the 基礎形式 of the input is a pile foundation (its value is checked by parse_input)."""
    sub = root.optional("下部構造")
    foundation = None if sub is None else sub.optional("基礎形式")
    return foundation is not None and foundation.value in choices.PILE_FOUNDATIONS


def parse_rebar(root: Reader) -> RebarInput:
    rebar = root.at("鉄筋").only("version", "梁", "柱", "フーチング", PILE_MEMBER)
    rebar.at("version").integer(REBAR_VERSION, REBAR_VERSION)
    # 鉄筋.杭 is not used by another 基礎形式, so an absent item is blank (decision 107)
    pile = rebar if _uses_piles(root) else AbsentAsBlank(rebar.value, rebar.path)
    return RebarInput(beam=_beam(rebar.at("梁")), column=_column(rebar.at("柱")),
                      footing=_footing(rebar.at("フーチング")), pile=_pile(pile.at(PILE_MEMBER)))
