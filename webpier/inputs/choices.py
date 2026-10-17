"""Choice lists owned by the program (decision 6); input JSON stores only the choice."""

from .model import BrakingRule

VEHICLES: dict[str, BrakingRule] = {
    "EA-17": BrakingRule.EA17,
    "P-16": BrakingRule.AXLE,
}

SOIL_TYPES = ("砂質土", "砂礫", "粘性土", "砂質土と粘性土の互層")

FOUNDATION_TYPES = ("直接基礎", "場所打ち杭")
SUPPORTED_FOUNDATION = "直接基礎"

CAST_IN_PLACE_CONDITIONS = ("自然泥水", "ベントナイト泥水", "気中施工", "設定しない")

BEARING_TYPES = ("固定", "可動")

CENTRIFUGAL_DIRECTIONS = ("←", "→")

SKEW_TYPES = (1, 2)

LAYER_SURFACE = "表層"
LAYER_SUPPORT = "支持層"

# 鉄筋 (rebar). The grade name is its characteristic yield strength (JIS G 3112: SD390 → 390 N/mm2).
STEEL_GRADES = ("SD295", "SD345", "SD390")
REBAR_DIRECTIONS = ("線路", "直角")
COVER_MODES = ("自動", "指定")
COVER_AUTOMATIC, COVER_SPECIFIED = COVER_MODES
ENDPOINTS = ("含む", "含めない")
ENDPOINTS_INCLUDED = ENDPOINTS[0]
DISTRIBUTION_MODES = ("等分", "中央ピッチ", "両端＋中央ピッチ")
EQUAL, CENTRE_PITCH, EDGE_AND_PITCH = DISTRIBUTION_MODES
POSITION_MODES = ("基本", "指定")
POSITION_BASIC, POSITION_MANUAL = POSITION_MODES
BEAM_FACES = ("上", "下")
BAR_TYPES = ("ループ筋", "直筋")
STIRRUP_POSITIONS = ("内側", "外側")
BAND_TYPES = ("外巻き", "内側")
LEGS_MODES = ("自動", "指定")
LEGS_AUTOMATIC = LEGS_MODES[0]
WIDTH_MODES = ("間隔", "密度")
