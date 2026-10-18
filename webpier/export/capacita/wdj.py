"""The WDJ WebPier gives Capacita for the 0611 柱の断面照査 (decision 48, ADR-0008), without its pickup data.

The document follows the RC document Capacita writes itself (WebDanforCS ProjectDocument.Create and
DocumentEditor.InitializeInputFields): ``$schema`` / ``format`` wdj, the basic lists, one member, one point, one bar
row, one crack row, the safety tables of group 1 and the calculation switches. It holds no pickup data: Capacita's
Headless imports the PIK of the same generation with ``run-rc --pickup`` (the GUI's 断面力データ取込), which keeps
the member and the point written here and adds the others of the PIK (WebPier never reads the PIK).

The point is identified as that import compares it: the FEMPython PIK lists every member of the frame in member
order with its ITAN (0) and JTAN (the member length) points, so the J end of member m is point 2m with ``p_id``
JTAN at the column length. A WDJ the import cannot match fails the runner and stops the generation. The bar row has
no ``position`` (the import would compare it with the point's), and the document no ``steel`` rows (an RC WDJ with
them is refused).

Only the column bottom is checked (bending about z, shear in y; no torsion). ``shape`` is the number 1 (rectangle;
RcDan does not read "矩形"). The section force list is printed: 0611 inserts it as 8.5.
"""

from __future__ import annotations

from typing import Any

from ...calc.column_check import ColumnCheckResult, SafetyFactors
from ...core.integrity import dump_json
from ...core.printed import Printed

SCHEMA = "urn:webdan:wdj:1.0.0"
VERSION = "1.0.0"
GROUP = "1"  # the one member group: the column
RECTANGLE = 1
J_END = "JTAN"
# specification2 of RcDan (OrganizedInput): the H16 base of each body
STANDARDS = ((0, "H16_Rail"), (1, "H16_Shinkansen"), (2, "H16_JREast"), (3, "R5_Rail"), (4, "R5_Shinkansen"),
             (8, "R5_JREast"))
BODIES = {"JR各社": 0, "運輸機構": 1, "JR東日本": 2}
# Capacita's row titles (DocumentEditor.PickupDefaults); the ids and the extraction cases are calc.column_check's.
_MOMENT_TITLES = ("耐久性 応力度", "耐久性 永久荷重", "安全性 疲労限", "安全性 永久作用", "安全性 永久＋変動", "安全性 破壊",
                  "復旧性 地震時以外", "復旧性 地震時", "最小鉄筋量")
_SHEAR_TITLES = ("耐久性 ひび割れ判定", "耐久性 永久荷重", "耐久性 変動荷重", *_MOMENT_TITLES[3:8])
_TORSION_TITLES = {0: "耐久性 ひび割れ判定", 1: "耐久性 永久荷重", 5: "安全性 破壊", 6: "復旧性 地震時以外", 7: "復旧性 地震時"}
_CONDITIONS = (("JR-001", "ひび割れ幅制限値に用いるかぶりは 100mm を上限とする", "jr001"),
               ("JR-004", "せん断耐力におけるβn算定時の Mud は軸力を考慮しない", "jr004"))
_PILE_FACTORS = (("pile-000", "使用しない", 1.0, 1.0, 1.0, 1.0),)  # the column is not a pile
_SEPARATE = (25, 29)  # Capacita's two diameter ranges of material_bar


def _number(value: Printed | None) -> int | float | None:
    """A printed number for JSON; a whole number as an integer (RcDan reads b, h, bar sizes and ε'csd as int)."""
    if value is None:
        return None
    return int(value.value) if float(value.value).is_integer() else value.value


def point_index(member: int) -> int:
    """The index of the J end of *member* in the FEMPython PIK (ITAN and JTAN of each member, in member order)."""
    return 2 * member


def _cases(cases, titles) -> list[dict[str, Any]]:
    return [{"id": id_, "title": titles[id_], "no": number} for id_, number in cases]


def _basic(check: ColumnCheckResult) -> dict[str, Any]:
    selected = BODIES[check.body]
    return {
        "specification1_list": [{"id": 0, "title": "Rail", "selected": True},
                                {"id": 3, "title": "Bangladesh", "selected": False}],
        "specification2_list": [{"id": id_, "title": title, "selected": id_ == selected} for id_, title in STANDARDS],
        "pickup_moment": _cases(check.moment_cases, _MOMENT_TITLES),
        "pickup_shear_force": _cases(check.shear_cases, _SHEAR_TITLES),
        "pickup_torsional_moment": _cases(check.torsion_cases, _TORSION_TITLES),
        "conditions_list": [{"id": id_, "title": title, "selected": getattr(check, name)}
                            for id_, title, name in _CONDITIONS],
    }


def _main(bars, title: str) -> dict[str, Any]:
    return {"title": title, "rebar_dia": _number(bars.diameter), "rebar_n": bars.count,
            "rebar_cover": _number(bars.cover),
            "rebar_lines": bars.per_layer if bars.layers > 1 else None, "rebar_space": _number(bars.layer_spacing),
            "rebar_ss": _number(bars.spacing), "cos": None, "enable": True}


def _bar(check: ColumnCheckResult, index: int) -> dict[str, Any]:
    side = check.side
    return {
        "index": index, "m_no": check.member, "haunch_M": None, "haunch_V": None,
        "rebar1": _main(check.upper, "上側"), "rebar2": _main(check.lower, "下側"),
        "sidebar1": {"side_dia": None if side is None else _number(side.diameter),
                     "side_n": None if side is None else side.count,
                     "side_cover": None if side is None else _number(side.first),
                     "side_ss": None if side is None else _number(side.spacing)},
        "sidebar2": {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None},
        "stirrup": {"stirrup_dia": _number(check.hoops.diameter), "stirrup_n": check.hoops.legs,
                    "stirrup_ss": _number(check.hoops.pitch)},
        "bend": {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None},
        "tan": None, "g_name": None, "p_name": None, "b": _number(check.width), "h": _number(check.depth),
    }


def _safety_row(factors: SafetyFactors) -> dict[str, Any]:
    return {"id": factors.id, "title": factors.title, "M_rc": _number(factors.m_rc), "M_rs": _number(factors.m_rs),
            "M_rbs": _number(factors.m_rbs), "V_rc": _number(factors.v_rc), "V_rs": _number(factors.v_rs),
            "V_rbc": _number(factors.v_rbc), "V_rbs": _number(factors.v_rbs), "V_rbv": _number(factors.v_rbv),
            "T_rbt": _number(factors.t_rbt), "ri": _number(factors.ri), "range": factors.range}


def _strengths(steel) -> dict[str, float] | None:
    return None if steel is None else {"fsy": _number(steel.fsy), "fsu": _number(steel.fsu)}


def _safety(check: ColumnCheckResult) -> dict[str, Any]:
    side = check.side_steel or check.main_steel  # without side bars Capacita still reads the row
    bars = {"tensionBar": _strengths(check.main_steel), "sidebar": _strengths(side),
            "stirrup": _strengths(check.hoop_steel)}
    return {
        "safety_factor": {GROUP: [_safety_row(factors) for factors in check.safety]},
        "material_bar": {GROUP: [{"separate": separate, **bars} for separate in _SEPARATE]},
        "material_concrete": {GROUP: {"fck": _number(check.fck), "dmax": _number(check.aggregate_max)}},
        "pile_factor": {GROUP: [{"id": id_, "title": title, "rfck": rfck, "rfbok": rfbok, "rEc": rec, "rVcd": rvcd,
                                 "selected": True} for id_, title, rfck, rfbok, rec, rvcd in _PILE_FACTORS]},
    }


def build_wdj(check: ColumnCheckResult) -> dict[str, Any]:
    """The WDJ of the column bottom check, as a JSON document."""
    index = point_index(check.member)
    environment = check.environment_number
    return {
        "$schema": SCHEMA, "format": "wdj", "schema_version": VERSION, "ver": VERSION, "lang": "ja",
        "pickup_filename": "", "pickup_data": None,
        "basic": _basic(check),
        "members": [{"m_no": check.member, "m_len": _number(check.length), "g_no": int(GROUP), "g_id": GROUP,
                     "g_name": "柱", "shape": RECTANGLE, "B": _number(check.width), "H": _number(check.depth),
                     "Bt": None,
                     "t": None, "n": 1}],
        "crack": [{"index": index, "m_no": check.member, "p_name": None, "con_u": environment, "con_l": environment,
                   "con_s": environment, "vis_u": check.appearance, "vis_l": check.appearance,
                   "ecsd_u": _number(check.ecsd), "ecsd_l": _number(check.ecsd), "kr": _number(check.kr),
                   "k4": _number(check.k4)}],
        "points": [{"index": index, "m_no": check.member, "position": _number(check.length), "p_name": None,
                    "p_id": J_END, "isMyCalc": False, "isVyCalc": True, "isMzCalc": True, "isVzCalc": False,
                    "isMtCalc": False, "axis_type": 2, "isUpperCalc": True, "isLowerCalc": True}],
        "bar": [_bar(check, index)],
        "shear": [],
        "fatigues": {"fatigue_list": [], "train_A_count": None, "train_B_count": None, "service_life": None},
        "safety": _safety(check),
        "force": [],
        "calc": {"print_calculate_checked": True, "print_section_force_checked": True,
                 "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                 "calculate_moment_checked": True, "calculate_shear_force": True,
                 "calculate_torsional_moment": False, "member_group_selection": []},
    }


def write_wdj(document: dict[str, Any]) -> bytes:
    """The bytes of the WDJ: UTF-8 JSON, as every JSON WebPier writes (core.integrity.dump_json)."""
    return dump_json(document)
