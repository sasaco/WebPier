"""The scalar fields of the schema 2 input: one table read by the parser and the editor (decisions 6, 17, 19, 23).

Each entry maps a path pattern to how its value is written: a number at its printed digits and unit with a sign
rule, an integer in a range, one of the program's choices, or free text; whether a blank (null) is allowed; a
range the value must lie in; and whether it is a reserved field, validated but not calculated (decision 19).
``[*]`` in a pattern stands for any list index. Rules between fields (B1 > B4+B5, the support layer, an empty
bearing slot, the foundation type that can be calculated) stay in the parser. Captions live in the editor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from ..core.printed import Precision, Printed
from ..core.reader import Reader, Sign
from . import choices

# Digits of the input sheet (.claude/docs/Example橋脚/pre/input-*.pdf).
LENGTH = Precision(3, "m")
LOAD = Precision(2, "kN")
LINE_LOAD = Precision(2, "kN/m")
RATIO = Precision(3, "")
FRICTION = Precision(2, "")
UNIT_WEIGHT = Precision(1, "kN/m3")
RADIUS = Precision(0, "m")
SPEED = Precision(0, "km/h")
ANGLE = Precision(0, "°")
FRICTION_ANGLE = Precision(1, "°")
N_VALUE = Precision(0, "")
STRESS = Precision(0, "kN/m2")
STRENGTH = Precision(1, "N/mm2")
SHEAR_FACTOR = Precision(2, "")  # γb, at most 99.99 (JRSNAP SectSafe)
AGGREGATE = Precision(1, "mm")  # Dmax, 0.1..999999 mm (JRSNAP SectConc)
SHRINKAGE = Precision(0, "×10⁻⁶")  # ε'csd of the flexural crack width (decision 48; Example2 300)
# 鉄筋 (lengths in mm)
LENGTH_MM = Precision(1, "mm")  # covers, centres, gaps, pitches, positions
DIAMETER = Precision(0, "mm")  # nominal bar size (D32 → 32), as Example2 10-6 / 11-6 print it
SETS = Precision(1, "組")  # the old band input allows a fractional set count
DENSITY = Precision(1, "本/m")

SHEAR_FACTOR_MAX = 99.99
AGGREGATE_RANGE = (0.1, 999_999)
MAX_STEPS = 100_000
MAX_COUNT = 10_000
MAX_LAYER = 100
BASIS_VERSION = 1  # generator of 鉄筋.柱.manual_basis

Kind = Literal["number", "integer", "choice", "text", "blank"]


@dataclass(frozen=True)
class Limit:
    """A range the printed value must lie in, with the message naming it."""

    test: Callable[[float], bool]
    message: str


def below(high: float, message: str) -> Limit:
    return Limit(lambda value: value < high, message)


def at_most(high: float) -> Limit:
    return Limit(lambda value: value <= high, f"{high}以下が必要です")


def within(low: float, high: float, unit: str) -> Limit:
    return Limit(lambda value: low <= value <= high, f"{low}～{high} {unit}が必要です")


@dataclass(frozen=True)
class Field:
    kind: Kind
    precision: Precision | None = None  # number
    sign: Sign = "nonnegative"  # number
    nullable: bool = False  # a blank (null) is "not entered", allowed until a stage asks for the value
    choices: tuple[str, ...] = ()  # choice
    minimum: int = 0  # integer
    maximum: int = 0  # integer
    limit: Limit | None = None  # number
    reserved: bool = False  # validated for a feature that is not calculated yet (decision 19)
    message: str = ""  # blank: why a value cannot be entered

    @property
    def unit(self) -> str:
        return self.precision.unit if self.precision is not None else ""

    def read(self, node: Reader) -> Printed | int | str | None:
        """The value at *node*, or None for an allowed blank; any other value is an input error naming the path."""
        if self.kind == "blank":
            if not node.is_null:
                raise node.error(self.message)
            return None
        if node.is_null and self.nullable:
            return None
        if self.kind == "number":
            assert self.precision is not None
            value = node.printed(self.precision, sign=self.sign)
            if self.limit is not None and not self.limit.test(value.value):
                raise node.error(self.limit.message)
            return value
        if self.kind == "integer":
            return node.integer(self.minimum, self.maximum)
        if self.kind == "choice":
            return node.choice(self.choices)
        return node.text()


def number(precision: Precision, sign: Sign = "nonnegative", *, nullable: bool = False, limit: Limit | None = None,
           reserved: bool = False) -> Field:
    return Field("number", precision, sign, nullable, limit=limit, reserved=reserved)


def integer(minimum: int, maximum: int, *, nullable: bool = False, reserved: bool = False) -> Field:
    return Field("integer", nullable=nullable, minimum=minimum, maximum=maximum, reserved=reserved)


def choice(options: Iterable[str], *, nullable: bool = False, reserved: bool = False) -> Field:
    return Field("choice", nullable=nullable, choices=tuple(options), reserved=reserved)


TEXT = Field("text")
SNOW_KEYS = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
LOAD_KEYS = ("固定死荷重_D1", "付加死荷重_D2", *SNOW_KEYS)
SIDES = ("起点側", "終点側")


def _reactions() -> dict[str, Field]:
    table = {}
    for side, end, bearings in (("起点側", "A支点", "B支点"), ("終点側", "D支点", "C支点")):
        for key in LOAD_KEYS:
            table[f"上部工反力.{side}.{end}.{key}"] = number(LOAD, "any")
        slot = f"上部工反力.{side}.{bearings}[*]"
        table[f"{slot}.支承位置"] = number(LENGTH, "any")
        for key in LOAD_KEYS:
            table[f"{slot}.{key}"] = number(LOAD, "any")
        for track in ("L1", "L2"):
            table[f"{slot}.列車分担.{track}"] = number(RATIO, "any")
        for track in ("L3", "L4"):  # decision 23: two tracks only
            table[f"{slot}.列車分担.{track}"] = Field("blank", message="3線以上は未対応です")
    return table


def _superstructure() -> dict[str, Field]:
    table = {}
    for side in SIDES:
        span = f"上部構造.{side}"
        table |= {
            f"{span}.桁長.L1": number(LENGTH), f"{span}.桁長.スパン長": number(LENGTH, "positive"),
            f"{span}.桁長.L2": number(LENGTH), f"{span}.衝撃係数_単線終局": number(RATIO),
            f"{span}.曲線半径": number(RADIUS), f"{span}.列車速度": number(SPEED),
            f"{span}.遠心作用方向": choice(choices.CENTRIFUGAL_DIRECTIONS, reserved=True),
            **{f"{span}.高さ.h{index}": number(LENGTH) for index in range(1, 5)},
            f"{span}.重心高_hs": number(LENGTH), f"{span}.支承位置_f": number(LENGTH),
        }
        support = f"上部構造.支承データ.{side}"
        table |= {f"{support}.支承名": choice(choices.BEARING_TYPES), f"{support}.摩擦係数_μ": number(FRICTION),
                  f"{support}.復旧性制動係数": number(RATIO, nullable=True)}
    train = "上部構造.列車"
    table |= {
        f"{train}.車両名": choice(choices.VEHICLES), f"{train}.1両の長さ": number(LENGTH, "positive"),
        f"{train}.軸距.a1_連結部": number(LENGTH, "positive"), f"{train}.軸距.a2": number(LENGTH),
        f"{train}.軸重.地震以外": number(LOAD, "positive"), f"{train}.軸重.地震": number(LINE_LOAD),
        f"{train}.編成数": integer(1, 200),
        **{f"{train}.車両高.{key}": number(LENGTH) for key in ("受風高", "遠心重心高", "地震重心高")},
        # decision 37: load factors must be positive
        **{f"{train}.荷重修正係数.{key}": number(RATIO, "positive") for key in ("使用性", "安全性(破壊)", "安全性(疲労)")},
    }
    return table


POSITIVE_SIZES = {"B": {1, 6, 8}, "W": {1, 6, 8}, "H": {4, 6}}


def _substructure() -> dict[str, Field]:
    table = {}
    for group, prefix, count in (("側面", "B", 9), ("正面", "W", 9), ("高さ", "H", 6)):
        for index in range(1, count + 1):
            sign = "positive" if index in POSITIVE_SIZES[prefix] else "nonnegative"
            table[f"下部構造.寸法.{group}.{prefix}{index}"] = number(LENGTH, sign)
    sub = "下部構造"
    table |= {
        f"{sub}.土かぶり.起点側_df1": number(LENGTH), f"{sub}.土かぶり.終点側_df2": number(LENGTH),
        **{f"{sub}.水位.{key}": number(LENGTH, "any") for key in ("高水位_hw1", "平水位_hw2", "低水位_hw3")},
        f"{sub}.斜角.θ": number(ANGLE, "positive", reserved=True), f"{sub}.斜角.タイプ": integer(1, 2, reserved=True),
        f"{sub}.単位体積重量.梁・躯体": number(UNIT_WEIGHT, "positive"),
        f"{sub}.単位体積重量.フーチング": number(UNIT_WEIGHT, "positive"),
        f"{sub}.単位体積重量.上載土": number(UNIT_WEIGHT),
        **{f"{sub}.単位体積重量.杭.{key}": number(UNIT_WEIGHT, nullable=True, reserved=True) for key in ("鉛直重量", "慣性力")},
        f"{sub}.杭種": choice(choices.FOUNDATION_TYPES, reserved=True),
        f"{sub}.場所打ち杭の施工条件": choice(choices.CAST_IN_PLACE_CONDITIONS, nullable=True, reserved=True),
    }
    for direction, axis in (("線路方向", "X"), ("線路直角方向", "Y")):
        row = f"{sub}.杭の配置[*].{direction}"
        table[f"{row}.{axis}"] = number(LENGTH, "any", nullable=True, reserved=True)
        table[f"{row}.本数"] = integer(0, MAX_COUNT, nullable=True, reserved=True)
    return table


def _soil() -> dict[str, Field]:
    layer = "地盤データ.層[*]"
    angle = number(FRICTION_ANGLE, nullable=True, limit=below(90, "90度未満が必要です"))
    return {
        f"{layer}.層番": TEXT, f"{layer}.層厚": number(LENGTH, nullable=True),
        f"{layer}.土質区分": choice(choices.SOIL_TYPES), f"{layer}.N値": number(N_VALUE, nullable=True),
        f"{layer}.単位体積重量.湿潤": number(UNIT_WEIGHT, nullable=True),
        f"{layer}.単位体積重量.水中": number(UNIT_WEIGHT, nullable=True),
        f"{layer}.内部摩擦角_φd": angle, f"{layer}.内部摩擦角の上限値": angle,
        f"{layer}.一軸圧縮強度_qu": number(STRESS, nullable=True),
        f"{layer}.変形係数_Ed": number(STRESS, nullable=True),
    }


def _seismic_design() -> dict[str, Field]:
    # Shared by both directions; needed only by 0711 / 0721 (decision 49).
    return {"耐震設計条件.地域別": choice(choices.REGIONS, nullable=True),
            "耐震設計条件.地盤区分": choice(choices.GROUND_CLASSES, nullable=True)}


def _column_check() -> dict[str, Field]:
    # 柱の断面照査: shared by both directions; needed only by 0611 (decision 48).
    section = "柱の断面照査"
    return {f"{section}.鋼材の腐食に対する環境条件": choice(choices.CORROSION_ENVIRONMENTS, nullable=True),
            f"{section}.外観の照査": choice(choices.APPEARANCE_CHECKS, nullable=True),
            f"{section}.ε'csd": number(SHRINKAGE, nullable=True),
            f"{section}.適用基準の機関": choice(choices.STANDARD_BODIES, nullable=True),
            f"{section}.JR-001": choice(choices.ADOPTIONS, nullable=True),
            f"{section}.JR-004": choice(choices.ADOPTIONS, nullable=True)}


def _jrsnap() -> dict[str, Field]:
    table = {}
    for direction in ("jrsnap_longitudinal", "jrsnap_transverse"):
        for key in ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd"):
            table[f"{direction}.{key}"] = number(SHEAR_FACTOR, "positive", nullable=True,
                                                 limit=at_most(SHEAR_FACTOR_MAX))
        table[f"{direction}.analysis_steps"] = integer(1, MAX_STEPS, nullable=True)
        table[f"{direction}.limited_final_step"] = integer(1, MAX_STEPS, nullable=True)
        # A magnitude: the export gives it the sign of the earthquake (decision 43).
        table[f"{direction}.target_displacement_m"] = number(LENGTH, "positive", nullable=True)
    return table


# 鉄筋: every value may stay blank while it is being entered (inputs/rebar.py).
_LENGTH_MM = number(LENGTH_MM, nullable=True)
_PITCH_MM = number(LENGTH_MM, "positive", nullable=True)
_DIAMETER = number(DIAMETER, "positive", nullable=True)
_STEEL = choice(choices.STEEL_GRADES, nullable=True)
_COUNT = integer(0, MAX_COUNT, nullable=True)
_LAYER = integer(1, MAX_LAYER, nullable=True)


def _optional_choice(options: Iterable[str]) -> Field:
    return choice(options, nullable=True)


def _main_row(member: str) -> dict[str, Field]:
    row = {"diameter_mm": _DIAMETER, "material": _STEEL, "cover_mode": _optional_choice(choices.COVER_MODES),
           "center_mm": _LENGTH_MM, "clear_gap_mm": _LENGTH_MM}
    if member == "柱":
        row |= {"face_direction": _optional_choice(choices.REBAR_DIRECTIONS), "layer": _LAYER,
                "per_face_count": _COUNT, "endpoints": _optional_choice(choices.ENDPOINTS),
                "distribution.mode": _optional_choice(choices.DISTRIBUTION_MODES),
                "distribution.edge_center_mm": _LENGTH_MM, "distribution.pitch_mm": _PITCH_MM}
    elif member == "梁":
        row |= {"face": _optional_choice(choices.BEAM_FACES), "bar_type": _optional_choice(choices.BAR_TYPES),
                "layer": _LAYER, "count": _COUNT}
    else:
        row |= {"direction": _optional_choice(choices.REBAR_DIRECTIONS), "face": _optional_choice(choices.BEAM_FACES),
                "pitch_mm": _PITCH_MM, "layers": _LAYER, "stack_order": _LAYER}
    return row


SIDE_ROW = {"diameter_mm": _DIAMETER, "material": _STEEL, "per_face_count": _COUNT, "columns": _LAYER,
            "column_pitch_mm": _PITCH_MM, "start_mm": _LENGTH_MM, "pitch_mm": _PITCH_MM,
            "stirrup_position": _optional_choice(choices.STIRRUP_POSITIONS),
            "cover_mode": _optional_choice(choices.COVER_MODES), "center_mm": _LENGTH_MM}
BAND_ROW = {"type": _optional_choice(choices.BAND_TYPES), "direction": _optional_choice(choices.REBAR_DIRECTIONS),
            "diameter_mm": _DIAMETER, "material": _STEEL, "sets": number(SETS, nullable=True), "pitch_mm": _PITCH_MM,
            "start_mm": _LENGTH_MM, "end_mm": _LENGTH_MM, "legs_mode": _optional_choice(choices.LEGS_MODES),
            "effective_legs": _COUNT}
FOOTING_BAND_ROW = BAND_ROW | {"distribution_mode": _optional_choice(choices.WIDTH_MODES), "width_pitch_mm": _PITCH_MM,
                               "density_per_m": number(DENSITY, "positive", nullable=True)}
MANUAL_ROW = {"x_mm": _LENGTH_MM, "y_mm": _LENGTH_MM, "diameter_mm": _DIAMETER, "material": _STEEL}
HOOP_ROW = {"direction": _optional_choice(choices.REBAR_DIRECTIONS), "diameter_mm": _DIAMETER, "material": _STEEL,
            "effective_legs": integer(1, MAX_COUNT, nullable=True), "pitch_mm": _PITCH_MM, "start_mm": _LENGTH_MM,
            "end_mm": _LENGTH_MM}
MEMBERS = ("梁", "柱", "フーチング")


def _prefixed(prefix: str, rows: dict[str, Field]) -> dict[str, Field]:
    return {f"{prefix}.{key}": spec for key, spec in rows.items()}


def _column_inputs(prefix: str) -> dict[str, Field]:
    """The column's basic input, also kept under manual_basis.inputs."""
    return {f"{prefix}.materials.main": _STEEL, f"{prefix}.materials.transverse": _STEEL,
            f"{prefix}.pure_cover_mm": _LENGTH_MM, **_prefixed(f"{prefix}.main_rows[*]", _main_row("柱")),
            f"{prefix}.column_hoops.enclosing_diameter_mm": _DIAMETER,
            **_prefixed(f"{prefix}.column_hoops.direction_rows[*]", HOOP_ROW)}


def _rebar() -> dict[str, Field]:
    table = {}
    for member in MEMBERS:
        base = f"鉄筋.{member}"
        table |= {f"{base}.concrete_strength_mpa": number(STRENGTH, "positive"),
                  f"{base}.position_mode": choice(choices.POSITION_MODES),
                  **_prefixed(f"{base}.manual_positions[*]", MANUAL_ROW)}
        if member == "柱":
            basis = f"{base}.manual_basis"
            table |= _column_inputs(base) | _column_inputs(f"{basis}.inputs") | {
                # Dmax: a property of the column concrete, read by 0611 and the JRSNAP export (decision 48)
                f"{base}.aggregate_max_mm": number(AGGREGATE, nullable=True, limit=within(*AGGREGATE_RANGE, "mm")),
                f"{basis}.generator_version": integer(BASIS_VERSION, BASIS_VERSION),
                f"{basis}.geometry.width_mm": number(LENGTH_MM, "positive"),
                f"{basis}.geometry.height_mm": number(LENGTH_MM, "positive")}
            continue
        table |= {f"{base}.materials.main": _STEEL, f"{base}.materials.transverse": _STEEL,
                  f"{base}.pure_cover_mm": _LENGTH_MM, **_prefixed(f"{base}.main_rows[*]", _main_row(member)),
                  **_prefixed(f"{base}.side_rows[*]", SIDE_ROW),
                  **_prefixed(f"{base}.band_rows[*]", FOOTING_BAND_ROW if member == "フーチング" else BAND_ROW)}
    return table


FIELDS: dict[str, Field] = {**_reactions(), **_superstructure(), **_substructure(), **_soil(), **_rebar(),
                            **_seismic_design(), **_column_check(), **_jrsnap()}
_INDEX = re.compile(r"\[\d+\]")


def path_text(path: tuple[str | int, ...]) -> str:
    """The path as an input error names it: 上部工反力.起点側.B支点[0].支承位置."""
    text = ""
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else part)
    return text


def pattern(path: str) -> str:
    return _INDEX.sub("[*]", path)


def field(path: str | tuple[str | int, ...]) -> Field:
    """The field at *path* (as text or as keys); KeyError for a path the schema has no scalar field at."""
    key = pattern(path if isinstance(path, str) else path_text(path))
    try:
        return FIELDS[key]
    except KeyError:
        raise KeyError(f"入力項目の定義がありません: {key}") from None


def read(node: Reader) -> Printed | int | str | None:
    """Read the scalar at *node* by its field."""
    return field(node.path).read(node)
