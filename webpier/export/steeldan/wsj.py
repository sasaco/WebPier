"""The WSJ of the pile body check of a steel pipe pile (decision 89; Capacita/SteelDan, docs plans wsj-json-specification.md).

One member and one point for each pile row (m_no and index are the row number; ``n`` is the piles of the row, by which SteelDan
divides the forces), all of one group. The section is the ``Pipe`` of the outer diameter ``h`` (corrosion allowance deducted)
and the effective thickness ``t``. The safety factors are the slot 1 of the group (安全性（破壊）: ``ri`` γi, ``rb_T``/``rb_C``/
``rb_S`` γb, ``rs`` γs; the slots 0 and 2 are placeholders that the check does not read), the material is the pipe's strength in
the three bands of the plate thickness. The forces are in the manual mode: ``<case>_Md``, ``<case>_Vd`` and ``<case>_Nd`` of the cases
6 (the largest bending moment), 7 (shear force) and 8 (axial force), the axial force positive in compression (FEMPython's
is negative). Nothing but ``calculate_pipe_pile`` is calculated and no report is selected but the one that adds no page.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...calc.pile_body import GAMMA_B, GAMMA_I, GAMMA_S, Case, PileRowForces, PileSteel
from ...core.integrity import dump_json

GROUP = "1"
NAME = "杭"
VERSION = "webpier"


def _number(item: Any) -> float:
    return item.value if hasattr(item, "value") else item


def _factor(identifier: int, title: str) -> dict[str, Any]:
    return {"id": identifier, "title": title, "ri": _number(GAMMA_I), "rb_T": _number(GAMMA_B), "rb_C": _number(GAMMA_B),
            "rb_S": _number(GAMMA_B), "rs": _number(GAMMA_S)}


def _section(row: int, steel: PileSteel) -> dict[str, Any]:
    return {"index": row, "m_no": row, "g_id": GROUP, "position": 0, "g_name": NAME, "p_name": f"杭列{row}", "shape": "Pipe",
            "1": None, "2": None, "3": None, "4": None, "5": None, "b": None, "h": steel.diameter.value,
            "t": steel.thickness.value}


def _force(item: PileRowForces) -> dict[str, Any]:
    force: dict[str, Any] = {"index": item.row}
    for case in Case:
        found = item.cases[case]
        force[f"{case.value}_Md"] = found.md
        force[f"{case.value}_Vd"] = found.vd
        force[f"{case.value}_Nd"] = -found.nd  # compression positive
        force[f"{case.value}_Mt"] = 0.0
    return force


def build_wsj(steel: PileSteel, rows: Sequence[PileRowForces]) -> dict[str, Any]:
    return {
        "$schema": "urn:webdan:wsj:1.0.0", "format": "wsj", "schema_version": "1.0.0", "ver": VERSION, "lang": "ja",
        "pickup_filename": "", "pickup_data": None,
        "basic": {"specification1_list": [], "specification2_list": [], "pickup_moment": [], "pickup_shear_force": [],
                  "pickup_torsional_moment": [], "conditions_list": []},
        "members": [{"m_no": item.row, "m_len": None, "g_no": 1, "g_id": GROUP, "g_name": NAME, "shape": "Pipe",
                     "eff_len": None, "n": item.piles} for item in rows],
        "crack": [],
        "points": [{"index": item.row, "m_no": item.row, "position": 0, "p_name": f"杭列{item.row}", "p_id": f"P{item.row}",
                    "isMyCalc": False, "isVyCalc": False, "isMzCalc": False, "isVzCalc": False, "isMtCalc": False,
                    "La": None} for item in rows],
        "sections": [_section(item.row, steel) for item in rows],
        "fatigues": {"fatigue_list": [], "train_A_count": None, "train_B_count": None, "service_life": None},
        "safety": {
            "safety_factor": {GROUP: [_factor(2, "安全性（疲労破壊）"), _factor(5, "安全性（破壊）"), _factor(7, "復旧性（損傷）地震時")]},
            "material_bar": {}, "material_concrete": {}, "pile_factor": {},
            "material_steel": {GROUP: [{"separate": limit, "fsyk": steel.fsyk.value, "fsvyk": steel.fsvyk.value, "fsuk": None}
                                       for limit in (16, 40, 75)]}},
        "force": [_force(item) for item in rows],
        "calc": {"print_calculate_checked": False, "print_section_force_checked": False, "print_safety_ratio_checked": True,
                 "print_summary_table_checked": False, "calculate_moment_checked": False, "calculate_shear_force": False,
                 "calculate_torsional_moment": False, "calculate_pipe_pile": True, "member_group_selection": []}}


def write_wsj(steel: PileSteel, rows: Sequence[PileRowForces]) -> bytes:
    return dump_json(build_wsj(steel, rows))
