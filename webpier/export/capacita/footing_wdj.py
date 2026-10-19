"""The WDJ WebPier gives Capacita for the 0810 / 0820 フーチングの断面照査 (decision 60, ADR-0008), in its section
force input mode: no pickup (``pickup_filename`` empty), the forces of each check written in ``force`` by Capacita's
case id (DocumentEditor.PickupDefaults: Md0 耐久性 応力度, Md1 耐久性 永久荷重, Md5 安全性 破壊, Md7 復旧性 地震時;
Vd5, Vd7 with their Md; N′d 0) and the shear span La of each point in ``shear`` (mm). The runner is called without
``--pickup`` (pipeline.capacita.check_footing) and returns the report only.

One member フーチング (1 m of width by H6, shape 1) and two points per direction, because Capacita keeps one La per
point: index 1, the direction's name, carries the 安全性 and 耐久性 forces with the safety La; index 2, the name with
（地震時）, the 復旧性（地震時） forces with the seismic La. Each section of the report then prints the point that has
its forces (tried on the real runner, 2026-10-19). The bar rows have the lower bars as the tensile side (rebar2) and
no upper or side bars, the crack rows no appearance check (vis false), and the calculation switches print the checks
only (the section force list belongs to the pickup mode). The basic lists name the cases with no pickup numbers.
"""

from __future__ import annotations

from typing import Any

from ...calc.footing_check import FootingCheckResult, Forces
from ...core.integrity import dump_json
from .wdj import (_CONDITIONS, _MOMENT_TITLES, _PILE_FACTORS, _SEPARATE, _SHEAR_TITLES, _TORSION_TITLES, BODIES, GROUP,
                  RECTANGLE, SCHEMA, STANDARDS, VERSION, _number, _safety_row, _strengths)

POINT_ID = "ITAN"
SEISMIC_SUFFIX = "（地震時）"
# Capacita's case ids the footing's forces are given as (the titles of _MOMENT_TITLES / _SHEAR_TITLES).
SHORT_TERM, LONG_TERM, SAFETY, SEISMIC = 0, 1, 5, 7


def _cases(titles) -> list[dict[str, Any]]:
    ids = sorted(titles) if isinstance(titles, dict) else range(len(titles))
    return [{"id": id_, "title": titles[id_], "no": None} for id_ in ids]


def _basic(check: FootingCheckResult) -> dict[str, Any]:
    selected = BODIES[check.body]
    return {
        "specification1_list": [{"id": 0, "title": "Rail", "selected": True},
                                {"id": 3, "title": "Bangladesh", "selected": False}],
        "specification2_list": [{"id": id_, "title": title, "selected": id_ == selected} for id_, title in STANDARDS],
        "pickup_moment": _cases(_MOMENT_TITLES),
        "pickup_shear_force": _cases(_SHEAR_TITLES),
        "pickup_torsional_moment": _cases(_TORSION_TITLES),
        "conditions_list": [{"id": id_, "title": title, "selected": getattr(check, name)}
                            for id_, title, name in _CONDITIONS],
    }


def _main(bars, title: str) -> dict[str, Any]:
    if bars is None:
        return {"title": title, "rebar_dia": None, "rebar_n": None, "rebar_cover": None, "rebar_lines": None,
                "rebar_space": None, "rebar_ss": None, "cos": None, "enable": True}
    return {"title": title, "rebar_dia": _number(bars.diameter), "rebar_n": bars.count,
            "rebar_cover": _number(bars.cover), "rebar_lines": None, "rebar_space": None,
            "rebar_ss": _number(bars.pitch), "cos": None, "enable": True}


def _point(index: int, name: str) -> dict[str, Any]:
    return {"index": index, "m_no": 1, "position": 0, "p_name": name, "p_id": POINT_ID, "isMyCalc": False,
            "isVyCalc": True, "isMzCalc": True, "isVzCalc": False, "isMtCalc": False, "axis_type": 2,
            "isUpperCalc": True, "isLowerCalc": True}


def _bar(check: FootingCheckResult, index: int, name: str) -> dict[str, Any]:
    none = {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None}
    return {
        "index": index, "m_no": 1, "haunch_M": None, "haunch_V": None,
        "rebar1": _main(None, "上側"), "rebar2": _main(check.bars, "下側"),
        "sidebar1": dict(none), "sidebar2": dict(none),
        "stirrup": {"stirrup_dia": _number(check.stirrups.diameter), "stirrup_n": check.stirrups.legs,
                    "stirrup_ss": _number(check.stirrups.pitch)},
        "bend": {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None},
        "tan": None, "g_name": None, "p_name": name, "b": _number(check.width), "h": _number(check.depth),
    }


def _crack(check: FootingCheckResult, index: int, name: str) -> dict[str, Any]:
    environment = check.environment_number
    return {"index": index, "m_no": 1, "p_name": name, "con_u": environment, "con_l": environment,
            "con_s": environment, "vis_u": False, "vis_l": False, "ecsd_u": _number(check.ecsd),
            "ecsd_l": _number(check.ecsd), "kr": _number(check.kr), "k4": _number(check.k4)}


def _shear(check: FootingCheckResult, index: int, name: str, forces: Forces) -> dict[str, Any]:
    return {"index": index, "p_name": name, "m_no": 1, "g_name": check.member, "La": _number(forces.la),
            "fixed_end": False, "L": None}


def _moment(id_: int, forces: Forces) -> dict[str, Any]:
    return {f"Md{id_}_Md": _number(forces.md), f"Md{id_}_Nd": 0}


def _shear_force(id_: int, forces: Forces) -> dict[str, Any]:
    return {f"Vd{id_}_Vd": _number(forces.vd), f"Vd{id_}_Md": _number(forces.md), f"Vd{id_}_Nd": 0}


def _force(check: FootingCheckResult) -> list[dict[str, Any]]:
    return [{"index": 1, **_moment(SHORT_TERM, check.durability_short), **_moment(LONG_TERM, check.durability_long),
             **_moment(SAFETY, check.safety), **_shear_force(SAFETY, check.safety)},
            {"index": 2, **_moment(SEISMIC, check.seismic), **_shear_force(SEISMIC, check.seismic)}]


def _safety(check: FootingCheckResult) -> dict[str, Any]:
    bars = {"tensionBar": _strengths(check.main_steel), "sidebar": _strengths(check.main_steel),
            "stirrup": _strengths(check.stirrup_steel)}
    return {
        "safety_factor": {GROUP: [_safety_row(factors) for factors in check.safety_factors]},
        "material_bar": {GROUP: [{"separate": separate, **bars} for separate in _SEPARATE]},
        "material_concrete": {GROUP: {"fck": _number(check.fck), "dmax": _number(check.aggregate_max)}},
        "pile_factor": {GROUP: [{"id": id_, "title": title, "rfck": rfck, "rfbok": rfbok, "rEc": rec, "rVcd": rvcd,
                                 "selected": True} for id_, title, rfck, rfbok, rec, rvcd in _PILE_FACTORS]},
    }


def build_footing_wdj(check: FootingCheckResult) -> dict[str, Any]:
    """The WDJ of the footing check of one direction, as a JSON document."""
    names = ((1, check.name), (2, check.name + SEISMIC_SUFFIX))
    return {
        "$schema": SCHEMA, "format": "wdj", "schema_version": VERSION, "ver": VERSION, "lang": "ja",
        "pickup_filename": "", "pickup_data": None,
        "basic": _basic(check),
        "members": [{"m_no": 1, "m_len": None, "g_no": int(GROUP), "g_id": GROUP, "g_name": check.member,
                     "shape": RECTANGLE, "B": _number(check.width), "H": _number(check.depth), "Bt": None, "t": None,
                     "n": 1}],
        "crack": [_crack(check, index, name) for index, name in names],
        "points": [_point(index, name) for index, name in names],
        "bar": [_bar(check, index, name) for index, name in names],
        "shear": [_shear(check, 1, check.name, check.safety),
                  _shear(check, 2, check.name + SEISMIC_SUFFIX, check.seismic)],
        "fatigues": {"fatigue_list": [], "train_A_count": None, "train_B_count": None, "service_life": None},
        "safety": _safety(check),
        "force": _force(check),
        "calc": {"print_calculate_checked": True, "print_section_force_checked": False,
                 "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                 "calculate_moment_checked": True, "calculate_shear_force": True,
                 "calculate_torsional_moment": False, "member_group_selection": []},
    }


def write_footing_wdj(document: dict[str, Any]) -> bytes:
    """The bytes of the WDJ: UTF-8 JSON, as every JSON WebPier writes (core.integrity.dump_json)."""
    return dump_json(document)
