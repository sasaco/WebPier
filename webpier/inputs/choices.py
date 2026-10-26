"""Choice lists owned by the program (decision 6); input JSON stores only the choice."""

from .model import BrakingRule

VEHICLES: dict[str, BrakingRule] = {
    "EA-17": BrakingRule.EA17,
    "P-16": BrakingRule.AXLE,
}

SOIL_TYPES = ("砂質土", "砂礫", "粘性土", "砂質土と粘性土の互層")

# 基礎形式 (decision 80): the pile foundations are put into SOIL-JR (ADR-0013), whose pile types and construction methods
# these are; others can be added as choices.
DIRECT_FOUNDATION = "直接基礎"
CAST_IN_PLACE_PILE = "場所打ち杭"
STEEL_SOIL_CEMENT_PILE = "鋼管ソイルセメント杭"
PILE_FOUNDATIONS = (CAST_IN_PLACE_PILE, STEEL_SOIL_CEMENT_PILE)
FOUNDATION_TYPES = (DIRECT_FOUNDATION, *PILE_FOUNDATIONS)

# 場所打ち杭の施工条件: SOIL-JR's K_SJYOUKEN 1 and 2
CAST_IN_PLACE_CONDITIONS = ("自然泥水", "安定液使用")
# 鋼管の材質（JIS G 3444）: the design strengths of each are the calculation's (calc.pile_body)
STEEL_PIPE_GRADES = ("SKK400", "SKK490")
# 杭の配置: 千鳥配置 has piles only where the sum of the column numbers is even (CONTEXT.md 千鳥配置)
PILE_ARRANGEMENTS = ("格子", "千鳥")
GRID, STAGGERED = PILE_ARRANGEMENTS

BEARING_TYPES = ("固定", "可動")

CENTRIFUGAL_DIRECTIONS = ("←", "→")

SKEW_TYPES = (1, 2)

# 耐震設計条件 (decision 49): Aggre-SE's 地域別 and 地盤区分; its 応答塑性率の直接入力 needs a μ the XML cannot hold.
REGIONS = ("A地域", "B地域", "C地域")
GROUND_CLASSES = ("G0地盤", "G1地盤", "G2地盤", "G3地盤", "G4地盤", "G5地盤")
# the 液状化指数 PL's range (decision 95): Aggre-SE's _rbEkijo, which the design earthquake of its liquefaction Cases depends on
LIQUEFACTION_INDEXES = ("5<PL<20", "20<PL")

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
BEAM_FACES = ("上", "下")
BAR_TYPES = ("ループ筋", "直筋")
STIRRUP_POSITIONS = ("内側", "外側")
WIDTH_MODES = ("間隔", "密度")
WIDTH_SPACING, WIDTH_DENSITY = WIDTH_MODES

# 柱の断面照査 (decision 48): one set for the column, shared by both directions.
WATER_EXPOSURES = ("常時乾燥", "乾湿繰返し", "常時湿潤")  # 水掛かりの程度 (RC標準 R5; Capacita con 1, 2, 3)
APPEARANCE_CHECKS = ("行う", "行わない")  # 外観の照査
APPEARANCE_CHECKED = APPEARANCE_CHECKS[0]
STANDARD_BODIES = ("運輸機構", "JR各社", "JR東日本")  # 適用基準の機関
ADOPTIONS = ("適用する", "適用しない")  # JR-001, JR-004
ADOPTED = ADOPTIONS[0]
