"""The WDJ WebPier gives Capacita for the 0810 / 0820 フーチングの断面照査 of a pile foundation (decision 96, ADR-0008), in its
section force input mode as the direct footing's (``footing_wdj``): no pickup, the forces of each check in ``force`` by
Capacita's case id (Md0 耐久性 応力度 = 永久＋変動, Md1 耐久性 永久荷重, Md5 安全性 破壊, Md7 復旧性 地震時, Md8 最小鉄筋量 the
long-term Md as Md1; Vd5 with its Md; N'd 0), and a ``deep_beam`` block of Capacita's R5 deep beam shear in the ``shear``
row of the points that have it (Capacita README, shear[].deep_beam).

One member フーチング per point, because the section's width (the effective width) differs by point: the width is the
member's B and the width of the bar row; the bars are those of the input per 1 m of width, scaled to it. The tension side
of a point is its ``isLowerCalc`` / ``isUpperCalc`` and the sign of its Md (a lower tension positive, an upper tension negative); the
deep beam block takes its tension side from its ``mode``. The calculation switches print the checks only.
"""

from __future__ import annotations

from typing import Any

from ...calc.footing_rebar import MainBars
from ...calc.pile_footing import LOWER, Case
from ...calc.pile_footing_check import CheckPoint, PileFootingCheckResult
from ...core.integrity import dump_json
from .footing_wdj import LONG_TERM, MINIMUM_REBAR, POINT_ID, SAFETY, SEISMIC, SHORT_TERM, _basic, _crack, _safety
from .wdj import GROUP, RECTANGLE, SCHEMA, VERSION, _number

DEEP_BEAM_THETA = 45  # the angle of the diagonal cracks, degrees


def _main(bars: MainBars, title: str) -> dict[str, Any]:
    layered = len(bars.counts) > 1
    return {"title": title, "rebar_dia": _number(bars.diameter), "rebar_n": _number(bars.count),
            "rebar_cover": _number(bars.cover), "rebar_lines": _number(bars.counts[0]) if layered else None,
            "rebar_space": _number(bars.layer_spacing), "rebar_ss": _number(bars.pitch), "cos": None, "enable": True}


def _point(item: CheckPoint) -> dict[str, Any]:
    lower = item.point.tension == LOWER
    return {"index": item.index, "m_no": item.index, "position": 0, "p_name": item.point.name, "p_id": POINT_ID,
            "isMyCalc": False, "isVyCalc": item.point.deep_beam is not None, "isMzCalc": item.point.bending,
            "isVzCalc": False, "isMtCalc": False, "axis_type": 2, "isUpperCalc": not lower, "isLowerCalc": lower}


def _bar(check: PileFootingCheckResult, item: CheckPoint) -> dict[str, Any]:
    none = {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None}
    return {
        "index": item.index, "m_no": item.index, "haunch_M": None, "haunch_V": None,
        "rebar1": _main(item.upper, "上側"), "rebar2": _main(item.lower, "下側"),
        "sidebar1": dict(none), "sidebar2": dict(none),
        "stirrup": {"stirrup_dia": _number(check.stirrups.diameter), "stirrup_n": 1,
                    "stirrup_ss": _number(check.stirrups.pitch)},
        "bend": {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None},
        "tan": None, "g_name": None, "p_name": item.point.name, "b": _number(item.point.width.be),
        "h": _number(item.point.height),
    }


def _shear(check: PileFootingCheckResult, item: CheckPoint) -> dict[str, Any]:
    row: dict[str, Any] = {"index": item.index, "p_name": item.point.name, "m_no": item.index, "g_name": check.member,
                           "La": None, "fixed_end": False, "L": None}
    if item.point.deep_beam == "lower_tension":
        row["deep_beam"] = {"mode": "lower_tension", "a1_mm": _number(item.point.a1),
                            "pile_diameter_mm": _number(item.point.pile_diameter),
                            "stirrup_b1_mm": _number(check.stirrup_spacing)}
    elif item.point.deep_beam == "upper_tension":
        row["deep_beam"] = {"mode": "upper_tension", "stirrup_count_in_range": item.point.stirrup_count,
                            "theta_deg": DEEP_BEAM_THETA}
    return row


def _moment(id_: int, md) -> dict[str, Any]:
    return {f"Md{id_}_Md": _number(md), f"Md{id_}_Nd": 0}


def _force(item: CheckPoint) -> dict[str, Any]:
    row: dict[str, Any] = {"index": item.index}
    forces = item.forces
    if item.point.bending:
        row.update({**_moment(SHORT_TERM, forces.force(Case.SHORT_TERM).md),
                    **_moment(LONG_TERM, forces.force(Case.LONG_TERM).md),
                    **_moment(SAFETY, forces.force(Case.SAFETY).md), **_moment(SEISMIC, forces.force(Case.SEISMIC).md),
                    **_moment(MINIMUM_REBAR, forces.force(Case.LONG_TERM).md)})
    if item.point.deep_beam is not None:
        safety = forces.force(Case.SAFETY)
        row.update({f"Vd{SAFETY}_Vd": _number(safety.vd), f"Vd{SAFETY}_Md": _number(safety.vd_md), f"Vd{SAFETY}_Nd": 0})
    return row


def build_pile_footing_wdj(check: PileFootingCheckResult) -> dict[str, Any]:
    """The WDJ of the footing check of one direction, as a JSON document."""
    points = check.points
    return {
        "$schema": SCHEMA, "format": "wdj", "schema_version": VERSION, "ver": VERSION, "lang": "ja",
        "pickup_filename": "", "pickup_data": None,
        "basic": _basic(check),
        "members": [{"m_no": item.index, "m_len": None, "g_no": int(GROUP), "g_id": GROUP, "g_name": check.member,
                     "shape": RECTANGLE, "B": _number(item.point.width.be), "H": _number(item.point.height), "Bt": None,
                     "t": None, "n": 1} for item in points],
        "crack": [_crack(check, item.index, item.point.name) for item in points],
        "points": [_point(item) for item in points],
        "bar": [_bar(check, item) for item in points],
        "shear": [_shear(check, item) for item in points],
        "fatigues": {"fatigue_list": [], "train_A_count": None, "train_B_count": None, "service_life": None},
        "safety": _safety(check),
        "force": [_force(item) for item in points],
        "calc": {"print_calculate_checked": True, "print_section_force_checked": False,
                 "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                 "calculate_moment_checked": True, "calculate_shear_force": True,
                 "calculate_torsional_moment": False, "member_group_selection": []},
    }


def write_pile_footing_wdj(document: dict[str, Any]) -> bytes:
    """The bytes of the WDJ: UTF-8 JSON, as every JSON WebPier writes (core.integrity.dump_json)."""
    return dump_json(document)
