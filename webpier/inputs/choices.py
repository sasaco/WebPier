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
