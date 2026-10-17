"""0610 longitudinal actions, frame data and original combination coefficients.

Only explicit source equations are evaluated. The calculation has no workbook
dependency and does not perform structural analysis or member verification.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import math
from typing import Any

from .foundation_springs import foundation_spring_set
from .frame_model import build_frame_model
from .inputs import InputError
from .longitudinal_actions import build_canonical_actions, calculation_details, reference_formulas, validate_action_upstream
from .longitudinal_combinations import BASIC_ROWS, COMBINATION_ROWS, SOURCE_SHA256
from .longitudinal_design_conditions import LongitudinalDesignConditions, apply_longitudinal_materials
from .longitudinal_example2_cases import build_case_model
from .reaction_inputs import ReactionInput
from .reaction_math import excel_round as R


def _finite(value: Any, path: str = "0610") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not math.isfinite(value):
        raise InputError(f"{path}: 有限の数値が必要です")


def calculate_longitudinal(inputs: ReactionInput, foundation: dict,
                           reactions: dict, *, design_conditions: LongitudinalDesignConditions) -> dict[str, Any]:
    """Public nonseismic schema 2 calculation with explicit part materials."""
    return calculate_longitudinal_canonical(inputs, foundation, reactions, design_conditions=design_conditions)


def _validate_inputs(inputs: ReactionInput, foundation: dict, reactions: dict) -> None:
    _finite(asdict(inputs), "0610入力")
    if inputs.geometry.unit_weight_footing <= 0:
        raise InputError("0610: フーチングの単位体積重量は正値が必要です")
    foundation_sha = foundation.get("provenance", {}).get("input_sha256")
    reaction_sha = reactions.get("provenance", {}).get("input_sha256")
    if foundation_sha and reaction_sha and foundation_sha != reaction_sha:
        raise InputError("0610: 0500と0600の入力SHA256が一致しません")


def calculate_longitudinal_legacy(inputs: ReactionInput, foundation: dict,
                                  reactions: dict) -> dict[str, Any]:
    """Replay the original schema 1 equations and historical macro springs."""
    try:
        _validate_inputs(inputs, foundation, reactions)
        result = _calculate(inputs, foundation, reactions, spring_set=None)
        _finite(result)
        return result
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError(f"0610線路方向荷重: 入力または計算結果が数値範囲を超えています（{exc}）") from exc


def calculate_longitudinal_canonical(inputs: ReactionInput, foundation: dict, reactions: dict, *,
                                     design_conditions: LongitudinalDesignConditions) -> dict[str, Any]:
    """Build the nonseismic Example2 families with the adopted 0600 pier impact."""
    if not isinstance(design_conditions, LongitudinalDesignConditions):
        raise InputError("0610.design_conditions: 部位別の材料条件が必要です")
    try:
        _validate_inputs(inputs, foundation, reactions)
        springs = foundation_spring_set(foundation, "longitudinal")
        validate_action_upstream(reactions)
        model = build_case_model(ultimate_factor=inputs.train.factors_ultimate,
                                 service_factor=inputs.train.factors_service)
        audit = _calculate(inputs, foundation, reactions, spring_set=springs)
        audit["provenance"]["audit_basis"] = "旧式＋正規方向ばね（線路方向Double）。旧macro完全再現はcalculate_longitudinal_legacy。"
        actions = build_canonical_actions(inputs, reactions, audit, model)
        result = {
            "schema_version": 2, "stage": "0610", "input": asdict(inputs),
            "design_conditions": asdict(design_conditions), **model, **actions,
            "frame": apply_longitudinal_materials(audit["frame"], design_conditions),
            "reference_formulas": reference_formulas(audit), "calculation_details": calculation_details(audit),
            "legacy_audit": audit,
            "units": deepcopy(audit["units"]),
            "provenance": {
                "reference_document": "Example橋脚2/08_線路.pdf", "reference_pages": [9, 10, 11],
                "dependencies": ["current input", "0500.long_term", "0500.short_term", "0600.dead_loads.points",
                                 "0600.dead_loads.track_totals", "0600.snow_loads.points", "0600.train.raw_reactions",
                                 "0600.train.pier", "0600.longitudinal", "0600.longitudinal_snow_cases",
                                 "0600.macro_handoff_single"],
                "combination_scope": "Example2非地震20基本・16組合せ。係数は名目定義、採用作用は用途別に解決。",
                "impact_policy": "C05: 0600用途別橋脚係数を保持。Single(ROUND((raw*a)*track*c_p,1))。低減・0.75・rhoを再適用しない。",
                "horizontal_policy": "C07: L+Iによる支承摩擦を保持。C08: 0600の側別復旧性制動係数を保持。",
                "rounding": "LはDoubleで(raw*a)*track。Iは支点別0.1kN丸め後Single。Mは支点別2桁、合計は追加丸めなし。",
                "audit_basis": audit["provenance"]["audit_basis"],
            },
            "warnings": [*inputs.warnings,
                         "0610は非地震の作用・組合せ定義を作成します。構造解析・断面照査は実施しません。",
                         "支持ばねは0500正規長短期の線路方向Double値を使用します。",
                         "材料は梁・柱・フーチングの既存入力とRcDan補間。H1は専用入力がないため旧bodyから柱材料を継承します。",
                         "C05の用途別橋脚衝撃低減を採用し、Example2の未低減衝撃とは区別します。",
                         "鉛直Iの名目係数0でも、C07のL+I支承摩擦とC08の側別復旧性係数を含む0600水平力は保持します。",
                         "旧セル・旧ケース・地震作用は旧式＋正規方向ばねのlegacy_auditに限定します。"],
        }
        _finite(result)
        return result
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError(f"0610線路方向荷重: 入力または計算結果が数値範囲を超えています（{exc}）") from exc


def _calculate(inputs: ReactionInput, foundation: dict, reactions: dict, *,
               spring_set: dict | None) -> dict[str, Any]:
    geometry = inputs.geometry
    handoff = reactions["macro_handoff_single"]
    dead = reactions["dead_loads"]["points"]
    cells: dict[str, dict[str, Any]] = {name: {} for name in ("骨組図", "荷重計算", "荷重図", "荷重組合せ")}
    transfers: list[dict[str, Any]] = []

    def transfer(sheet: str, cell: str, source: str, value: Any,
                 precision: str = "Double", unit: str = "m") -> None:
        cells[sheet][cell] = value
        transfers.append({"sheet": sheet, "cell": cell, "source": source,
                          "value": value, "precision": precision, "unit": unit})

    frame_cells = cells["骨組図"]
    for prefix, column, count in (("b", "E", 9), ("w", "M", 9), ("h", "U", 6)):
        for index in range(1, count + 1):
            attribute = f"{prefix}{index}"
            transfer("骨組図", f"{column}{index + 3}", f"input.geometry.{attribute}", getattr(geometry, attribute))
    transfer("骨組図", "B16", "input.下部構造.杭種.選択値", "直接基礎", "text", "")
    for component, field, cell in (("柱", "xL", "E13"), ("フーチング", "hG", "U10")):
        transfer("骨組図", cell, f"0600.macro_handoff_single.{component}.{field}",
                 handoff[component][field], "VBA Single")
    spring_components = ({(row["term"], row["component"]): row for row in spring_set["components"]}
                         if spring_set is not None else None)
    for column, term in (("L", "long_term"), ("T", "short_term")):
        for row, spring in ((144, "Kv"), (145, "Ks"), (146, "Kr")):
            if spring_components is None:
                transfer("骨組図", f"{column}{row}", f"0500.macro_handoff_single.{term}.{spring}",
                         foundation["macro_handoff_single"][term][spring], "VBA Single",
                         "kN m/rad" if spring == "Kr" else "kN/m")
            else:
                component = spring_components[term, spring]
                transfer("骨組図", f"{column}{row}", component["source_path"], component["value"],
                         component["precision"], component["unit"])
    _frame(frame_cells)

    load_cells = cells["荷重計算"]
    for field, cell, unit in (
        ("df1", "R4", "m"), ("df2", "R5", "m"), ("hw1", "R6", "m"),
        ("hw2", "R7", "m"), ("hw3", "R8", "m"),
        ("unit_weight_body", "AC4", "kN/m3"), ("unit_weight_footing", "AC5", "kN/m3"),
        ("unit_weight_soil", "AC6", "kN/m3"), ("unit_weight_displaced_soil", "AC7", "kN/m3"),
    ):
        transfer("荷重計算", cell, f"input.geometry.{field}", getattr(geometry, field), unit=unit)
    for side, span, row in (("B", inputs.spans.b, 5), ("C", inputs.spans.c, 6)):
        transfer("荷重計算", f"E{row}", f"input.spans.{side.lower()}.f", span.f)
    for side, d1, d2 in (("B", "M29", "M52"), ("C", "M30", "M53")):
        for field, cell in (("D1", d1), ("D2", d2)):
            transfer("荷重計算", cell, f"0600.dead_loads.points.{side}.{field}", dead[side][field], unit="kN")
    for component, ncell, xcell in (
        ("フーチング", "AB21", "P22"), ("桁受け", "M31", "T31"), ("はり", "M32", "T32"),
        ("上載土", "AB42", "P43"), ("高水位", "AB62", "P63"),
        ("平水位", "AB67", "P68"), ("低水位", "AB72", "P73"),
    ):
        for field, cell, unit in (("N", ncell, "kN"), ("xL", xcell, "m")):
            transfer("荷重計算", cell, f"0600.macro_handoff_single.{component}.{field}",
                     handoff[component][field], "VBA Single", unit)
    transfer("荷重計算", "T156", "0600.macro_handoff_single.桁受け.hG", handoff["桁受け"]["hG"], "VBA Single")
    for kind, group, track, first in (("列車荷重", "安全性", "複線", 83),
                                      ("列車荷重", "使用性", "単線", 91),
                                      ("衝撃荷重", "安全性", "複線", 112),
                                      ("衝撃荷重", "使用性", "単線", 120)):
        for offset, support in enumerate(("RB", "RC")):
            transfer("荷重計算", f"M{first + offset}", f"0600.macro_handoff_single.{kind}.{group}.{track}.{support}",
                     handoff[kind][group][track][support], "VBA Single", "kN")
    for support, row in (("RB", 99), ("RC", 100)):
        transfer("荷重計算", f"M{row}", f"0600.macro_handoff_single.地震列車.{support}",
                 handoff["地震列車"][support], "VBA Single", "kN")
    for index, forces in enumerate(handoff["線路荷重強度"]):
        for support, column in (("RB", "U"), ("RC", "Y")):
            transfer("荷重計算", f"{column}{131 + index}", f"0600.macro_handoff_single.線路荷重強度[{index}].{support}",
                     forces[support], "VBA Single", "kN")
    _loads(load_cells, frame_cells)

    frame = {
        "nodes": [{"id": row - 80, "x": frame_cells[f"I{row}"], "y": frame_cells[f"L{row}"],
                   "source_row": row} for row in range(81, 85)],
        "shape_eccentricity": frame_cells["E13"],
        "section": {"width": frame_cells["I92"], "depth": frame_cells["P92"],
                    "area": frame_cells["AB93"], "inertia": frame_cells["AB94"], "footing": "rigid"},
        "materials": {"body": {"fck": 24.0, "Ec": 2.5e7}, "footing": {"fck": 24.0, "Ec": 2.5e7}},
        "springs": {term: {spring: frame_cells[f"{column}{row}"]
                            for row, spring in ((144, "Kv"), (145, "Ks"), (146, "Kr"))}
                    for column, term in (("L", "long_term"), ("T", "short_term"))},
    }
    frame = build_frame_model(asdict(geometry), frame, "b")
    if spring_set is not None:
        frame["spring_provenance"] = {"direction": "longitudinal", "support_node_id": frame["support_node_id"],
                                      "components": deepcopy(spring_set["components"])}
    vertical, horizontal, inertia = _load_groups(load_cells)
    basic_cases, combinations = _combinations(cells["荷重組合せ"], vertical, horizontal, inertia)
    snow_transfers = _append_snow_cases(inputs, reactions, vertical, horizontal, basic_cases, combinations)
    warnings = [*inputs.warnings,
                *[f"0500: {warning}" for warning in foundation.get("warnings", [])],
                *[f"0600: {warning}" for warning in reactions.get("warnings", [])],
                "0610は荷重・骨組条件と原表の組合せ係数を作成します。構造解析・断面照査は実施しません。",
                ("Krは元VBAに従い0500の直角方向のSingle値を線路方向にも使用します。" if spring_set is None else
                 "支持ばね6成分は0500正規長短期の線路方向Double値を使用します。荷重式は旧式監査用です。"),
                "主幹節点のx座標は0とし、H1が正のパラペットには形状による偏心を設けます。柱重心の偏心を節点へ加算しません。",
                "基本ケースのバネ番号3は原表の分類です。第3のばね定数や応答を算定するものではありません。",
                "保存済み図形の固定寸法は使用せず、現在の節点座標から図を作成します。"]
    return {
        "schema_version": 1, "stage": "0610", "input": asdict(inputs),
        "provenance": {
            "source_workbook": "Example橋脚/0610_線路方向荷重.xls", "source_sha256": SOURCE_SHA256,
            "source_vba": ["Example橋脚/wiki/evidence/vba/input/線路荷重.bas"],
            "method": "元セル数式を明示的に再計算。実行時Excel・証拠JSON参照なし。",
            "rounding": ("元ROUND箇所だけ15桁正規化と指定桁丸め。転記Singleは上流値を保持。" if spring_set is None else
                         "元ROUND箇所だけ15桁正規化と指定桁丸め。支持ばねは0500正規Double、0600転記Singleは上流値を保持。"),
            "dependencies": [*(["0500.macro_handoff_single"] if spring_set is None else ["0500.long_term", "0500.short_term"]),
                             "0600.macro_handoff_single", "0600.dead_loads.points",
                             *(["0600.snow_loads.points", "0600.longitudinal_snow_cases"] if snow_transfers else [])],
            "combination_scope": "旧元表係数を保持しS30/LR単独4組合せを追加（存在時）。暗黙の1.2乗算・応答解析なし。",
            **({"snow_combinations": "Example橋脚2/07 7-10・7-12のS30とLR単独を追加。列車・衝撃・水位荷重を含まない。0600のS30鉛直荷重Doubleと水平荷重Singleを使用。構造解析・断面照査は実施しない。"}
               if snow_transfers else {}),
        },
        "units": {"length": "m", "force": "kN", "moment": "kN m", "line_load": "kN/m",
                  "area": "m2", "inertia": "m4", "unit_weight": "kN/m3", "elastic_modulus": "kN/m2"},
        "warnings": warnings, "frame": frame, "vertical": vertical,
        "horizontal": horizontal, "inertia": inertia,
        "basic_cases": basic_cases, "combinations": combinations,
        **({"snow_transfers": snow_transfers} if snow_transfers else {}),
        "transfers": transfers, "cells": cells,
        "inactive_source_cells": {"骨組図": ["AB102", "AB103", "W113", "W114", *[f"S{r}" for r in range(149, 157)]],
                                  "荷重計算": [f"AB{r}" for r in (23, 24, 44, 45, 46, 47, 64, 69, 74)]},
    }


def _snow_handoff(reactions: dict) -> tuple[list[dict[str, Any]], list[Any]] | None:
    handoff = reactions["macro_handoff_single"]
    has_cases = "longitudinal_snow_cases" in reactions
    has_handoff = "線路雪荷重強度" in handoff
    if not has_cases and not has_handoff:
        return None
    if has_cases != has_handoff:
        raise InputError("0610: 0600のlongitudinal_snow_casesと線路雪荷重強度は両方必要です")
    cases, forces = reactions["longitudinal_snow_cases"], handoff["線路雪荷重強度"]
    identifiers = ("safety_lr_s30", "recovery_lr_s30")
    if (not isinstance(cases, list) or not isinstance(forces, list)
            or len(cases) != 2 or len(forces) != 2
            or any(not isinstance(row, dict) or row.get("id") != identifier or not isinstance(row.get("label"), str)
                   for row, identifier in zip(cases, identifiers))):
        raise InputError("0610: 0600のS30追加荷重は安全性・復旧性の2行が必要です")
    return cases, forces


def _append_snow_cases(inputs: ReactionInput, reactions: dict, vertical: dict,
                       horizontal: list, basics: list, combinations: list) -> list:
    handoff = _snow_handoff(reactions)
    if handoff is None:
        return []
    cases, forces = handoff
    transfers = []

    def transferred(target: str, source: str, value: Any, precision: str, unit: str) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise InputError(f"0610: {source}には有限の数値が必要です")
        transfers.append({"target": target, "source": source, "value": value, "precision": precision, "unit": unit})
        return value

    snow = {}
    for side, arm in (("B", -inputs.spans.b.f), ("C", inputs.spans.c.f)):
        source = f"0600.snow_loads.points.{side}.雪荷重_30年確率"
        value = reactions.get("snow_loads", {}).get("points", {}).get(side, {}).get("雪荷重_30年確率")
        force = transferred(f"vertical.snow30.{side}.N", source, value, "Double", "kN")
        snow[side] = {"N": force, "arm": arm, "M": R(force * arm, 2)}
    snow.update(N=snow["B"]["N"] + snow["C"]["N"], M=snow["B"]["M"] + snow["C"]["M"])
    vertical["snow30"] = snow
    for index, (case, force) in enumerate(zip(cases, forces)):
        if not isinstance(force, dict) or not all(support in force for support in ("RB", "RC")):
            raise InputError(f"0610: 0600.線路雪荷重強度[{index}]にはRB/RCが必要です")
        values = {side: transferred(f"horizontal[{10 + index}].{side}",
                                   f"0600.macro_handoff_single.線路雪荷重強度[{index}].R{side}",
                                   force[f"R{side}"], "VBA Single", "kN") for side in ("B", "C")}
        horizontal.append({"case": 11 + index, "id": case["id"], "label": case["label"],
                           **values, "total": values["B"] + values["C"], "source_row": None})
    for identifier, label, condition, loads in (
        (22, "雪荷重30年 S30", "30年確率・列車なし", snow),
        (23, "安全性 LR + S30", "安全性・列車なし", horizontal[10]),
        (24, "復旧性 LR + S30", "復旧性・列車なし", horizontal[11]),
    ):
        basics.append({"id": identifier, "source_row": None, "label": label, "condition": condition,
                       "track": "", "spring_case": 1, "loads": loads})
    _extend_snow_combinations(combinations)
    return transfers


def _extend_snow_combinations(combinations: list[dict[str, Any]]) -> None:
    for combination in combinations:
        combination["coefficients"].extend((0.0, 0.0, 0.0))
    for scope, first in (("body", 13), ("foundation", 9)):
        for offset, safety in enumerate((True, False)):
            coefficients = [0.0] * 24
            coefficients[:2] = (1.1, 1.2) if safety else (1.0, 1.0)
            coefficients[21] = coefficients[22 if safety else 23] = 1.0
            combinations.append({"scope": scope, "id": first + offset, "source_column": None,
                                 "title": ("安全性" if safety else "復旧性") + " LR + S30（列車・水位なし）",
                                 "coefficients": coefficients})


def _frame(c: dict[str, Any]) -> None:
    c.update(L82=c["U9"] + c["U8"], L83=c["U10"], L84=0.0)
    c["L81"] = c["L82"] + c["U7"] + c["U6"] + c["U5"]
    for row in range(81, 85):
        c[f"F{row}"], c[f"I{row}"] = row - 80, 0.0
    c.update({f"A{row}": "" if row <= 84 else "×" for row in range(82, 88)})
    c.update(I92=c["M9"], P92=c["E9"])
    c.update(O93=c["I92"], S93=c["P92"], O94=1.0, Q94=12.0, S94=c["I92"], W94=c["P92"], Z94=3.0)
    c["AB93"] = R(c["O93"] * c["S93"], 3)
    c["AB94"] = R(c["O94"] / c["Q94"] * c["S94"] * c["W94"] ** c["Z94"], 5)
    if c["AB93"] <= 0 or c["AB94"] <= 0:
        raise InputError("0610: 丸め後の柱断面積・断面二次モーメントは正値が必要です")
    # Source constants for the inactive pile branch remain auditable in JSON.
    c.update(J101=1.1, U102=2.0, W102=3.0, U103=4.0, W103=3.0,
             M107=24.0, M108=2.5, Q108=10.0, S108=7.0,
             M110=24.0, M111=2.5, Q111=10.0, S111=7.0,
             M113=30.0, T113=0.8, M114=2.8, Q114=0.8, AA114=10.0, AC114=7.0,
             S149=8.0, S150=8.0, S151=243952.0, S152=0.0, S153=2.8, S154=6.0, S155=10.0, S156=50.0)
    c.update(R102=c["J101"], R103=c["J101"])
    c["AB102"] = R((math.pi / 4) * c["R102"] ** c["U102"] * c["W102"], 3)
    c["AB103"] = R((math.pi / 64) * c["R103"] ** c["U103"] * c["W103"], 5)
    c["W113"], c["W114"] = R(c["M113"] * c["T113"], 1), R(c["M114"] * c["Q114"], 2)


def _loads(c: dict[str, Any], f: dict[str, Any]) -> None:
    c.update(J18=f["E9"], N18=f["M9"], R18=c["AC4"])
    c["AB18"] = R(c["J18"] * c["N18"] * c["R18"], 2)
    for nrow, moment_row in ((21, 22), (42, 43), (62, 63), (67, 68), (72, 73)):
        c[f"J{moment_row}"] = c[f"AB{nrow}"]
        c[f"AB{moment_row}"] = R(c[f"J{moment_row}"] * c[f"P{moment_row}"], 2)
        c[f"A{nrow}"] = ""
        c[f"A{moment_row}"] = "×" if c[f"AB{moment_row}"] == 0 else ""
    c.update(J23=f["U9"] + f["U8"], N23=f["M10"] + f["M11"] + f["M12"], R23=c["AC5"])
    c.update(J24=f["U9"], N24=c["N23"], R24=c["R23"])
    for row, height in ((44, c["R4"] + f["U8"]), (45, c["R4"]),
                        (46, c["R5"] + f["U8"]), (47, c["R5"])):
        c.update({f"J{row}": height, f"N{row}": c["N24"], f"R{row}": c["AC6"]})
    for row, height in ((64, c["R6"]), (69, c["R7"]), (74, c["R8"])):
        c.update({f"J{row}": height, f"N{row}": c["N47"], f"R{row}": -10.0})
    for row in (23, 24, 44, 45, 46, 47, 64, 69, 74):
        c[f"AB{row}"] = R(c[f"J{row}"] * c[f"N{row}"] * c[f"R{row}"], 2)
        c[f"A{row}"] = "×"

    c.update(T29=-c["E5"], T30=c["E6"])
    for row in range(29, 33):
        c[f"Y{row}"] = R(c[f"T{row}"] * c[f"M{row}"], 2)
    for row in (31, 32):
        c[f"A{row}"] = "×" if c[f"M{row}"] == 0 else ""
    c["M33"] = sum(c[f"M{row}"] for row in range(29, 33))
    c["Y33"] = sum(c[f"Y{row}"] for row in range(29, 33))
    c.update(L35=c["M33"], R35=c["AB18"], W35=f["U5"] + f["U6"])
    c["AB35"], c["AB36"] = R(c["L35"] - c["R35"] * c["W35"], 2), c["Y33"]
    for first in (52, 83, 91, 99, 112, 120):
        for row, arm in ((first, c["T29"]), (first + 1, c["T30"])):
            c[f"T{row}"] = arm
            c[f"Y{row}"] = R(c[f"T{row}"] * c[f"M{row}"], 2)
        c[f"M{first + 2}"] = c[f"M{first}"] + c[f"M{first + 1}"]
        c[f"Y{first + 2}"] = c[f"Y{first}"] + c[f"Y{first + 1}"]
    for row in range(131, 141):
        c[f"AC{row}"] = c[f"U{row}"] + c[f"Y{row}"]

    c.update(P151=1.0, M156=c["M31"])
    c["Y156"] = R(c["T156"] * c["M156"], 2)
    for row in range(153, 158):
        c[f"A{row}"] = "×" if c["M156"] == 0 else ""
    for row, b, w in ((160, f["E4"], f["M4"]),
                      (162, f["E4"] - f["E7"] - f["E8"], f["M4"] - f["M7"] - f["M8"]),
                      (164, f["E9"], f["M9"])):
        c.update({f"N{row}": b, f"R{row}": w, f"V{row}": c["AC4"]})
        c[f"AB{row}"] = R(c[f"N{row}"] * c[f"R{row}"] * c[f"V{row}"], 2)
    c["A162"] = c["A163"] = "×" if c["AB162"] == c["AB164"] else ""
    c.update(J169=c["AB21"], P169=c["AC5"], S170=c["AC5"], W170=c["AC7"])
    c["AB170"] = R(c["J169"] / c["P169"] * (c["S170"] - c["W170"]), 2)


def _load_groups(c: dict[str, Any]) -> tuple[dict, list, dict]:
    def force_moment(n: str, moment: str) -> dict:
        return {"N": c[n], "M": c[moment], "source_cells": {"N": n, "M": moment}}

    def two_supports(first: int) -> dict:
        return {**force_moment(f"M{first + 2}", f"Y{first + 2}"),
                "B": {"N": c[f"M{first}"], "arm": c[f"T{first}"], "M": c[f"Y{first}"]},
                "C": {"N": c[f"M{first + 1}"], "arm": c[f"T{first + 1}"], "M": c[f"Y{first + 1}"]}}

    vertical = {
        "fixed": {"column": {"intensity": c["AB18"], "source_cell": "AB18"},
                  "top": force_moment("AB35", "AB36"), "footing": force_moment("AB21", "AB22")},
        "additional": {"top": two_supports(52), "soil": force_moment("AB42", "AB43")},
        "water": {name: force_moment(f"AB{row}", f"AB{row + 1}")
                  for name, row in (("high", 62), ("normal", 67), ("low", 72))},
        "train": {name: two_supports(row) for name, row in (("ultimate", 83), ("service", 91), ("earthquake", 99))},
        "impact": {name: two_supports(row) for name, row in (("ultimate", 112), ("service", 120))},
    }
    horizontal_labels = ("使用性 0.8LR", "使用性 1.0LR", "安全性 1.0B", "安全性 1.1B",
                         "安全性 1.0LR+1.0B", "安全性 1.1LR+1.0B", "安全性 1.0LR+1.1B",
                         "復旧性 1.0LR+1.0B", "桁荷重慣性力 Kh=1.00", "列車荷重慣性力 Kh=0.20")
    horizontal = [{"case": index + 1, "label": label, "B": c[f"U{131 + index}"],
                   "C": c[f"Y{131 + index}"], "total": c[f"AC{131 + index}"], "source_row": 131 + index}
                  for index, label in enumerate(horizontal_labels)]
    inertia = {"Kh": c["P151"], "pedestal": {"H": c["M156"], "height": c["T156"], "M": c["Y156"]},
               "beam_top": c["AB160"], "beam_bottom": c["AB162"], "column": c["AB164"],
               "footing": c["AB170"], "source_cells": {"pedestal_H": "M156", "pedestal_M": "Y156",
                  "beam_top": "AB160", "beam_bottom": "AB162", "column": "AB164", "footing": "AB170"}}
    return vertical, horizontal, inertia


def _combinations(c: dict[str, Any], vertical: dict, horizontal: list, inertia: dict) -> tuple[list, list]:
    groups = [vertical["fixed"], vertical["additional"],
              *[vertical["water"][name] for name in ("high", "normal", "low")],
              *[vertical["train"][name] for name in ("ultimate", "service")],
              *[vertical["impact"][name] for name in ("ultimate", "service")],
              *horizontal[:8], vertical["train"]["earthquake"], *horizontal[8:], inertia]
    basic_cases = []
    for index, ((row, label, condition, track, spring), loads) in enumerate(zip(BASIC_ROWS, groups), 1):
        c.update({f"G{row}": index, f"I{row}": label, f"R{row}": condition,
                  f"Z{row}": track, f"AC{row}": spring})
        basic_cases.append({"id": index, "source_row": row, "label": label, "condition": condition,
                            "track": track, "spring_case": spring, "loads": loads})
    combinations = []
    for scope, identifier, column, title, coefficients in COMBINATION_ROWS:
        c[f"{column}7"] = identifier
        c.update({f"{column}{row}": value for row, value in zip(range(11, 32), coefficients)})
        combinations.append({"scope": scope, "id": identifier, "source_column": column,
                             "title": title, "coefficients": list(coefficients)})
    return basic_cases, combinations
