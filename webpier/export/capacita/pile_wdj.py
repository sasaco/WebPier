"""The WDJ WebPier gives Capacita for the 0612 / 0622 杭体の照査 of a cast-in-place pile (decision 91, ADR-0008), in its
section force input mode: no pickup (``pickup_filename`` empty), the forces of each case written in ``force`` by Capacita's
case id 5 (安全性（破壊）: Md5 with its Nd, Vd5 with its Md and Nd; the other cases are left blank, so the warnings WD-408
and WD-409 name them and the report has the two sections of the 安全性（破壊）only). The runner is called without ``--pickup``
(pipeline.capacita.check_section) and returns the report only.

One group 場所打ち杭 of a circular section (``shape`` 3, B the diameter, the bars of the first face only, the
bars on the worst side: ``c_type`` 1), one member for each pile row with ``n`` the piles of the row (Capacita divides the
forces by it), and one point for each case of each row: the design forces of the case are the point's. The forces are
those of the bundled member, the per-pile values the report prints given back multiplied by the piles; the axial force is
positive in compression, as Capacita reads it (tried on the real runner: a compression case prints its N'd as it is and a
tension case as negative). Both sides of a point are calculated (``isUpperCalc`` and ``isLowerCalc``): with only the
lower one the real runner returned no section at all (tried). The shear span is not given (``shear`` is empty: the shear span
ratio is not considered, as Capacita does for a point without a La).
The safety factors are those of the column (wdj.py): RC標準 R5 of the railway bodies, 安全性（破壊）, with the pile factors
of the 施工条件 selected. The crack rows are not written: the check of the durability is not asked for.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...calc._exact import d, put
from ...calc.pile_cast import FORCE, LEGS_PER_SET, PILE_FACTORS, CaseForces, CastSection, RowForces
from ...calc.column_check import SAFETY_FACTORS
from ...core.integrity import dump_json
from ...core.printed import Printed
from .wdj import (_CONDITIONS, _MOMENT_TITLES, _SEPARATE, _SHEAR_TITLES, _TORSION_TITLES, BODIES, GROUP, SCHEMA, STANDARDS,
                  VERSION, _number, _safety_row, _strengths)

CIRCLE = 3  # RcDan's shape number of a circle or a ring
WORST_SIDE = 1  # c_type: the bars on the most severe side (RcDan ReBarTypeForCircular.MostSevere)
POINT_ID = "ITAN"  # the points are not places of the pile: the PIK's point of each case is printed by the report
SAFETY = 5  # Capacita's case id of 安全性（破壊）
BODY = "JR各社"  # the specification: RC標準 R5 of the railway (R5_Rail)
# the two conditions of Capacita's 条件: not adopted (the column's are the input's, decision 48; a pile has none)
ADOPTED = {"jr001": False, "jr004": False}


def _total(value: Printed, piles: int) -> int | float | None:
    """The forces of the bundled member: the printed force of one pile times the piles (exact decimals, ADR-0003)."""
    return _number(put(FORCE, d(value) * piles))


def _points(rows: Sequence[RowForces]) -> list[tuple[int, RowForces, CaseForces]]:
    """(index, row, case) of each point, rows in order and the cases of a row in order, the index from 1."""
    return [(index, row, case) for index, (row, case) in enumerate(
        ((row, case) for row in rows for case in row.cases), 1)]


def name(row: RowForces, case: CaseForces) -> str:
    """The name of a point: the pile row and the case, as the report of Capacita prints it."""
    return f"杭列{row.row} {case.kind.value}"


def _cases(titles) -> list[dict[str, Any]]:
    ids = sorted(titles) if isinstance(titles, dict) else range(len(titles))
    return [{"id": id_, "title": titles[id_], "no": None} for id_ in ids]


def _basic() -> dict[str, Any]:
    selected = BODIES[BODY]
    return {
        "specification1_list": [{"id": 0, "title": "Rail", "selected": True},
                                {"id": 3, "title": "Bangladesh", "selected": False}],
        "specification2_list": [{"id": id_, "title": title, "selected": id_ == selected} for id_, title in STANDARDS],
        "pickup_moment": _cases(_MOMENT_TITLES),
        "pickup_shear_force": _cases(_SHEAR_TITLES),
        "pickup_torsional_moment": _cases(_TORSION_TITLES),
        "conditions_list": [{"id": id_, "title": title, "selected": ADOPTED[key]} for id_, title, key in _CONDITIONS],
    }


def _point(index: int, row: RowForces, case: CaseForces) -> dict[str, Any]:
    return {"index": index, "m_no": row.row, "position": _number(case.distance), "p_name": name(row, case),
            "p_id": POINT_ID, "isMyCalc": False, "isVyCalc": True, "isMzCalc": True, "isVzCalc": False,
            "isMtCalc": False, "axis_type": 2, "isUpperCalc": True, "isLowerCalc": True}


def _bar(section: CastSection, index: int, row: RowForces, case: CaseForces) -> dict[str, Any]:
    none = {"side_dia": None, "side_n": None, "side_cover": None, "side_ss": None}
    return {
        "index": index, "m_no": row.row, "haunch_M": None, "haunch_V": None,
        "rebar1": {"title": "全周", "rebar_dia": _number(section.bar_diameter), "rebar_n": section.bar_count,
                   "rebar_cover": _number(section.centre), "rebar_lines": None, "rebar_space": None, "rebar_ss": None,
                   "cos": None, "enable": True},
        "rebar2": {"title": "", "rebar_dia": None, "rebar_n": None, "rebar_cover": None, "rebar_lines": None,
                   "rebar_space": None, "rebar_ss": None, "cos": None, "enable": True},
        "sidebar1": dict(none), "sidebar2": dict(none),
        "stirrup": {"stirrup_dia": _number(section.hoop_diameter), "stirrup_n": section.hoop_sets * LEGS_PER_SET,
                    "stirrup_ss": _number(section.hoop_pitch)},
        "bend": {"bending_dia": None, "bending_n": None, "bending_ss": None, "bending_angle": None},
        "tan": None, "g_name": None, "p_name": name(row, case), "b": _number(section.diameter),
        "h": _number(section.diameter),
    }


def _force(index: int, row: RowForces, case: CaseForces) -> dict[str, Any]:
    md, nd, vd = (_total(value, row.piles) for value in (case.md, case.nd, case.vd))
    return {"index": index, f"Md{SAFETY}_Md": md, f"Md{SAFETY}_Nd": nd,
            f"Vd{SAFETY}_Vd": vd, f"Vd{SAFETY}_Md": md, f"Vd{SAFETY}_Nd": nd}


def _safety(section: CastSection, factor: tuple[str, str, float, float, float, float]) -> dict[str, Any]:
    bars = {"tensionBar": _strengths(section.bar_steel), "sidebar": _strengths(section.bar_steel),
            "stirrup": _strengths(section.hoop_steel)}
    return {
        "safety_factor": {GROUP: [_safety_row(factors) for factors in SAFETY_FACTORS]},
        "material_bar": {GROUP: [{"separate": separate, **bars} for separate in _SEPARATE]},
        "material_concrete": {GROUP: {"fck": _number(section.fck), "dmax": _number(section.aggregate_max)}},
        "pile_factor": {GROUP: [{"id": id_, "title": title, "rfck": rfck, "rfbok": rfbok, "rEc": rec, "rVcd": rvcd,
                                 "selected": id_ == factor[0]} for id_, title, rfck, rfbok, rec, rvcd in PILE_FACTORS]},
    }


def build_pile_wdj(section: CastSection, factor: tuple[str, str, float, float, float, float],
                   rows: Sequence[RowForces]) -> dict[str, Any]:
    """The WDJ of the pile body check of a cast-in-place pile, as a JSON document."""
    points = _points(rows)
    return {
        "$schema": SCHEMA, "format": "wdj", "schema_version": VERSION, "ver": VERSION, "lang": "ja",
        "pickup_filename": "", "pickup_data": None,
        "basic": _basic(),
        "members": [{"m_no": row.row, "m_len": None, "g_no": int(GROUP), "g_id": GROUP, "g_name": "場所打ち杭",
                     "shape": CIRCLE, "B": _number(section.diameter), "H": None, "Bt": None, "t": None, "n": row.piles,
                     "c_type": WORST_SIDE, "vo_type": None} for row in rows],
        "crack": [],
        "points": [_point(index, row, case) for index, row, case in points],
        "bar": [_bar(section, index, row, case) for index, row, case in points],
        "shear": [],
        "fatigues": {"fatigue_list": [], "train_A_count": None, "train_B_count": None, "service_life": None},
        "safety": _safety(section, factor),
        "force": [_force(index, row, case) for index, row, case in points],
        "calc": {"print_calculate_checked": True, "print_section_force_checked": False,
                 "print_safety_ratio_checked": False, "print_summary_table_checked": False,
                 "calculate_moment_checked": True, "calculate_shear_force": True,
                 "calculate_torsional_moment": False, "member_group_selection": []},
    }


def write_pile_wdj(document: dict[str, Any]) -> bytes:
    """The bytes of the WDJ: UTF-8 JSON, as every JSON WebPier writes (core.integrity.dump_json)."""
    return dump_json(document)
