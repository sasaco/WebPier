"""Build a WebDan WDJ by applying typed semantic edits to a trusted base WDJ."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


class WdjError(RuntimeError):
    """Raised when a WDJ or request is unsafe or inconsistent."""


ROOT_KEYS = {
    "ver",
    "basic",
    "members",
    "points",
    "bar",
    "safety",
    "force",
    "calc",
}

GRADE = {
    "SD295": {"id": 1, "fsy": 295, "fsu": 440},
    "SD345": {"id": 2, "fsy": 345, "fsu": 490},
    "SD390": {"id": 3, "fsy": 390, "fsu": 560},
    "SD490": {"id": 4, "fsy": 490, "fsu": 620},
}

JAPAN_DIAMETERS = {10, 13, 16, 19, 22, 25, 29, 32, 35, 38, 41, 51}
BANGLADESH_DIAMETERS = {10, 12, 16, 20, 25, 28, 32, 36, 40, 50}

FORCE_FIELDS = {
    *(f"Md{i}_{suffix}" for i in range(9) for suffix in ("Md", "Nd")),
    *(f"Vd{i}_{suffix}" for i in range(8) for suffix in ("Vd", "Md", "Nd")),
    *(f"Mt{i}_{suffix}" for i in (0, 1, 5, 6, 7) for suffix in ("Mt", "Md", "Vd", "Nd")),
}

POINT_CHECK_FIELDS = {
    "upper": "isUpperCalc",
    "lower": "isLowerCalc",
    "torsion": "isMtCalc",
}

REBAR_FIELDS = {
    "diameter_mm": "rebar_dia",
    "count": "rebar_n",
    "cover_to_center_mm": "rebar_cover",
    "first_row_count": "rebar_lines",
    "row_spacing_mm": "rebar_space",
    "adjacent_spacing_mm": "rebar_ss",
    "slope_cos": "cos",
}

CALCULATION_FIELDS = {
    "bending": "calculate_moment_checked",
    "shear": "calculate_shear_force",
    "torsion": "calculate_torsional_moment",
    "print_calculation": "print_calculate_checked",
    "print_section_forces": "print_section_force_checked",
    "print_safety_ratios": "print_safety_ratio_checked",
    "print_summary": "print_summary_table_checked",
}


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise WdjError(f"failed to read {label} {path}: {exc}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WdjError(f"{label} is not UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WdjError(f"{label} root must be a JSON object: {path}")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WdjError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise WdjError(f"{label} must be an array")
    return value


def _positive_number(value: Any, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WdjError(f"{label} must be a number")
    if not math.isfinite(float(value)) or value <= 0:
        raise WdjError(f"{label} must be greater than zero")
    return value


def _nullable_number(value: Any, label: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WdjError(f"{label} must be a number or null")
    if not math.isfinite(float(value)):
        raise WdjError(f"{label} must be finite")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WdjError(f"{label} must be an integer")
    return value


def _reject_unknown(
    value: dict[str, Any], allowed: set[str], label: str
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise WdjError(f"unsupported {label} field(s): {', '.join(unknown)}")


def _require(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise WdjError(f"{label} is missing required field(s): {', '.join(missing)}")


def _validate_request_shape(request: dict[str, Any]) -> None:
    """Enforce the closed request shape documented by request.schema.json."""
    _reject_unknown(
        request,
        {"design", "member", "point", "rebar", "materials", "forces", "calculation"},
        "request",
    )
    _require(request, {"member", "point"}, "request")

    if "design" in request:
        design = _object(request["design"], "request.design")
        _reject_unknown(design, {"application_id", "standard_id"}, "design")

    member = _object(request["member"], "request.member")
    _require(member, {"m_no"}, "member")
    _reject_unknown(member, {"m_no", "group_name", "section"}, "member")
    if "section" in member:
        section = _object(member["section"], "member.section")
        _require(section, {"width_mm", "height_mm"}, "member.section")
        _reject_unknown(
            section, {"shape", "width_mm", "height_mm"}, "member.section"
        )

    point = _object(request["point"], "request.point")
    _require(point, {"index"}, "point")
    _reject_unknown(point, {"index", "name", "axis", "checks"}, "point")
    if "checks" in point:
        checks = _object(point["checks"], "point.checks")
        _reject_unknown(
            checks,
            {"upper", "lower", "bending", "shear", "torsion"},
            "point.checks",
        )

    if "rebar" in request:
        rebar = _object(request["rebar"], "request.rebar")
        _reject_unknown(rebar, {"upper", "lower"}, "rebar")
        for side in ("upper", "lower"):
            if side in rebar:
                side_value = _object(rebar[side], f"rebar.{side}")
                _reject_unknown(side_value, set(REBAR_FIELDS), f"rebar.{side}")

    if "materials" in request:
        materials = _object(request["materials"], "request.materials")
        _reject_unknown(
            materials,
            {"group_no", "longitudinal_grade", "concrete"},
            "materials",
        )
        if "concrete" in materials:
            concrete = _object(materials["concrete"], "materials.concrete")
            _reject_unknown(
                concrete,
                {"fck_mpa", "max_aggregate_mm"},
                "materials.concrete",
            )

    if "forces" in request:
        forces = _object(request["forces"], "request.forces")
        _reject_unknown(forces, FORCE_FIELDS, "forces")

    if "calculation" in request:
        calculation = _object(request["calculation"], "request.calculation")
        _reject_unknown(calculation, set(CALCULATION_FIELDS), "calculation")


def _unique(rows: list[Any], key: str, value: Any, label: str) -> dict[str, Any]:
    matches = [row for row in rows if isinstance(row, dict) and row.get(key) == value]
    if len(matches) != 1:
        raise WdjError(
            f"expected exactly one {label} with {key}={value!r}; found {len(matches)}"
        )
    return matches[0]


def _selected_id(basic: dict[str, Any], name: str) -> int:
    rows = _array(basic.get(name), f"basic.{name}")
    selected = [row for row in rows if isinstance(row, dict) and row.get("selected") is True]
    if (
        len(selected) != 1
        or isinstance(selected[0].get("id"), bool)
        or not isinstance(selected[0].get("id"), int)
    ):
        raise WdjError(f"basic.{name} must contain exactly one selected integer id")
    return selected[0]["id"]


def _set_selected(basic: dict[str, Any], name: str, wanted: int) -> None:
    rows = _array(basic.get(name), f"basic.{name}")
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == wanted]
    if len(matches) != 1:
        raise WdjError(f"basic.{name} has no unique id {wanted}")
    for row in rows:
        if isinstance(row, dict):
            row["selected"] = row.get("id") == wanted


def _apply_design(root: dict[str, Any], request: dict[str, Any]) -> None:
    design = request.get("design")
    if design is None:
        return
    design = _object(design, "request.design")
    basic = _object(root.get("basic"), "basic")
    if "application_id" in design:
        _set_selected(
            basic,
            "specification1_list",
            _integer(design["application_id"], "design.application_id"),
        )
    if "standard_id" in design:
        _set_selected(
            basic,
            "specification2_list",
            _integer(design["standard_id"], "design.standard_id"),
        )


def _sync_dimensions(
    root: dict[str, Any], member_no: int, width: Any, height: Any
) -> None:
    for row in _array(root.get("bar"), "bar"):
        if isinstance(row, dict) and row.get("m_no") == member_no:
            row["b"] = width
            row["h"] = height
    fatigues = root.get("fatigues")
    if isinstance(fatigues, dict):
        rows = fatigues.get("fatigue_list")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("m_no") == member_no:
                    row["b"] = width
                    row["h"] = height


def _rename_group(
    root: dict[str, Any], group_no: Any, old: str, new: str
) -> None:
    for member in _array(root.get("members"), "members"):
        if isinstance(member, dict) and member.get("g_no") == group_no:
            member["g_name"] = new
    for collection in ("bar", "shear", "crack"):
        for row in _array(root.get(collection), collection):
            if isinstance(row, dict) and row.get("g_name") == old:
                row["g_name"] = new
    fatigues = root.get("fatigues")
    if isinstance(fatigues, dict) and isinstance(fatigues.get("fatigue_list"), list):
        for row in fatigues["fatigue_list"]:
            if isinstance(row, dict) and row.get("g_name") == old:
                row["g_name"] = new
    calc = _object(root.get("calc"), "calc")
    selections = calc.get("member_group_selection")
    if isinstance(selections, list):
        for row in selections:
            if isinstance(row, dict) and row.get("GroupName") == old:
                row["GroupName"] = new


def _apply_member(
    root: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    member_request = _object(request.get("member"), "request.member")
    member_no = _integer(member_request.get("m_no"), "member.m_no")
    member = _unique(
        _array(root.get("members"), "members"), "m_no", member_no, "member"
    )

    if "group_name" in member_request:
        new_name = member_request["group_name"]
        if not isinstance(new_name, str) or not new_name.strip():
            raise WdjError("member.group_name must be a non-empty string")
        old_name = member.get("g_name") if isinstance(member.get("g_name"), str) else ""
        _rename_group(root, member.get("g_no"), old_name, new_name.strip())

    section = member_request.get("section")
    if section is not None:
        section = _object(section, "member.section")
        shape = section.get("shape", "rectangle")
        if shape != "rectangle":
            raise WdjError(
                "build_wdj.py currently supports only section.shape='rectangle'"
            )
        width = _positive_number(
            section.get("width_mm"), "member.section.width_mm"
        )
        height = _positive_number(
            section.get("height_mm"), "member.section.height_mm"
        )
        member.update(
            {"shape": 1, "B": width, "H": height, "Bt": None, "t": None}
        )
        _sync_dimensions(root, member_no, width, height)
    return member


def _rename_point(root: dict[str, Any], point_index: int, new_name: str) -> None:
    for collection in ("bar", "shear", "crack"):
        for row in _array(root.get(collection), collection):
            if isinstance(row, dict) and row.get("index") == point_index:
                row["p_name"] = new_name
    fatigues = root.get("fatigues")
    if isinstance(fatigues, dict) and isinstance(fatigues.get("fatigue_list"), list):
        for row in fatigues["fatigue_list"]:
            if isinstance(row, dict) and row.get("index") == point_index:
                row["p_name"] = new_name


def _apply_point(
    root: dict[str, Any], request: dict[str, Any], member_no: int
) -> dict[str, Any]:
    point_request = _object(request.get("point"), "request.point")
    point_index = _integer(point_request.get("index"), "point.index")
    point = _unique(
        _array(root.get("points"), "points"), "index", point_index, "point"
    )
    if point.get("m_no") != member_no:
        raise WdjError(f"point {point_index} does not refer to member {member_no}")

    if "name" in point_request:
        name = point_request["name"]
        if not isinstance(name, str) or not name.strip():
            raise WdjError("point.name must be a non-empty string")
        point["p_name"] = name.strip()
        _rename_point(root, point_index, name.strip())

    if "axis" in point_request:
        axes = {"My-Vz": 1, "Mz-Vy": 2}
        if point_request["axis"] not in axes:
            raise WdjError("point.axis must be 'My-Vz' or 'Mz-Vy'")
        point["axis_type"] = axes[point_request["axis"]]

    checks = point_request.get("checks")
    if checks is not None:
        checks = _object(checks, "point.checks")
        for source, target in POINT_CHECK_FIELDS.items():
            if source in checks:
                if not isinstance(checks[source], bool):
                    raise WdjError(f"point.checks.{source} must be boolean")
                point[target] = checks[source]
        axis = point.get("axis_type")
        if "bending" in checks:
            if not isinstance(checks["bending"], bool):
                raise WdjError("point.checks.bending must be boolean")
            point["isMyCalc"] = bool(checks["bending"] and axis == 1)
            point["isMzCalc"] = bool(checks["bending"] and axis == 2)
        if "shear" in checks:
            if not isinstance(checks["shear"], bool):
                raise WdjError("point.checks.shear must be boolean")
            point["isVzCalc"] = bool(checks["shear"] and axis == 1)
            point["isVyCalc"] = bool(checks["shear"] and axis == 2)
    return point


def _apply_rebar_side(
    target: dict[str, Any],
    source: dict[str, Any],
    label: str,
    diameters: set[int],
) -> None:
    if "diameter_mm" in source:
        diameter = _integer(
            source["diameter_mm"], f"rebar.{label}.diameter_mm"
        )
        if diameter not in diameters:
            raise WdjError(
                f"rebar.{label}.diameter_mm={diameter} is unsupported for the selected application"
            )
        target["rebar_dia"] = diameter
    if "count" in source:
        count = _integer(source["count"], f"rebar.{label}.count")
        if count < 2:
            raise WdjError(
                f"rebar.{label}.count must be at least 2 for a rectangular section"
            )
        target["rebar_n"] = count
    for source_name, target_name in REBAR_FIELDS.items():
        if source_name in {"diameter_mm", "count"}:
            continue
        if source_name in source:
            target[target_name] = _nullable_number(
                source[source_name], f"rebar.{label}.{source_name}"
            )


def _apply_rebar(
    root: dict[str, Any],
    request: dict[str, Any],
    member_no: int,
    point_index: int,
) -> None:
    rebar_request = request.get("rebar")
    if rebar_request is None:
        return
    rebar_request = _object(rebar_request, "request.rebar")
    bar = _unique(
        _array(root.get("bar"), "bar"), "index", point_index, "bar row"
    )
    if bar.get("m_no") != member_no:
        raise WdjError(f"bar row {point_index} does not refer to member {member_no}")
    if bar.get("input_mode") not in (None, 0):
        raise WdjError("preview reinforcement mode (rebar0) is not supported")

    application_id = _selected_id(
        _object(root.get("basic"), "basic"), "specification1_list"
    )
    diameters = (
        BANGLADESH_DIAMETERS if application_id == 3 else JAPAN_DIAMETERS
    )
    for source_name, target_name in (("upper", "rebar1"), ("lower", "rebar2")):
        if source_name not in rebar_request:
            continue
        source = _object(rebar_request[source_name], f"rebar.{source_name}")
        target = _object(bar.get(target_name), f"bar.{target_name}")
        _apply_rebar_side(target, source, source_name, diameters)


def _group_key(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WdjError(f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise WdjError(f"{label} must be finite")
    return str(int(value)) if float(value).is_integer() else str(value)


def _apply_materials(
    root: dict[str, Any], request: dict[str, Any], member: dict[str, Any]
) -> None:
    materials = request.get("materials")
    if materials is None:
        return
    materials = _object(materials, "request.materials")
    group_key = _group_key(
        materials.get("group_no", member.get("g_no")),
        "materials.group_no or member.g_no",
    )
    member_group_key = _group_key(member.get("g_no"), "member.g_no")
    if group_key != member_group_key:
        raise WdjError(
            "materials.group_no must match the selected member group: "
            f"expected {member_group_key}, got {group_key}"
        )
    safety = _object(root.get("safety"), "safety")

    if "longitudinal_grade" in materials:
        grade_name = materials["longitudinal_grade"]
        if grade_name not in GRADE:
            raise WdjError(f"unsupported longitudinal grade: {grade_name!r}")
        material_bar = _object(
            safety.get("material_bar"), "safety.material_bar"
        )
        rows = _array(
            material_bar.get(group_key), f"safety.material_bar.{group_key}"
        )
        if not rows:
            raise WdjError(f"safety.material_bar.{group_key} is empty")
        for row in rows:
            tension = _object(
                _object(row, "material_bar row").get("tensionBar"),
                "tensionBar",
            )
            tension.update(GRADE[grade_name])

    concrete = materials.get("concrete")
    if concrete is not None:
        concrete = _object(concrete, "materials.concrete")
        by_group = _object(
            safety.get("material_concrete"), "safety.material_concrete"
        )
        target = _object(
            by_group.get(group_key), f"safety.material_concrete.{group_key}"
        )
        if "fck_mpa" in concrete:
            target["fck"] = _positive_number(
                concrete["fck_mpa"], "materials.concrete.fck_mpa"
            )
        if "max_aggregate_mm" in concrete:
            target["dmax"] = _positive_number(
                concrete["max_aggregate_mm"],
                "materials.concrete.max_aggregate_mm",
            )


def _apply_forces(
    root: dict[str, Any], request: dict[str, Any], point_index: int
) -> None:
    forces = request.get("forces")
    if forces is None:
        return
    forces = _object(forces, "request.forces")
    if root.get("pickup_filename") not in (None, ""):
        raise WdjError("request.forces is only valid when pickup_filename is empty")
    row = _unique(
        _array(root.get("force"), "force"), "index", point_index, "force row"
    )
    unknown = sorted(set(forces) - FORCE_FIELDS)
    if unknown:
        raise WdjError(f"unsupported force field(s): {', '.join(unknown)}")
    for key, value in forces.items():
        row[key] = _nullable_number(value, f"forces.{key}")


def _apply_calculation(root: dict[str, Any], request: dict[str, Any]) -> None:
    calculation = request.get("calculation")
    if calculation is None:
        return
    calculation = _object(calculation, "request.calculation")
    calc = _object(root.get("calc"), "calc")
    for source, target in CALCULATION_FIELDS.items():
        if source in calculation:
            if not isinstance(calculation[source], bool):
                raise WdjError(f"calculation.{source} must be boolean")
            calc[target] = calculation[source]


def _selected_summary(basic: dict[str, Any], name: str) -> dict[str, Any]:
    selected_id = _selected_id(basic, name)
    row = _unique(_array(basic.get(name), f"basic.{name}"), "id", selected_id, name)
    return {"id": selected_id, "title": row.get("title")}


def _grade_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    matches = [
        name
        for name, grade in GRADE.items()
        if all(value.get(key) == expected for key, expected in grade.items())
    ]
    return matches[0] if len(matches) == 1 else None


def _flatten_request(
    value: dict[str, Any], prefix: str = ""
) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.extend(_flatten_request(child, path))
        else:
            result.append((path, child))
    return result


def _numeric_group_key(value: str) -> int | float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _semantic_summary_data(
    root: dict[str, Any],
    member: dict[str, Any],
    point: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    point_index = point.get("index")
    bar = _unique(
        _array(root.get("bar"), "bar"), "index", point_index, "bar row"
    )
    basic = _object(root.get("basic"), "basic")
    application = _selected_summary(basic, "specification1_list")
    standard = _selected_summary(basic, "specification2_list")

    materials_request = request.get("materials")
    if not isinstance(materials_request, dict):
        materials_request = {}
    material_group_key = _group_key(
        materials_request.get("group_no", member.get("g_no")),
        "materials.group_no or member.g_no",
    )
    safety = _object(root.get("safety"), "safety")
    material_rows = _array(
        _object(safety.get("material_bar"), "safety.material_bar").get(
            material_group_key
        ),
        f"safety.material_bar.{material_group_key}",
    )
    longitudinal_rows = []
    grade_names: list[str | None] = []
    for raw_row in material_rows:
        row = _object(raw_row, "material_bar row")
        tension = _object(row.get("tensionBar"), "tensionBar")
        grade_name = _grade_name(tension)
        grade_names.append(grade_name)
        longitudinal_rows.append(
            {
                "diameterBoundaryMm": row.get("separate"),
                "grade": grade_name,
                "stored": tension.copy(),
            }
        )
    unique_grades = set(grade_names)
    longitudinal_grade: Any = (
        grade_names[0] if len(unique_grades) == 1 and grade_names else grade_names
    )

    concrete = _object(
        _object(safety.get("material_concrete"), "safety.material_concrete").get(
            material_group_key
        ),
        f"safety.material_concrete.{material_group_key}",
    )
    force = _unique(
        _array(root.get("force"), "force"), "index", point_index, "force row"
    )
    calc = _object(root.get("calc"), "calc")
    axis_name = {1: "My-Vz", 2: "Mz-Vy"}.get(point.get("axis_type"))

    fatigue_mirrors = []
    fatigues = root.get("fatigues")
    if isinstance(fatigues, dict) and isinstance(fatigues.get("fatigue_list"), list):
        for row in fatigues["fatigue_list"]:
            if (
                isinstance(row, dict)
                and row.get("m_no") == member.get("m_no")
                and row.get("index") == point_index
            ):
                fatigue_mirrors.append(
                    {"index": row.get("index"), "bMm": row.get("b"), "hMm": row.get("h")}
                )

    actuals: dict[str, Any] = {
        "design.application_id": application["id"],
        "design.standard_id": standard["id"],
        "member.m_no": member.get("m_no"),
        "member.group_name": member.get("g_name"),
        "member.section.shape": "rectangle",
        "member.section.width_mm": member.get("B"),
        "member.section.height_mm": member.get("H"),
        "point.index": point_index,
        "point.name": point.get("p_name"),
        "point.axis": axis_name,
        "point.checks.upper": point.get("isUpperCalc"),
        "point.checks.lower": point.get("isLowerCalc"),
        "point.checks.bending": point.get("isMyCalc") is True
        or point.get("isMzCalc") is True,
        "point.checks.shear": point.get("isVyCalc") is True
        or point.get("isVzCalc") is True,
        "point.checks.torsion": point.get("isMtCalc"),
        "materials.group_no": _numeric_group_key(material_group_key),
        "materials.longitudinal_grade": longitudinal_grade,
        "materials.concrete.fck_mpa": concrete.get("fck"),
        "materials.concrete.max_aggregate_mm": concrete.get("dmax"),
    }
    for side_name, stored_name in (("upper", "rebar1"), ("lower", "rebar2")):
        side = _object(bar.get(stored_name), f"bar.{stored_name}")
        for request_name, stored_field in REBAR_FIELDS.items():
            actuals[f"rebar.{side_name}.{request_name}"] = side.get(stored_field)
    for field in FORCE_FIELDS:
        actuals[f"forces.{field}"] = force.get(field)
    for request_name, stored_field in CALCULATION_FIELDS.items():
        actuals[f"calculation.{request_name}"] = calc.get(stored_field)

    force_values = {
        field: force.get(field)
        for field in sorted(FORCE_FIELDS)
        if force.get(field) is not None
    }
    calculation = {
        request_name: calc.get(stored_field)
        for request_name, stored_field in CALCULATION_FIELDS.items()
    }
    return {
        "application": application,
        "standard": standard,
        "bar": bar,
        "fatigueMirrors": fatigue_mirrors,
        "materialGroupNo": _numeric_group_key(material_group_key),
        "longitudinalRows": longitudinal_rows,
        "concrete": {
            "fckMpa": concrete.get("fck"),
            "maxAggregateMm": concrete.get("dmax"),
        },
        "forceValues": force_values,
        "calculation": calculation,
        "memberGroupSelection": calc.get("member_group_selection"),
        "axisName": axis_name,
        "actuals": actuals,
    }


def _compare_request(
    request: dict[str, Any], actuals: dict[str, Any]
) -> dict[str, Any]:
    items = []
    mismatches = []
    for path, requested in _flatten_request(request):
        if path not in actuals:
            items.append(
                {
                    "requestPath": path,
                    "requested": requested,
                    "actual": None,
                    "status": "unmapped",
                }
            )
            mismatches.append(path)
            continue
        actual = actuals[path]
        effective_requested = (
            requested.strip()
            if path in {"member.group_name", "point.name"}
            and isinstance(requested, str)
            else requested
        )
        status = "matched" if effective_requested == actual else "mismatch"
        items.append(
            {
                "requestPath": path,
                "requested": requested,
                "actual": actual,
                "status": status,
            }
        )
        if status != "matched":
            mismatches.append(path)
    if mismatches:
        raise WdjError(
            "request-to-output comparison failed for: " + ", ".join(mismatches)
        )
    return {
        "status": "matched",
        "requestedLeafCount": len(items),
        "matchedLeafCount": len(items),
        "items": items,
    }


def _validate(
    root: dict[str, Any], member: dict[str, Any], point: dict[str, Any]
) -> tuple[list[str], list[dict[str, str]]]:
    checks: list[dict[str, str]] = []
    missing = sorted(ROOT_KEYS - set(root))
    if missing:
        raise WdjError(f"WDJ is missing root key(s): {', '.join(missing)}")
    checks.append({"id": "root-keys", "status": "passed"})
    basic = _object(root.get("basic"), "basic")
    _selected_id(basic, "specification1_list")
    _selected_id(basic, "specification2_list")
    checks.append({"id": "design-selection", "status": "passed"})

    if member.get("shape") != 1:
        raise WdjError("selected member must be a rectangular section (shape=1)")
    width = _positive_number(member.get("B"), "member.B")
    height = _positive_number(member.get("H"), "member.H")
    checks.append({"id": "member-section", "status": "passed"})
    member_no = member.get("m_no")
    point_index = point.get("index")
    if point.get("m_no") != member_no:
        raise WdjError("selected point has a dangling member reference")
    if point.get("axis_type") not in (1, 2):
        raise WdjError("point.axis_type must be 1 or 2")
    checks.append({"id": "point-reference", "status": "passed"})

    bar = _unique(
        _array(root.get("bar"), "bar"), "index", point_index, "bar row"
    )
    if bar.get("m_no") != member_no:
        raise WdjError("selected bar row has a dangling member reference")
    if bar.get("b") != width or bar.get("h") != height:
        raise WdjError("bar.b/h are inconsistent with member.B/H")
    checks.append({"id": "bar-dimension-mirror", "status": "passed"})

    for side in ("rebar1", "rebar2"):
        rebar = _object(bar.get(side), f"bar.{side}")
        count = rebar.get("rebar_n")
        if count is not None and (
            isinstance(count, bool)
            or not isinstance(count, (int, float))
            or count < 2
        ):
            raise WdjError(f"bar.{side}.rebar_n must be at least 2 when set")
        cover = rebar.get("rebar_cover")
        if cover is not None and (
            isinstance(cover, bool)
            or not isinstance(cover, (int, float))
            or cover <= 0
            or cover >= height
        ):
            raise WdjError(f"bar.{side}.rebar_cover must be between 0 and H")
    checks.append({"id": "reinforcement-geometry", "status": "passed"})

    warnings: list[str] = []
    fatigue_status = "passed"
    fatigues = root.get("fatigues")
    if isinstance(fatigues, dict) and isinstance(fatigues.get("fatigue_list"), list):
        for row in fatigues["fatigue_list"]:
            if (
                isinstance(row, dict)
                and row.get("m_no") == member_no
                and row.get("index") == point_index
                and (row.get("b") != width or row.get("h") != height)
            ):
                fatigue_status = "warning"
                warnings.append("fatigue b/h are inconsistent with member.B/H")
    checks.append({"id": "fatigue-dimension-mirror", "status": fatigue_status})

    group_key = _group_key(member.get("g_no"), "member.g_no")
    safety = _object(root.get("safety"), "safety")
    material_rows = _array(
        _object(safety.get("material_bar"), "safety.material_bar").get(group_key),
        f"safety.material_bar.{group_key}",
    )
    if not material_rows:
        raise WdjError(f"safety.material_bar.{group_key} is empty")
    for raw_row in material_rows:
        _object(_object(raw_row, "material_bar row").get("tensionBar"), "tensionBar")
    concrete = _object(
        _object(safety.get("material_concrete"), "safety.material_concrete").get(
            group_key
        ),
        f"safety.material_concrete.{group_key}",
    )
    _positive_number(concrete.get("fck"), "material_concrete.fck")
    _positive_number(concrete.get("dmax"), "material_concrete.dmax")
    checks.append({"id": "materials-and-concrete", "status": "passed"})

    force_status = "passed"
    if root.get("pickup_filename") in (None, ""):
        force = _unique(
            _array(root.get("force"), "force"),
            "index",
            point_index,
            "force row",
        )
        bending = point.get("isMyCalc") is True or point.get("isMzCalc") is True
        if bending and not any(
            force.get(f"Md{i}_Md") is not None for i in range(9)
        ):
            warnings.append("bending is enabled but no Md*_Md force is set")
            force_status = "warning"
        shear = point.get("isVyCalc") is True or point.get("isVzCalc") is True
        if shear and not any(
            force.get(f"Vd{i}_Vd") is not None for i in range(8)
        ):
            warnings.append("shear is enabled but no Vd*_Vd force is set")
            force_status = "warning"
        if point.get("isMtCalc") is True and not any(
            force.get(f"Mt{i}_Mt") is not None for i in (0, 1, 5, 6, 7)
        ):
            warnings.append("torsion is enabled but no Mt*_Mt force is set")
            force_status = "warning"
    checks.append({"id": "force-coverage", "status": force_status})

    calc = _object(root.get("calc"), "calc")
    calc_status = "passed"
    requested_checks = {
        "bending": point.get("isMyCalc") is True or point.get("isMzCalc") is True,
        "shear": point.get("isVyCalc") is True or point.get("isVzCalc") is True,
        "torsion": point.get("isMtCalc") is True,
    }
    for label, point_enabled in requested_checks.items():
        calc_enabled = calc.get(CALCULATION_FIELDS[label]) is True
        if point_enabled and not calc_enabled:
            warnings.append(
                f"point enables {label} but calculation.{label} is disabled"
            )
            calc_status = "warning"
    checks.append({"id": "calculation-selection", "status": calc_status})
    return warnings, checks


def _summary(
    root: dict[str, Any],
    member: dict[str, Any],
    point: dict[str, Any],
    request: dict[str, Any],
    warnings: list[str],
    checks: list[dict[str, str]],
) -> dict[str, Any]:
    data = _semantic_summary_data(root, member, point, request)
    bar = data["bar"]
    request_comparison = _compare_request(request, data["actuals"])
    requested_paths = [item["requestPath"] for item in request_comparison["items"]]
    inherited_paths = sorted(
        path
        for path, actual in data["actuals"].items()
        if path not in requested_paths
        and path not in {"member.m_no", "point.index"}
        and actual is not None
    )
    return {
        "version": root.get("ver"),
        "mode": (
            "manual" if root.get("pickup_filename") in (None, "") else "pickup"
        ),
        "application": data["application"],
        "standard": data["standard"],
        "member": {
            "mNo": member.get("m_no"),
            "groupNo": member.get("g_no"),
            "groupName": member.get("g_name"),
            "shape": "rectangle",
            "widthMm": member.get("B"),
            "heightMm": member.get("H"),
            "dimensionMirrors": {
                "bar": {"bMm": bar.get("b"), "hMm": bar.get("h")},
                "fatigue": data["fatigueMirrors"],
            },
        },
        "point": {
            "index": point.get("index"),
            "name": point.get("p_name"),
            "axis": {"id": point.get("axis_type"), "name": data["axisName"]},
            "checks": {
                "upper": point.get("isUpperCalc"),
                "lower": point.get("isLowerCalc"),
                "bending": (
                    point.get("isMyCalc") is True
                    or point.get("isMzCalc") is True
                ),
                "shear": (
                    point.get("isVyCalc") is True
                    or point.get("isVzCalc") is True
                ),
                "torsion": point.get("isMtCalc"),
            },
        },
        "rebar": {"upper": bar.get("rebar1"), "lower": bar.get("rebar2")},
        "materials": {
            "groupNo": data["materialGroupNo"],
            "longitudinalRows": data["longitudinalRows"],
            "concrete": data["concrete"],
        },
        "forces": {
            "pointIndex": point.get("index"),
            "nonNullCount": len(data["forceValues"]),
            "values": data["forceValues"],
        },
        "calculation": {
            **data["calculation"],
            "memberGroupSelection": data["memberGroupSelection"],
        },
        "provenance": {
            "requestedPaths": requested_paths,
            "inheritedPaths": inherited_paths,
        },
        "validation": {
            "status": (
                "semantic_passed_with_warnings" if warnings else "semantic_passed"
            ),
            "checks": checks,
            "requestComparison": request_comparison,
            "engineValidation": "not_run_by_build_wdj",
            "warnings": warnings,
        },
    }


def _write_atomic(
    path: Path,
    value: dict[str, Any],
    indent: int | None,
    *,
    overwrite: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = None if indent else (",", ":")
    text = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
        )
        + "\n"
    )
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    reservation_created = False
    try:
        with os.fdopen(
            handle, "w", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if not overwrite:
            try:
                reservation = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
            except FileExistsError as exc:
                raise WdjError(
                    f"output already exists: {path}; pass --overwrite only "
                    "when replacement is explicitly authorized"
                ) from exc
            else:
                os.close(reservation)
                reservation_created = True
        os.replace(temporary_name, path)
        reservation_created = False
    except Exception:
        if reservation_created:
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def build_document(
    root: dict[str, Any], request: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_request_shape(request)
    missing = sorted(ROOT_KEYS - set(root))
    if missing:
        raise WdjError(f"base WDJ is missing root key(s): {', '.join(missing)}")
    _apply_design(root, request)
    member = _apply_member(root, request)
    point = _apply_point(
        root, request, _integer(member.get("m_no"), "member.m_no")
    )
    point_index = _integer(point.get("index"), "point.index")
    _apply_rebar(root, request, member["m_no"], point_index)
    _apply_materials(root, request, member)
    _apply_forces(root, request, point_index)
    _apply_calculation(root, request)
    warnings, checks = _validate(root, member, point)
    return root, _summary(root, member, point, request, warnings, checks)


def build(
    base_path: Path, request_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _load_json(base_path, "base WDJ")
    request = _load_json(request_path, "request")
    return build_document(root, request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", required=True, type=Path, help="trusted existing WDJ"
    )
    parser.add_argument(
        "--request", required=True, type=Path, help="typed request JSON"
    )
    parser.add_argument(
        "--output", type=Path, help="new WDJ path; required unless --check-only"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate and print summary without writing",
    )
    parser.add_argument(
        "--compact", action="store_true", help="write compact JSON"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output file; use only with explicit authorization",
    )
    args = parser.parse_args()

    base_path = args.base.resolve()
    request_path = args.request.resolve()
    if not base_path.is_file():
        parser.error(f"base WDJ not found: {base_path}")
    if not request_path.is_file():
        parser.error(f"request JSON not found: {request_path}")
    if not args.check_only and args.output is None:
        parser.error("--output is required unless --check-only is used")

    try:
        root, summary = build(base_path, request_path)
        if not args.check_only:
            output_path = args.output.resolve()
            if output_path == base_path:
                raise WdjError(
                    "output must differ from base; in-place overwrite is not allowed"
                )
            if output_path == request_path:
                raise WdjError("output must differ from the request JSON path")
            if output_path.suffix.lower() != ".wdj":
                raise WdjError("output filename must use the .wdj extension")
            if output_path.exists() and not output_path.is_file():
                raise WdjError(f"output exists and is not a file: {output_path}")
            if output_path.exists() and not args.overwrite:
                raise WdjError(
                    f"output already exists: {output_path}; pass --overwrite only "
                    "when replacement is explicitly authorized"
                )
            _write_atomic(
                output_path,
                root,
                None if args.compact else 2,
                overwrite=args.overwrite,
            )
            summary["output"] = str(output_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except WdjError as exc:
        parser.exit(2, f"WDJ build failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
