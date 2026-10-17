"""0610 concrete materials from the existing part-specific reinforcement inputs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
import math
from typing import Any

from .inputs import InputError


# RcDan EcCivilList: strength in N/mm² and elastic modulus in kN/mm².
_EC_TABLE = (
    (18, 22), (24, 25), (30, 28), (40, 31),
    (50, 33), (60, 35), (70, 37), (80, 38),
)
_EC_SOURCE = (
    "RcDan/General/InformationGetter.cs:192–217 (EcCivilList/GetEc); "
    "RcDan/Calculation/GeneralCalculation.cs:29–62 (GetLinear)"
)


@dataclass(frozen=True)
class ConcreteDesignCondition:
    """Strength in N/mm² and elastic modulus in kN/m², with provenance."""

    fck: float
    Ec: float
    input_path: str
    ec_source: str


@dataclass(frozen=True)
class LongitudinalDesignConditions:
    beam: ConcreteDesignCondition
    column: ConcreteDesignCondition
    footing: ConcreteDesignCondition


def _positive_strength(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path}: 正の有限数値が必要です")
    try:
        strength = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{path}: 正の有限数値が必要です") from exc
    if not math.isfinite(strength) or strength <= 0:
        raise InputError(f"{path}: 正の有限数値が必要です")
    return strength


def concrete_ec(fck_mpa: float) -> float:
    """Interpolate RcDan's table, extrapolate below 18, and cap at 80 MPa.

    The result is kN/m². No pile or density correction is applied.
    """
    strength = _positive_strength(fck_mpa, "fck_mpa")
    if strength >= _EC_TABLE[-1][0]:
        return _EC_TABLE[-1][1] * 1e6
    for (lower_fck, lower_ec), (upper_fck, upper_ec) in zip(_EC_TABLE, _EC_TABLE[1:]):
        if strength <= upper_fck:
            ec = lower_ec + (upper_ec - lower_ec) * (strength - lower_fck) / (upper_fck - lower_fck)
            return ec * 1e6
    raise AssertionError("finite strength below the upper bound must have an interval")


def _input_value(data: Any, *keys: str) -> Any:
    value = data
    traversed: list[str] = []
    for key in keys:
        traversed.append(key)
        if not isinstance(value, Mapping) or key not in value:
            raise InputError(f"入力項目がありません: {'.'.join(traversed)}")
        value = value[key]
    return value


def parse_longitudinal_design_conditions(data: Any) -> LongitudinalDesignConditions:
    """Read the already-loaded input without changing 0600/0620 parsing."""
    def material(part: str) -> ConcreteDesignCondition:
        path = f"鉄筋.{part}.concrete_strength_mpa"
        fck = _positive_strength(_input_value(data, "鉄筋", part, "concrete_strength_mpa"), path)
        return ConcreteDesignCondition(fck, concrete_ec(fck), path, _EC_SOURCE)

    return LongitudinalDesignConditions(
        beam=material("梁"),
        column=material("柱"),
        footing=material("フーチング"),
    )


def apply_longitudinal_materials(
    frame: Mapping[str, Any], conditions: LongitudinalDesignConditions,
) -> dict[str, Any]:
    """Return a 0610 material view without changing geometry or the shared frame.

    H1 has no dedicated material input. Its existing body reference is retained
    as column inheritance; this is a compatibility policy, not a new physical
    classification of the pedestal.
    """
    result = deepcopy(dict(frame))
    result["materials"] = {
        "beam": asdict(conditions.beam),
        "column": asdict(conditions.column),
        "footing": asdict(conditions.footing),
    }
    region_materials = {"h2": "beam", "h3": "beam", "h4": "column", "h1": "column"}
    for index, member in enumerate(result["members"]):
        if member["behavior"] == "rigid":
            member["material_ref"] = None
        elif member["behavior"] == "elastic":
            region = member["region"]
            if region not in region_materials:
                raise InputError(f"0610.frame.members[{index}].region: 材料対応のない弾性部位です（{region}）")
            member["material_ref"] = region_materials[region]
        else:
            raise InputError(f"0610.frame.members[{index}].behavior: elastic または rigid が必要です")
    result["material_provenance"] = {
        region: {
            "policy": "input_part", "material_ref": material,
            "input_path": result["materials"][material]["input_path"],
        }
        for region, material in region_materials.items() if region != "h1"
    }
    result["material_provenance"]["h1"] = {
        "policy": "compatibility_inheritance", "legacy_material_ref": "body",
        "material_ref": "column", "dedicated_input": False,
        "input_path": conditions.column.input_path,
    }
    result["material_provenance"]["footing"] = {
        "policy": "rigid_member_display_strength", "material_ref": None,
        "display_material_ref": "footing", "input_path": conditions.footing.input_path,
    }
    return result
