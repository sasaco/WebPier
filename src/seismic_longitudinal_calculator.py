"""0710 earthquake actions adapted from the current in-memory 0610 result.

This report contract describes actions and physical geometry. It does not define
foundation restraints, apply a second seismic coefficient, or solve a response.
Only the explicitly selected earthquake audit fields cross the 0610 boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math
import re
from typing import Any

from .inputs import InputError
from .reaction_math import excel_round
from .seismic_frame import build_seismic_frame


CASE_MODEL_VERSION = "seismic-longitudinal-example2-v1"
FRAME_SPEC_VERSION = "seismic-longitudinal-column-base-micro-v2"
_HORIZONTAL_LABELS = {9: "桁荷重慣性力 Kh=1.00", 10: "列車荷重慣性力 Kh=0.20"}
_GEOMETRY_KEYS = (
    *(f"b{i}" for i in range(1, 10)), *(f"w{i}" for i in range(1, 10)),
    *(f"h{i}" for i in range(1, 7)), "df1", "df2", "hw1", "hw2", "hw3",
    "unit_weight_body", "unit_weight_footing", "unit_weight_soil", "unit_weight_displaced_soil",
)


def _at(source: Mapping[str, Any], path: str) -> Any:
    value: Any = source
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            raise InputError(f"0710: 0610.{path}が必要です")
        value = value[key]
    return value


def _number(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"0710: 0610.{path}には有限の数値が必要です")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise InputError(f"0710: 0610.{path}は数値範囲を超えています") from exc
    if not finite:
        raise InputError(f"0710: 0610.{path}には有限の数値が必要です")
    return value


def _numbers(source: Mapping[str, Any], path: str, keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: _number(_at(source, f"{path}.{key}"), f"{path}.{key}") for key in keys}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputError(f"0710: 0610.{path}にはオブジェクトが必要です")
    return value


def _rows(value: Any, path: str) -> list | tuple:
    if not isinstance(value, (list, tuple)) or not value:
        raise InputError(f"0710: 0610.{path}には空でない配列が必要です")
    return value


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InputError(f"0710: 0610.{path}には正の整数が必要です")
    return value


def _snapshot(value: Any, path: str) -> Any:
    """Copy the input snapshot, rejecting non-finite numeric values anywhere."""
    if isinstance(value, Mapping):
        return {key: _snapshot(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_snapshot(item, f"{path}[{index}]") for index, item in enumerate(value)]
        return tuple(items) if isinstance(value, tuple) else items
    if isinstance(value, (int, float)):
        _number(value, path)
    return deepcopy(value)


def _validate_result_numbers(value: Any, path: str = "result") -> None:
    """Include newly derived formula factors, whose arithmetic can overflow."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_result_numbers(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_result_numbers(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _number(value, path)


def _force_moment(source: Mapping[str, Any], path: str, *, supports: bool = False) -> dict[str, Any]:
    result = _numbers(source, path, ("N", "M"))
    if supports:
        for side in ("B", "C"):
            result[side] = _numbers(source, f"{path}.{side}", ("N", "arm", "M"))
    return result


def _seismic_frame(source: Mapping[str, Any], geometry: Mapping[str, Any]) -> dict[str, Any]:
    frame, _, _ = build_seismic_frame(source, geometry, target_stage="0710", source_stage="0610",
                                    frame_spec_version=FRAME_SPEC_VERSION)
    return frame


def _horizontal(source: Mapping[str, Any]) -> dict[str, Any]:
    rows = _rows(_at(source, "legacy_audit.horizontal"), "legacy_audit.horizontal")
    result = {}
    for name, identifier, kh in (("girder", 9, 1.0), ("train", 10, .2)):
        selected = [row for row in rows if isinstance(row, Mapping) and row.get("case") == identifier]
        if len(selected) != 1:
            raise InputError(f"0710: 0610.legacy_audit.horizontalのcase{identifier}は1件だけ必要です")
        row = selected[0]
        if (type(row["case"]) is not int or row.get("label") != _HORIZONTAL_LABELS[identifier]):
            raise InputError(f"0710: 0610.legacy_audit.horizontalのcase{identifier}の意味（Kh）が一致しません")
        result[name] = {key: _number(row.get(key), f"legacy_audit.horizontal.case{identifier}.{key}")
                        for key in ("B", "C", "total")}
        result[name].update(Kh=kh, coefficient_applied=True)
    return result


def _inertia_formulas(source: Mapping[str, Any], geometry: Mapping[str, Any],
                      inertia: Mapping[str, Any]) -> dict[str, Any]:
    kh = inertia["Kh"]
    formulas: dict[str, Any] = {}
    for name, b, w in (
        ("beam_top", geometry["b1"], geometry["w1"]),
        ("beam_bottom", geometry["b1"] - geometry["b4"] - geometry["b5"],
         geometry["w1"] - geometry["w4"] - geometry["w5"]),
        ("column", geometry["b6"], geometry["w6"]),
    ):
        raw = _number(b * w * geometry["unit_weight_body"] * kh, f"formulas.{name}.unrounded")
        if excel_round(raw, 2) != inertia[name]:
            raise InputError(f"0710: 0610.legacy_audit.inertia.{name}と現在入力の式が一致しません")
        formulas[name] = {"expression": "b*w*unit_weight*Kh",
                          "factors": {"b": b, "w": w, "unit_weight": geometry["unit_weight_body"], "Kh": kh},
                          "unrounded": raw, "value": inertia[name], "unit": "kN/m", "rounding_digits": 2}
    pedestal = inertia["pedestal"]
    pedestal_moment = _number(pedestal["H"] * pedestal["height"], "formulas.pedestal.moment_unrounded")
    if excel_round(pedestal_moment, 2) != pedestal["M"]:
        raise InputError("0710: 0610.legacy_audit.inertia.pedestal.Mと作用高さの式が一致しません")
    formulas["pedestal"] = {
        "expression": "weight*Kh", "moment_expression": "H*height",
        "factors": {"weight": pedestal["H"], "height": pedestal["height"], "Kh": kh,
                    "b": geometry["b3"], "w": geometry["w3"], "h": geometry["h1"]},
        "unrounded": pedestal["H"] * kh, "value": pedestal["H"],
        "moment_unrounded": pedestal_moment, "moment": pedestal["M"], "unit": "kN",
    }
    weight = _number(_at(source, "vertical.fixed.footing.N"), "vertical.fixed.footing.N")
    gamma, displaced = geometry["unit_weight_footing"], geometry["unit_weight_displaced_soil"]
    if gamma <= 0:
        raise InputError("0710: 0610.input.geometry.unit_weight_footingは正値が必要です")
    raw = _number(weight / gamma * (gamma - displaced) * kh, "formulas.footing.unrounded")
    if excel_round(raw, 2) != inertia["footing"]:
        raise InputError("0710: 0610.legacy_audit.inertia.footingと現在入力の式が一致しません")
    formulas["footing"] = {
        "expression": "weight/unit_weight*(unit_weight-displaced_unit_weight)*Kh",
        "factors": {"weight": weight, "unit_weight": gamma, "displaced_unit_weight": displaced, "Kh": kh},
        "geometry": {"b": geometry["b7"] + geometry["b8"] + geometry["b9"],
                     "w": geometry["w7"] + geometry["w8"] + geometry["w9"],
                     "h5": geometry["h5"], "h6": geometry["h6"]},
        "unrounded": raw, "value": inertia["footing"], "unit": "kN", "rounding_digits": 2,
    }
    return formulas


def calculate_seismic_longitudinal(longitudinal: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached 0710 snapshot; no files are read and no input is changed."""
    source = _mapping(longitudinal, "result")
    if type(source.get("schema_version")) is not int or source["schema_version"] != 2 or source.get("stage") != "0610":
        raise InputError("0710: schema_version=2、stage=0610の正規結果が必要です")
    audit = _mapping(_at(source, "legacy_audit"), "legacy_audit")
    if type(audit.get("schema_version")) is not int or audit["schema_version"] != 1 or audit.get("stage") != "0610":
        raise InputError("0710: 0610.legacy_auditにはschema_version=1、stage=0610が必要です")
    inputs = _snapshot(_mapping(_at(source, "input"), "input"), "input")
    geometry = _numbers(source, "input.geometry", _GEOMETRY_KEYS)
    for side in ("b", "c"):
        _numbers(source, f"input.spans.{side}", ("l1", "span", "l2", "f"))
        if _at(source, f"input.spans.{side}.bearing") not in ("固定", "可動"):
            raise InputError(f"0710: 0610.input.spans.{side}.bearingが不正です")
    _numbers(source, "input.train", ("earthquake_load",))
    vertical = {
        "fixed": {"column": _numbers(source, "vertical.fixed.column", ("intensity",)),
                  "top": _force_moment(source, "vertical.fixed.top"),
                  "footing": _force_moment(source, "vertical.fixed.footing")},
        "additional": {"top": _force_moment(source, "vertical.additional.top", supports=True),
                       "soil": _force_moment(source, "vertical.additional.soil")},
        "water": {"normal": _force_moment(source, "vertical.water.normal")},
        "snow": {"s2": _force_moment(source, "vertical.snow.s2", supports=True)},
        "train": {"earthquake": _force_moment(source, "legacy_audit.vertical.train.earthquake", supports=True)},
    }
    horizontal = _horizontal(source)
    inertia = _numbers(source, "legacy_audit.inertia", ("Kh", "beam_top", "beam_bottom", "column", "footing"))
    inertia["pedestal"] = _numbers(source, "legacy_audit.inertia.pedestal", ("H", "height", "M"))
    if inertia["Kh"] != 1.0:
        raise InputError("0710: 0610.legacy_audit.inertia.Kh=1.00が必要です")
    formulas = _inertia_formulas(source, geometry, inertia)
    specifications = (
        ("D1", "固定死荷重", "down", "fixed", vertical["fixed"]),
        ("D2", "付加死荷重", "down", "fixed", vertical["additional"]),
        ("Wp", "浮力（平水位）", "up", "fixed", vertical["water"]["normal"]),
        ("Sw2", "雪荷重（2年確率）", "down", "fixed", vertical["snow"]["s2"]),
        ("L", "地震時列車荷重", "down", "fixed", vertical["train"]["earthquake"]),
        ("EQ1", "桁荷重慣性力", "left", "incremental", horizontal["girder"]),
        ("EQL", "列車荷重慣性力", "left", "limited_incremental", horizontal["train"]),
        ("EQ2", "橋脚自重慣性力", "left", "incremental", inertia),
    )
    basics = [{"id": index, "symbol": symbol, "label": label, "direction": direction,
               "load_type": load_type, "coefficient": 1.0, "loads": deepcopy(loads)}
              for index, (symbol, label, direction, load_type, loads) in enumerate(specifications, 1)]
    provenance = {
        "references": [
            {"document": ".claude/docs/Example橋脚2/08_線路.pdf", "physical_pages": [1], "purpose": "physical_frame"},
            {"document": ".claude/docs/Example橋脚2/10_線路(耐震).pdf", "physical_pages": [1, 2, 3, 4, 5],
             "purpose": "column_base_micro_member"},
            {"document": ".claude/docs/Example橋脚2/10_線路(耐震).pdf", "physical_pages": [8, 12], "purpose": "actions_and_cases"},
            {"document": ".claude/docs/Example橋脚2/10_線路(耐震).pdf", "physical_pages": [10], "purpose": "normal_water_and_s2"},
        ],
        "dependencies": ["0610.input", "0610.frame", "0610.vertical.fixed", "0610.vertical.additional",
                         "0610.vertical.water.normal", "0610.vertical.snow.s2",
                         "0610.legacy_audit.vertical.train.earthquake", "0610.legacy_audit.horizontal.case9",
                         "0610.legacy_audit.horizontal.case10", "0610.legacy_audit.inertia"],
        "rounding": "0610の符号・転記精度・丸め順序を保持。列車Kh=0.20は適用済みで再乗算しない。",
        "combination_scope": "8基本ケースと1組合せの作用定義。構造応答・増分解析は実施しない。",
        "reference_section": "10.4作用の組合せを本帳票10.3として構成。",
        "model_scope": "柱下端微小要素の形状・原本種別だけを示し、構成則・解析は未定義。他部材の剛域化は今回再現しない。",
    }
    source_provenance = source.get("provenance", {})
    if not isinstance(source_provenance, Mapping):
        raise InputError("0710: 0610.provenanceにはオブジェクトが必要です")
    if "input_sha256" in source_provenance:
        sha = source_provenance["input_sha256"]
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None:
            raise InputError("0710: 0610.provenance.input_sha256が不正です")
        provenance["input_sha256"] = sha
    result = {
        "schema_version": 1, "stage": "0710", "direction": "longitudinal",
        "case_model_version": CASE_MODEL_VERSION, "input": inputs, "frame": _seismic_frame(source, geometry),
        "seismic_conditions": {"girder_Kh": 1.0, "train_Kh": .2, "pier_Kh": 1.0,
                               "train_coefficient_applied": True},
        "vertical": vertical, "horizontal": horizontal, "inertia": inertia, "formulas": formulas,
        "basic_cases": basics,
        "combinations": [{"id": 1, "alpha_f": 1.0, "rho_m": 1.0, "direction": "left",
                          "ground_resistance_type": 1, "coefficients": [1.0] * 8}],
        "units": {"length": "m", "force": "kN", "moment": "kN m", "line_load": "kN/m",
                  "area": "m2", "inertia": "m4", "unit_weight": "kN/m3", "elastic_modulus": "kN/m2"},
        "provenance": provenance,
        "warnings": ["0710は骨組形状と地震時作用・組合せを示します。構造解析・断面照査は実施しません。"],
    }
    _validate_result_numbers(result)
    return result
