"""The WDJ WebPier gives Capacita for the 0910 片持ち梁の断面照査 (decision 59, ADR-0008), with its section forces.

The document follows the RC document Capacita writes itself, as the column's (wdj.py), but it carries no pickup: the
section forces of each check are 0900's governing combinations, written to the force table (``force``: Md of each
bending row, Vd with its Md of each shear row, Mt with its Md and Vd of each torsion row; Md negative, tension at the
top), and Capacita's Headless calculates the WDJ as given (``run-rc`` without ``--pickup``, which returns no
``model.wdj``). One member (the beam, rectangle B1 × (H2 + H3)) with one point, 柱前面, checked for bending, shear and
torsion; the shear table gives the point's shear span a, in mm as RcDan reads it (the shear span ratio is La / d with d
in mm: a length in m would be taken for a few mm, a deep beam with βa at its cap). The faces have their own corrosion
environments (``con_u``, ``con_l``, ``con_s``), the crack row ε'csd of 0900's cracking moment, and the fatigue
conditions the trains of the input (the counts as text, as Capacita writes them). The side bars' centre from the side
face (``sidebar2.side_cover``) is the one the main bars' spacing is measured from.
"""

from __future__ import annotations

from typing import Any

from ...calc.cantilever.check import MEMBER, MEMBER_NAME, POINT_NAME, CantileverSectionResult
from ...calc.cantilever.combinations import Quantity
from ...core.printed import Precision, Printed
from .wdj import (_CONDITIONS, _MOMENT_TITLES, _PILE_FACTORS, _SEPARATE, _SHEAR_TITLES, _TORSION_TITLES, BODIES, GROUP,
                  RECTANGLE, SCHEMA, STANDARDS, VERSION, _main, _number, _safety_row, _strengths)

MOMENT_ROWS = tuple(range(9))  # Md0 … Md8
SHEAR_ROWS = tuple(range(8))  # Vd0 … Vd7
TORSION_ROWS = (0, 1, 5, 6, 7)  # Mt0, Mt1, Mt5, Mt6, Mt7
MILLIMETRES = Precision(0, "mm")  # the shear span a (m to 3 decimals) is a whole number of mm


def _millimetres(length: Printed) -> int | float | None:
    """*length* (m) in the mm RcDan reads La in."""
    return _number(MILLIMETRES(length.value * 1000))


def _blank_fatigue(*keys: str) -> dict[str, Any]:
    return dict.fromkeys(keys)


def _fatigue(check: CantileverSectionResult) -> dict[str, Any]:
    f = check.fatigue
    counts = {"SA": _number(f.sa_ratio), "SB": _number(f.sb_ratio), "NA06": _number(f.na06), "NB06": _number(f.nb06),
              "NA12": _number(f.na12), "NB12": _number(f.nb12), "A": 1, "B": 1}
    moment = {**counts, "r1_1": _number(f.gamma1_main), "r1_3": None, "Class": None, "weld": None}
    shear = {**counts, "r1_2": _number(f.gamma1_stirrup), "r1_3": 1}
    return {"fatigue_list": [{"m_no": None, "index": 1, "g_name": None, "p_name": None, "b": None, "h": None,
                              "M1": moment, "V1": shear,
                              "M2": _blank_fatigue(*moment), "V2": _blank_fatigue(*shear)}],
            "train_A_count": str(f.passenger_trains), "train_B_count": str(f.freight_trains),
            "service_life": str(f.service_life)}


def _force(check: CantileverSectionResult) -> dict[str, Any]:
    row: dict[str, Any] = {"index": 1}
    for id_ in MOMENT_ROWS:
        selected = check.selection(id_, Quantity.BENDING)
        row[f"Md{id_}_Md"] = None if selected is None else -_number(selected.md)
        row[f"Md{id_}_Nd"] = None
    for id_ in SHEAR_ROWS:
        selected = check.selection(id_, Quantity.SHEAR)
        row[f"Vd{id_}_Vd"] = None if selected is None else _number(selected.vd)
        row[f"Vd{id_}_Md"] = None if selected is None else -_number(selected.md)
        row[f"Vd{id_}_Nd"] = None
    for id_ in TORSION_ROWS:
        selected = check.selection(id_, Quantity.TORSION)
        row[f"Mt{id_}_Mt"] = None if selected is None else _number(selected.mt)
        row[f"Mt{id_}_Md"] = None if selected is None else -_number(selected.md)
        row[f"Mt{id_}_Vd"] = None if selected is None else _number(selected.vd)
        row[f"Mt{id_}_Nd"] = None
    return row


def _bar(check: CantileverSectionResult) -> dict[str, Any]:
    side = check.side
    return {
        "index": 1, "m_no": MEMBER, "haunch_M": None, "haunch_V": None,
        "rebar1": _main(check.upper, "上側"), "rebar2": _main(check.lower, "下側"),
        "sidebar1": {"side_dia": None if side is None else _number(side.diameter),
                     "side_n": None if side is None else side.count,
                     "side_cover": None if side is None else _number(side.first),
                     "side_ss": None if side is None else _number(side.spacing)},
        "sidebar2": {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None},
        "stirrup": {"stirrup_dia": _number(check.stirrups.diameter), "stirrup_n": check.stirrups.legs,
                    "stirrup_ss": _number(check.stirrups.pitch)},
        "bend": {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None},
        "tan": None, "g_name": None, "p_name": POINT_NAME, "b": _number(check.width), "h": _number(check.depth),
    }


def build_cantilever_wdj(check: CantileverSectionResult) -> dict[str, Any]:
    """The WDJ of the beam check, as a JSON document, with its section forces."""
    numbers = check.environment_numbers
    side = check.side_steel or check.main_steel
    bars = {"tensionBar": _strengths(check.main_steel), "sidebar": _strengths(side),
            "stirrup": _strengths(check.stirrup_steel)}
    return {
        "$schema": SCHEMA, "format": "wdj", "schema_version": VERSION, "ver": VERSION, "lang": "ja",
        "pickup_filename": "", "pickup_data": None,
        "basic": {
            "specification1_list": [{"id": 0, "title": "Rail", "selected": True},
                                    {"id": 3, "title": "Bangladesh", "selected": False}],
            "specification2_list": [{"id": id_, "title": title, "selected": id_ == BODIES[check.body]}
                                    for id_, title in STANDARDS],
            "pickup_moment": [{"id": id_, "title": _MOMENT_TITLES[id_], "no": None} for id_ in MOMENT_ROWS],
            "pickup_shear_force": [{"id": id_, "title": _SHEAR_TITLES[id_], "no": None} for id_ in SHEAR_ROWS],
            "pickup_torsional_moment": [{"id": id_, "title": _TORSION_TITLES[id_], "no": None} for id_ in TORSION_ROWS],
            "conditions_list": [{"id": id_, "title": title, "selected": getattr(check, name)}
                                for id_, title, name in _CONDITIONS],
        },
        "members": [{"m_no": MEMBER, "m_len": None, "g_no": int(GROUP), "g_id": GROUP, "g_name": MEMBER_NAME,
                     "shape": RECTANGLE, "B": _number(check.width), "H": _number(check.depth), "Bt": None, "t": None,
                     "n": 1}],
        "crack": [{"index": 1, "m_no": MEMBER, "p_name": None, "con_u": numbers["上面"], "con_l": numbers["下面"],
                   "con_s": numbers["側面"], "vis_u": check.appearance, "vis_l": check.appearance,
                   "ecsd_u": _number(check.ecsd), "ecsd_l": _number(check.ecsd), "kr": _number(check.kr),
                   "k4": _number(check.k4)}],
        "points": [{"index": 1, "m_no": MEMBER, "position": None, "p_name": POINT_NAME, "p_id": None,
                    "isMyCalc": False, "isVyCalc": True, "isMzCalc": True, "isVzCalc": False, "isMtCalc": True,
                    "axis_type": 2, "isUpperCalc": True, "isLowerCalc": True}],
        "bar": [_bar(check)],
        "shear": [{"index": 1, "m_no": MEMBER, "p_name": POINT_NAME, "La": _millimetres(check.shear_span),
                   "fixed_end": None, "L": None, "concrete": None, "bar": None, "g_name": None}],
        "fatigues": _fatigue(check),
        "safety": {
            "safety_factor": {GROUP: [_safety_row(factors) for factors in check.safety]},
            "material_bar": {GROUP: [{"separate": separate, **bars} for separate in _SEPARATE]},
            "material_concrete": {GROUP: {"fck": _number(check.fck), "dmax": _number(check.aggregate_max)}},
            "pile_factor": {GROUP: [{"id": id_, "title": title, "rfck": rfck, "rfbok": rfbok, "rEc": rec,
                                     "rVcd": rvcd, "selected": True}
                                    for id_, title, rfck, rfbok, rec, rvcd in _PILE_FACTORS]},
        },
        "force": [_force(check)],
        "calc": {"print_calculate_checked": True, "print_section_force_checked": False,
                 "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                 "calculate_moment_checked": True, "calculate_shear_force": True,
                 "calculate_torsional_moment": True, "member_group_selection": []},
    }
