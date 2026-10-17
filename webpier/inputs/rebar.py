"""The 鉄筋 section: reinforcement of the beam, the column and the footing (lengths in mm).

Parsing checks the form only (decisions 17, 19): every key is required, digits, choices and unknown keys.
A blank (null) is a value the editor has not been given yet. Nothing is filled in here or later: the column
layout (calc.column_rebar) and the JRSNAP export ask for the values they use and report a blank as an input
error naming its path. The concrete strengths of this section are read into ``Materials`` (parse.py).

Column coordinates: origin at the upper-left corner, X across the track (W6), Y along it (B6). A 線路 row
lies on the two faces normal to Y, a 直角 row on the two faces normal to X (CONTEXT.md 柱の軸方向鉄筋).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.printed import Precision, Printed
from ..core.reader import Reader
from . import choices

REBAR_VERSION = 2
LENGTH_MM = Precision(1, "mm")  # covers, centres, gaps, pitches, positions
DIAMETER = Precision(0, "mm")  # nominal bar size (D32 → 32), as Example2 10-6 / 11-6 print it
SETS = Precision(1, "組")  # the old band input allows a fractional set count
DENSITY = Precision(1, "本/m")
MAX_COUNT = 10_000
MAX_LAYER = 100
BASIS_VERSION = 1


@dataclass(frozen=True)
class SteelMaterials:
    """The shared steel of a member; a row's own material overrides it."""

    main: str | None
    transverse: str | None


@dataclass(frozen=True)
class Distribution:
    """How the bars of one column face are spaced along the face."""

    mode: str | None  # choices.DISTRIBUTION_MODES
    edge_center: Printed | None  # centre of an end bar from the side face
    pitch: Printed | None


@dataclass(frozen=True)
class ColumnMainRow:
    """One layer of column main bars on a pair of opposite faces (片面本数 per face)."""

    diameter: Printed | None
    material: str | None
    cover_mode: str | None  # 自動: from the pure cover and the layers outside; 指定: center
    center: Printed | None  # 主鉄筋の芯かぶり when 指定
    clear_gap: Printed | None  # clear gap from the layer outside (layer > 1)
    face_direction: str | None
    layer: int | None
    per_face_count: int | None
    endpoints: str | None  # 等分: whether the end positions carry a bar
    distribution: Distribution


@dataclass(frozen=True)
class HoopRow:
    """帯鉄筋の方向別有効本数: the hoop legs effective for one shear direction (not a shape)."""

    direction: str | None
    diameter: Printed | None
    material: str | None
    effective_legs: int | None
    pitch: Printed | None
    start: Printed | None  # from the column base
    end: Printed | None


@dataclass(frozen=True)
class ColumnHoops:
    enclosing_diameter: Printed | None  # the outer hoop around the main bars (純かぶり → 芯かぶり)
    rows: tuple[HoopRow, ...]


@dataclass(frozen=True)
class ManualBar:
    x: Printed | None
    y: Printed | None
    diameter: Printed | None
    material: str | None


@dataclass(frozen=True)
class ManualBasis:
    """The basic input the detail positions were generated from, to tell whether it has changed since."""

    width: Printed  # X, mm
    height: Printed  # Y, mm
    materials: SteelMaterials
    pure_cover: Printed | None
    main_rows: tuple[ColumnMainRow, ...]
    hoops: ColumnHoops


@dataclass(frozen=True)
class ColumnBars:
    materials: SteelMaterials
    pure_cover: Printed | None  # 純かぶり
    main_rows: tuple[ColumnMainRow, ...]
    hoops: ColumnHoops
    manual_positions: tuple[ManualBar, ...]
    position_mode: str  # 基本: generated from main_rows; 指定: manual_positions
    manual_basis: ManualBasis | None


@dataclass(frozen=True)
class BeamMainRow:
    diameter: Printed | None
    material: str | None
    cover_mode: str | None
    center: Printed | None
    clear_gap: Printed | None
    face: str | None
    bar_type: str | None
    layer: int | None
    count: int | None


@dataclass(frozen=True)
class SideRow:
    diameter: Printed | None
    material: str | None
    per_face_count: int | None
    columns: int | None
    column_pitch: Printed | None
    start: Printed | None
    pitch: Printed | None
    stirrup_position: str | None
    cover_mode: str | None
    center: Printed | None


@dataclass(frozen=True)
class BandRow:
    type: str | None
    direction: str | None
    diameter: Printed | None
    material: str | None
    sets: Printed | None
    pitch: Printed | None
    start: Printed | None
    end: Printed | None
    legs_mode: str | None
    effective_legs: int | None
    width_mode: str | None  # footing only: spacing across the width by pitch or by density
    width_pitch: Printed | None
    density: Printed | None


@dataclass(frozen=True)
class BeamBars:
    materials: SteelMaterials
    pure_cover: Printed | None
    main_rows: tuple[BeamMainRow, ...]
    side_rows: tuple[SideRow, ...]
    band_rows: tuple[BandRow, ...]
    manual_positions: tuple[ManualBar, ...]
    position_mode: str


@dataclass(frozen=True)
class FootingMainRow:
    diameter: Printed | None
    material: str | None
    cover_mode: str | None
    center: Printed | None
    clear_gap: Printed | None
    direction: str | None
    face: str | None
    pitch: Printed | None
    layers: int | None
    stack_order: int | None


@dataclass(frozen=True)
class FootingBars:
    materials: SteelMaterials
    pure_cover: Printed | None
    main_rows: tuple[FootingMainRow, ...]
    side_rows: tuple[SideRow, ...]
    band_rows: tuple[BandRow, ...]
    manual_positions: tuple[ManualBar, ...]
    position_mode: str  # always 基本


@dataclass(frozen=True)
class RebarInput:
    beam: BeamBars
    column: ColumnBars
    footing: FootingBars


def _length(node: Reader, key: str, *, positive: bool = False) -> Printed | None:
    child = node.at(key)
    return None if child.is_null else child.printed(LENGTH_MM, sign="positive" if positive else "nonnegative")


def _diameter(node: Reader, key: str = "diameter_mm") -> Printed | None:
    child = node.at(key)
    return None if child.is_null else child.printed(DIAMETER, sign="positive")


def _count(node: Reader, key: str, minimum: int = 0, maximum: int = MAX_COUNT) -> int | None:
    child = node.at(key)
    return None if child.is_null else child.integer(minimum, maximum)


def _choice(node: Reader, key: str, options: tuple[str, ...]) -> str | None:
    child = node.at(key)
    return None if child.is_null else child.choice(options)


def _steel(node: Reader, key: str = "material") -> str | None:
    return _choice(node, key, choices.STEEL_GRADES)


def _ordered(node: Reader, start: Printed | None, end: Printed | None) -> None:
    if start is not None and end is not None and end.value < start.value:
        raise node.at("end_mm").error("開始位置以上が必要です")


def _materials(node: Reader) -> SteelMaterials:
    node.only("main", "transverse")
    return SteelMaterials(main=_steel(node, "main"), transverse=_steel(node, "transverse"))


COLUMN_ROW_KEYS = ("diameter_mm", "material", "cover_mode", "center_mm", "clear_gap_mm", "face_direction", "layer",
                   "per_face_count", "endpoints", "distribution")


def _column_row(node: Reader) -> ColumnMainRow:
    node.only(*COLUMN_ROW_KEYS)
    spacing = node.at("distribution").only("mode", "edge_center_mm", "pitch_mm")
    row = ColumnMainRow(
        diameter=_diameter(node), material=_steel(node), cover_mode=_choice(node, "cover_mode", choices.COVER_MODES),
        center=_length(node, "center_mm"), clear_gap=_length(node, "clear_gap_mm"),
        face_direction=_choice(node, "face_direction", choices.REBAR_DIRECTIONS),
        layer=_count(node, "layer", 1, MAX_LAYER), per_face_count=_count(node, "per_face_count"),
        endpoints=_choice(node, "endpoints", choices.ENDPOINTS),
        distribution=Distribution(mode=_choice(spacing, "mode", choices.DISTRIBUTION_MODES),
                                  edge_center=_length(spacing, "edge_center_mm"),
                                  pitch=_length(spacing, "pitch_mm", positive=True)))
    if row.distribution.mode == choices.EDGE_AND_PITCH and row.per_face_count == 1:
        raise node.at("per_face_count").error(f"{choices.EDGE_AND_PITCH}の配列は2本以上が必要です")
    return row


def _hoops(node: Reader) -> ColumnHoops:
    node.only("enclosing_diameter_mm", "direction_rows")
    rows = []
    for row in node.at("direction_rows").items():
        row.only("direction", "diameter_mm", "material", "effective_legs", "pitch_mm", "start_mm", "end_mm")
        start, end = _length(row, "start_mm"), _length(row, "end_mm")
        _ordered(row, start, end)
        rows.append(HoopRow(direction=_choice(row, "direction", choices.REBAR_DIRECTIONS), diameter=_diameter(row),
                            material=_steel(row), effective_legs=_count(row, "effective_legs", 1),
                            pitch=_length(row, "pitch_mm", positive=True), start=start, end=end))
    return ColumnHoops(enclosing_diameter=_diameter(node, "enclosing_diameter_mm"), rows=tuple(rows))


def _manual(node: Reader) -> tuple[ManualBar, ...]:
    bars = []
    for row in node.at("manual_positions").items():
        row.only("x_mm", "y_mm", "diameter_mm", "material")
        bars.append(ManualBar(x=_length(row, "x_mm"), y=_length(row, "y_mm"), diameter=_diameter(row),
                              material=_steel(row)))
    return tuple(bars)


def _basis(node: Reader | None) -> ManualBasis | None:
    if node is None:
        return None
    node.only("generator_version", "geometry", "inputs")
    node.at("generator_version").integer(BASIS_VERSION, BASIS_VERSION)
    size = node.at("geometry").only("width_mm", "height_mm")
    inputs = node.at("inputs").only("main_rows", "materials", "pure_cover_mm", "column_hoops")
    return ManualBasis(
        width=size.at("width_mm").printed(LENGTH_MM, sign="positive"),
        height=size.at("height_mm").printed(LENGTH_MM, sign="positive"),
        materials=_materials(inputs.at("materials")), pure_cover=_length(inputs, "pure_cover_mm"),
        main_rows=tuple(_column_row(row) for row in inputs.at("main_rows").items()),
        hoops=_hoops(inputs.at("column_hoops")))


def _mode(node: Reader) -> str:
    return node.at("position_mode").choice(choices.POSITION_MODES)


def _column(node: Reader) -> ColumnBars:
    node.only("materials", "concrete_strength_mpa", "pure_cover_mm", "main_rows", "column_hoops", "side_rows",
              "band_rows", "manual_positions", "position_mode", "manual_basis")
    for key in ("side_rows", "band_rows"):
        if node.at(key).items():
            raise node.at(key).error("柱では使いません（帯鉄筋は column_hoops に入力します）")
    return ColumnBars(
        materials=_materials(node.at("materials")), pure_cover=_length(node, "pure_cover_mm"),
        main_rows=tuple(_column_row(row) for row in node.at("main_rows").items()),
        hoops=_hoops(node.at("column_hoops")), manual_positions=_manual(node), position_mode=_mode(node),
        manual_basis=_basis(node.optional("manual_basis")))


def _side_row(node: Reader) -> SideRow:
    node.only("diameter_mm", "material", "per_face_count", "columns", "column_pitch_mm", "start_mm", "pitch_mm",
              "stirrup_position", "cover_mode", "center_mm")
    row = SideRow(
        diameter=_diameter(node), material=_steel(node), per_face_count=_count(node, "per_face_count"),
        columns=_count(node, "columns", 1, MAX_LAYER), column_pitch=_length(node, "column_pitch_mm", positive=True),
        start=_length(node, "start_mm"), pitch=_length(node, "pitch_mm", positive=True),
        stirrup_position=_choice(node, "stirrup_position", choices.STIRRUP_POSITIONS),
        cover_mode=_choice(node, "cover_mode", choices.COVER_MODES), center=_length(node, "center_mm"))
    if row.per_face_count and row.columns is not None and row.columns > row.per_face_count:
        raise node.at("columns").error("片面本数以下が必要です")
    return row


BAND_KEYS = ("type", "direction", "diameter_mm", "material", "sets", "pitch_mm", "start_mm", "end_mm", "legs_mode",
             "effective_legs")
WIDTH_KEYS = ("distribution_mode", "width_pitch_mm", "density_per_m")


def _band_row(node: Reader, *, footing: bool) -> BandRow:
    node.only(*BAND_KEYS, *(WIDTH_KEYS if footing else ()))
    start, end = _length(node, "start_mm"), _length(node, "end_mm")
    _ordered(node, start, end)
    sets_node = node.at("sets")
    sets = None if sets_node.is_null else sets_node.printed(SETS)
    width_mode = width_pitch = density = None
    if footing:
        width_mode = _choice(node, "distribution_mode", choices.WIDTH_MODES)
        width_pitch = _length(node, "width_pitch_mm", positive=True)
        density_node = node.at("density_per_m")
        density = None if density_node.is_null else density_node.printed(DENSITY, sign="positive")
    row = BandRow(
        type=_choice(node, "type", choices.BAND_TYPES), direction=_choice(node, "direction", choices.REBAR_DIRECTIONS),
        diameter=_diameter(node), material=_steel(node), sets=sets, pitch=_length(node, "pitch_mm", positive=True),
        start=start, end=end, legs_mode=_choice(node, "legs_mode", choices.LEGS_MODES),
        effective_legs=_count(node, "effective_legs"), width_mode=width_mode, width_pitch=width_pitch, density=density)
    if row.legs_mode == choices.LEGS_AUTOMATIC and sets is not None and not (sets.value * 2).is_integer():
        raise sets_node.error("有効脚数（1組＝2脚）が整数にならないため、有効脚数を指定してください")
    return row


SHARED_KEYS = ("materials", "concrete_strength_mpa", "pure_cover_mm", "main_rows", "side_rows", "band_rows",
               "manual_positions", "position_mode")


def _beam(node: Reader) -> BeamBars:
    node.only(*SHARED_KEYS)
    rows = []
    for row in node.at("main_rows").items():
        row.only("diameter_mm", "material", "cover_mode", "center_mm", "clear_gap_mm", "face", "bar_type", "layer",
                 "count")
        rows.append(BeamMainRow(
            diameter=_diameter(row), material=_steel(row), cover_mode=_choice(row, "cover_mode", choices.COVER_MODES),
            center=_length(row, "center_mm"), clear_gap=_length(row, "clear_gap_mm"),
            face=_choice(row, "face", choices.BEAM_FACES), bar_type=_choice(row, "bar_type", choices.BAR_TYPES),
            layer=_count(row, "layer", 1, MAX_LAYER), count=_count(row, "count")))
    return BeamBars(
        materials=_materials(node.at("materials")), pure_cover=_length(node, "pure_cover_mm"), main_rows=tuple(rows),
        side_rows=tuple(_side_row(row) for row in node.at("side_rows").items()),
        band_rows=tuple(_band_row(row, footing=False) for row in node.at("band_rows").items()),
        manual_positions=_manual(node), position_mode=_mode(node))


def _footing(node: Reader) -> FootingBars:
    node.only(*SHARED_KEYS)
    rows = []
    for row in node.at("main_rows").items():
        row.only("diameter_mm", "material", "cover_mode", "center_mm", "clear_gap_mm", "direction", "face",
                 "pitch_mm", "layers", "stack_order")
        rows.append(FootingMainRow(
            diameter=_diameter(row), material=_steel(row), cover_mode=_choice(row, "cover_mode", choices.COVER_MODES),
            center=_length(row, "center_mm"), clear_gap=_length(row, "clear_gap_mm"),
            direction=_choice(row, "direction", choices.REBAR_DIRECTIONS),
            face=_choice(row, "face", choices.BEAM_FACES), pitch=_length(row, "pitch_mm", positive=True),
            layers=_count(row, "layers", 1, MAX_LAYER), stack_order=_count(row, "stack_order", 1, MAX_LAYER)))
    mode = _mode(node)
    if mode != choices.POSITION_BASIC:
        raise node.at("position_mode").error("フーチングは方向別の芯かぶり・重ね順で配置します")
    return FootingBars(
        materials=_materials(node.at("materials")), pure_cover=_length(node, "pure_cover_mm"), main_rows=tuple(rows),
        side_rows=tuple(_side_row(row) for row in node.at("side_rows").items()),
        band_rows=tuple(_band_row(row, footing=True) for row in node.at("band_rows").items()),
        manual_positions=_manual(node), position_mode=mode)


def parse_rebar(root: Reader) -> RebarInput:
    rebar = root.at("鉄筋").only("version", "梁", "柱", "フーチング")
    rebar.at("version").integer(REBAR_VERSION, REBAR_VERSION)
    return RebarInput(beam=_beam(rebar.at("梁")), column=_column(rebar.at("柱")),
                      footing=_footing(rebar.at("フーチング")))
