"""Project XML bytes as Aggre-SE itself saves them (decision 49).

Aggre-SE serializes its ``Datas`` with XmlSerializer to a string (hence the declared utf-16) and writes that string
with a Shift-JIS StreamWriter: CRLF, two-space indentation, no BOM, no newline after the root. The element order,
the array lengths (``Option_ケース数`` = 50 Cases) and ``Version`` are those of the Aggre-SE this follows
(structural-mcp ``Batch``, Batch.exe 5.3.0.1); when it changes, this follows it. A number is written as XmlSerializer
writes it (7600, 1.5, 0.000 for a formatted text). An unencodable character is an error, never replaced.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from .project import AnchorBar, Project

BATCH_VERSION = "5.3.0.1"  # Batch.exe (Aggre-SE) FileVersion, which it writes as Version
CASES = 50  # Option_ケース数: the length of every per-Case array
ENCODING = "cp932"
NEWLINE = "\r\n"
NIL = None  # an array item written as xsi:nil

# WebPier's conditions, those of the Example2 projects (P1_線路.xml, P1_直角.xml); the check items ①..⑨ of each Case
# are those of its 照査パターン (project.CHECKS, decision 76):
CHECK_ITEMS = 9  # dgCaseList_1..9
PILE_TYPE = 4  # 部材照査タイプ of each section of the piles: 杭
MEMBER_TYPE = 2  # 部材照査タイプ of the one nonlinear member: 柱
SHEAR_FORMULA = 1  # せん断耐力の算定式 ① 標準せん断耐力【RC標準】
SUPPORT = -1  # 端部支持条件: none (an M-θ member)
TYPE_TITLES = ("梁", "柱", NIL, "杭", NIL)  # 部材照査タイプ 1..5
DAMAGE_RECOVERY = (2, 2, 0, 2, 0)  # 損傷レベルの制限値 of each type: 復旧性
DAMAGE_SAFETY = (2, 3, 0, 2, 0)  # and 安全性
DIRECT_FOUNDATION = 1  # 基礎形式 (0 杭基礎)
PILE_FOUNDATION = 0
DISPLACEMENT_POINTS = 30  # dgDispAtPoints: the rows of the 変位照査位置 table (杭基礎)
PILE_LIMITS, DIRECT_LIMITS = 31, 11  # 制限値, blank: Aggre-SE calculates them
SPECTRUM = (True, False, False)  # スペクトルⅠ,Ⅱ 両方 / Ⅰ / Ⅱ
LIQUEFACTION = (True, False)  # 液状化指数 5<PL<20 / 20<PL
GROUND_SLOTS = 10  # _rbJIban: G0..G5, unused, 応答塑性率の直接入力 (9)
PRODUCT = (False, True)  # 帳票: 標準仕様 / カスタム仕様

Node = tuple[str, "str | list[Node] | None"]  # (tag, text | children | empty element)


def _number(value: Decimal) -> str:
    """As XmlSerializer writes a Single: 7600, 7600.5 (a printed value, so no exponent)."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _array(item: str, values: Sequence[object]) -> list[Node]:
    def text(value: object) -> str | None:
        if value is NIL:
            return NIL
        if isinstance(value, bool):
            return "true" if value else "false"
        return _number(value) if isinstance(value, Decimal) else str(value)
    return [(item, text(value)) for value in values]


def _cases(values: Sequence[object], fill: object) -> list[object]:
    return [*values, *([fill] * (CASES - len(values)))]


def _one_hot(index: int, size: int) -> list[bool]:
    return [slot == index for slot in range(size)]


def _point(joint: int) -> list[Node]:
    return [("_Direction", "0"), ("pointNo", str(joint)), ("Direction", "0.000")]


def _foundation(project: Project) -> list[Node]:
    """The 基礎照査 of the project: the direct foundation checked at its joint, or the piles whose limit values the runner reads
    from the .sdr (decision 94): the reaction at the head of each pile row and the displacement at the footing top."""
    limits0 = ("dgLimitValue0", _array("string", [NIL] * PILE_LIMITS))
    limits1 = ("dgLimitValue1", _array("string", [NIL] * DIRECT_LIMITS))
    if not project.piled:
        return [("sdtFilePath", None), ("dgReactAtPoint", [("clsAtPoints", _point(project.footing_joint))]),
                ("dgDispAtPoint", _point(project.footing_joint)), ("dgDispAtPoints", None), limits0, limits1,
                ("FoundationType", str(DIRECT_FOUNDATION))]
    reactions = [("clsAtPoints", [("_Direction", str(row.piles)), ("pointNo", str(row.head)),
                                  ("Direction", f"{row.piles}.000")]) for row in project.pile_rows]
    displaced = [("clsAtPoints", [("_Direction", "0"), ("pointNo", str(project.footing_joint) if index == 0 else None),
                                  ("Direction", "0.000")]) for index in range(DISPLACEMENT_POINTS)]
    return [("sdtFilePath", None), ("dgReactAtPoint", reactions),
            ("dgDispAtPoint", [("_Direction", "0"), ("pointNo", None), ("Direction", "0.000")]),
            ("dgDispAtPoints", displaced), limits0, limits1, ("FoundationType", str(PILE_FOUNDATION))]


_ANCHOR_BARS = ("D1", "n1", "D2", "Aw", "Ss")
_ANCHOR_LENGTHS = ("PileHeadLength", "ParagraphLength", "ConcreteStrength", "ReductionCoefficient", "PileMidLength",
                   "DesignMarginLength", "DisabledFromPileHead", "DisabledUpwardFromCutOffPoint",
                   "DisabledDownwardFromCutOffPoint")


def _pile_anchor_bar(anchor: AnchorBar | None) -> list[Node]:
    """The 段落し情報: Aggre-SE's initial values (no pile, or a pile without a cut-off), or those of *anchor* (decision 98).
    XmlSerializer writes each value twice, the field (``_D1``) and the text property (``D1``) whose setter sets the field
    again when it is read back, so both are written alike (an empty property would set it to 0)."""
    if anchor is None:
        texts = {name: None for name in (*_ANCHOR_BARS, *_ANCHOR_LENGTHS)}
        rows: list[Node] = [("dgMemberFirst", None), ("dgMemberLast", None), ("dgMemberNumber", None)]
        moment = shear = "1.5"
    else:
        numbers = (anchor.main_diameter, Decimal(anchor.main_count), anchor.hoop_diameter, Decimal(anchor.hoop_sets),
                   anchor.hoop_pitch, anchor.head_anchorage, anchor.cutoff_length, anchor.concrete_strength,
                   anchor.joint_reduction, anchor.cutoff_anchorage, anchor.margin, anchor.no_joint_head,
                   anchor.no_joint_above, anchor.no_joint_below)
        texts = {name: _number(value) for name, value in zip((*_ANCHOR_BARS, *_ANCHOR_LENGTHS), numbers)}
        rows = [("dgMemberFirst", _array("int", [first for first, _, _ in anchor.rows])),
                ("dgMemberLast", _array("int", [last for _, last, _ in anchor.rows])),
                ("dgMemberNumber", _array("float", [Decimal(piles) for _, _, piles in anchor.rows]))]
        moment, shear = _number(anchor.margin_moment), _number(anchor.margin_shear)
    values: list[Node] = [(f"_{name}", texts[name] or "0") for name in _ANCHOR_BARS]
    values += rows
    values += [(f"_{name}", texts[name] or "0") for name in _ANCHOR_LENGTHS]
    values += [("MudCoefficient", moment), ("VudCoefficient", shear)]
    values += [(name, texts[name]) for name in (*_ANCHOR_BARS, *_ANCHOR_LENGTHS)]
    return [("段落し情報", [("clsPileAnchorBar", values)])]


def document(project: Project, databases: Sequence[str]) -> list[Node]:
    """The children of ``Datas``: the project with the DB1 of each Case (paths from the XML)."""
    if len(databases) != len(project.cases):
        raise ValueError(f"DB1 が{len(databases)}件です（Case は{len(project.cases)}件）")
    case_name = [(f"dgCaseList_{item + 1}",
                  _array("int", _cases([-1 if checks[item] else 0 for checks in project.cases], 0)))
                 for item in range(CHECK_ITEMS)]
    case_name.append(("analysisObject", _array("string", _cases([], NIL))))
    # the nonlinear members: the column, then (of piles) each section of the piles, which has no shear span of its own
    piles = project.pile_sections
    element = [("_dgLimitLevel_SIJI", _array("int", [SUPPORT] * (1 + piles))),
               ("_dgLimitLevel_type", _array("int", [MEMBER_TYPE, *[PILE_TYPE] * piles])),
               ("_dgLimitLevel_La", _array("float", [Decimal(repr(project.shear_span.value)), *[Decimal(0)] * piles])),
               ("_dgLimitLevel_VydType", _array("int", [SHEAR_FORMULA] * (1 + piles))),
               ("dgLimitLevel_title", _array("string", TYPE_TITLES)),
               ("_dgLimitLevel", _array("int", DAMAGE_RECOVERY)), ("_dgLimitLevel2", _array("int", DAMAGE_SAFETY)),
               ("dgLimitLevel_typeCount", str(1 + piles))]
    foundation = _foundation(project)
    # a Case for the liquefaction is one of the L2 earthquake, for each spectrum the project checks (_rbSpec): I and II (decision 95)
    flagged = [-1 if index in project.liquefaction_cases else 0 for index in range(CASES)]
    requirement = [("_AtPoint", str(project.focus_joint)), ("_rbSpec", _array("boolean", SPECTRUM)),
                   ("_rbChiiki", _array("boolean", _one_hot(project.region, 3))),
                   ("_rbJIban", _array("boolean", _one_hot(project.ground_class, GROUND_SLOTS))),
                   ("_rbEkijo", _array("boolean", _one_hot(project.liquefaction_index, 2)
                                       if project.liquefaction_cases else LIQUEFACTION)),
                   ("dgEkijoCase1", _array("int", _cases([], 0))), ("dgEkijoCase21", _array("int", flagged)),
                   ("dgEkijoCase2", _array("int", flagged)),
                   ("cbM65Area", "0"), ("_tbAlfa", "1"), ("_cbηx", "false"), ("_tbηxL1", "1"), ("_tbηxL2", "1"),
                   ("tbηxL1", None), ("tbηxL2", None), ("tbAlfa", "1.000"), ("AtPoint", str(project.focus_joint))]
    return [("cmd", "-1"), ("Version", BATCH_VERSION), ("CaseName", case_name),
            ("SNAP", [("SnapDBPath", _array("string", _cases(list(databases), NIL)))]),
            ("Element", element), ("Foundation", [("基礎照査", [("clsFoundation", foundation)])]),
            ("Requirement", requirement), ("Calculation", [("_rbProduct", _array("boolean", PRODUCT))]),
            ("PileAnchorBar", _pile_anchor_bar(project.anchor_bar))]


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _lines(node: Node, depth: int) -> list[str]:
    tag, value = node
    indent = "  " * depth
    if value is None:  # a nil item of a string array, or an empty element
        return [f'{indent}<{tag} xsi:nil="true" />' if tag == "string" else f"{indent}<{tag} />"]
    if isinstance(value, str):
        return [f"{indent}<{tag}>{_escape(value)}</{tag}>"]
    return [f"{indent}<{tag}>", *(line for child in value for line in _lines(child, depth + 1)), f"{indent}</{tag}>"]


def write_project(project: Project, databases: Sequence[str]) -> bytes:
    """The project XML of *project* reading the DB1 *databases* (one per Case, paths from the XML)."""
    lines = ['<?xml version="1.0" encoding="utf-16"?>',
             '<Datas xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
             *(line for node in document(project, databases) for line in _lines(node, 1)), "</Datas>"]
    return NEWLINE.join(lines).encode(ENCODING, errors="strict")
