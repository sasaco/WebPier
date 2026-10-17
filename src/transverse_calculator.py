"""Physical nonseismic 0620 actions and an independent legacy audit entrypoint.

The legacy functions below preserve historical cells and mixed-unit sums solely
for the existing workbook oracle. Public actions do not call that calculation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
import math
from typing import Any

from .calculator import vba_single
from .foundation_springs import foundation_spring_set
from .frame_model import build_frame_model
from .inputs import InputError
from .longitudinal_design_conditions import LongitudinalDesignConditions
from .reaction_inputs import ReactionInput
from .reaction_math import excel_round as R
from .transverse_combinations import BASIC_ROWS, COMBINATION_ROWS, SOURCE_SHA256


def calculate_transverse(inputs: ReactionInput, foundation: dict, reactions: dict, *,
                         design_conditions: LongitudinalDesignConditions) -> dict[str, Any]:
    """Build the nonseismic Example2 model from physical, usage-aware actions."""
    from .transverse_actions import build_transverse_actions, resolve_transverse_combinations
    from .transverse_example2_cases import build_case_model

    if not isinstance(design_conditions, LongitudinalDesignConditions):
        raise InputError("0620.design_conditions: 部位別の材料条件が必要です")
    try:
        _validate(inputs, foundation, reactions)
        springs = foundation_spring_set(foundation, "transverse")
        frame = _normal_frame(inputs, reactions, springs, design_conditions)
        actions = build_transverse_actions(inputs, reactions, frame=frame)
        case_model = build_case_model(ultimate_factor=inputs.train.factors_ultimate,
                                      service_factor=inputs.train.factors_service)
        for basic in case_model["basic_cases"]:
            basic["loads"] = actions[basic["key"]]
            basic["status"] = "calculated_group"
        case_model["combinations"] = resolve_transverse_combinations(
            inputs, reactions, frame, actions, case_model)
        result = {"schema_version": 2, "stage": "0620", "input": asdict(inputs),
                  "design_conditions": asdict(design_conditions), "frame": frame,
                  "actions": actions, **case_model,
                  "units": {"length": "m", "force": "kN", "moment": "kN m",
                            "area": "m2", "inertia": "m4", "line_load": "kN/m"},
                  "provenance": {
                      "reference_document": ".claude/docs/Example橋脚2/09_直角.pdf",
                      "dependencies": ["current input", "0500.long_term", "0500.short_term",
                                       "0600.train.raw_reactions", "0600.train.pier",
                                       "0600.macro_handoff_single"],
                      "scope": "nonseismic actions and case references; no structural response solver",
                      "wind_policy": "Current adjusted input and wind H/M preserved; Example moment difference accepted",
                      "impact_policy": "Usage-specific upstream pier coefficient preserved; effective load factor applied once",
                      "material_policy": "Existing part inputs and RcDan interpolation; equivalent body sections unchanged",
                  },
                  "legacy_audit": {"entrypoint": "calculate_transverse_legacy",
                                   "source_workbook": ".claude/docs/Example橋脚/0620_直角方向荷重.xls",
                                   "source_sha256": SOURCE_SHA256,
                                   "public_actions_use_legacy_selection": False},
                  "warnings": list(inputs.warnings)}
        _finite(result)
        return result
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError(f"0620直角方向荷重: 入力または計算結果が数値範囲を超えています（{exc}）") from exc


def _normal_frame(inputs: ReactionInput, reactions: dict, springs: dict,
                  conditions: LongitudinalDesignConditions) -> dict:
    g = inputs.geometry
    top = g.h2 + g.h3 + g.h4 + g.h5 + g.h6
    footing_top = g.h5 + g.h6
    handoff = reactions["macro_handoff_single"]
    section = {"width": g.b6, "depth": g.w6, "area": R(g.b6 * g.w6, 3),
               "inertia": R(g.b6 * g.w6 ** 3 / 12, 5), "footing": "rigid"}
    materials = {name: asdict(getattr(conditions, name)) for name in ("beam", "column", "footing")}
    base = {"nodes": [{"id": identifier, "x": 0.0, "y": y, "source_row": 78 + identifier}
                      for identifier, y in ((1, top), (2, footing_top),
                                            (3, handoff["フーチング"]["hG"]), (4, 0.0))],
            "shape_eccentricity": handoff["柱"]["xC"], "section": section,
            "materials": {"body": materials["column"], **materials}, "springs": springs["terms"]}
    frame = build_frame_model(asdict(g), base, "w")
    frame["materials"] = materials
    for member in frame["members"]:
        member["material_ref"] = ("beam" if member["region"] in ("h2", "h3") else "column") \
            if member["behavior"] == "elastic" else None
    frame["spring_provenance"] = {"direction": "transverse", "support_node_id": frame["support_node_id"],
                                  "components": springs["components"]}
    return frame


def calculate_transverse_legacy(inputs: ReactionInput, foundation: dict, reactions: dict) -> dict[str, Any]:
    """Audit the historical Single spring handoff without changing its oracle."""
    return _calculate(inputs, foundation, reactions, spring_set=None)


def _calculate(inputs: ReactionInput, foundation: dict, reactions: dict,
               *, spring_set: dict | None) -> dict[str, Any]:
    """Share the load equations and current-input single-track selection."""
    try:
        _validate(inputs, foundation, reactions)
        cells, transfers = _prepare(inputs, foundation, reactions, spring_set=spring_set)
        selection = _select_current(inputs, cells["荷重計算"])
        return _finish(inputs, foundation, reactions, cells, transfers,
                       selection["factors_B"], selection["factors_C"], selection,
                       spring_set=spring_set)
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError(f"0620直角方向荷重: 入力または計算結果が数値範囲を超えています（{exc}）") from exc


def _select_current(inputs: ReactionInput, c: dict) -> dict:
    # AD181 uses the undistributed upstream force, so its value is independent
    # of all candidate rates. Populate the current table before the VBA loop.
    _train_tables(c, (0.0,) * 10, (0.0,) * 10)
    md1, md2, ml = (vba_single(c[address]) for address in ("AB68", "AA104", "AD181"))
    score = vba_single(vba_single(ml + md1) + md2)
    key, key_score = 0, 0.0
    candidates = []
    for index in range(4):
        sums = {}
        for side, bearings in (("B", inputs.dead.b), ("C", inputs.dead.c)):
            total = 0.0
            for bearing in bearings:
                total = vba_single(total + vba_single(bearing.factors[index]))
            sums[side] = total
        eligible = sums["C"] > 0
        adopted = eligible and score >= key_score
        if adopted:
            key, key_score = index + 1, score
        candidates.append({"index": index + 1, "source_row": f"L{index + 1}",
                           "sum_B_single": sums["B"], "sum_C_single": sums["C"],
                           "eligible": eligible, "score_single": score, "adopted_during_scan": adopted,
                           "winner_after": key})
    def selected(bearings: tuple) -> tuple:
        return tuple(row.factors[key - 1] if key else row.d2 for row in bearings)
    return {"policy": "current_input", "evaluation_state": "current_input",
            "selected_index": key, "key_score_single": key_score,
            "MD1_single": md1, "MD2_single": md2, "ML_single": ml,
            "candidates": candidates, "factors_B": selected(inputs.dead.b), "factors_C": selected(inputs.dead.c),
            "fallback_to_d2": key == 0, "source_row": f"L{key}" if key else "prior_D2",
            "source_unit": "1" if key else "kN", "destination_unit": "1"}


def _finite(value: Any, path: str = "0620") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not math.isfinite(value):
        raise InputError(f"{path}: 有限の数値が必要です")


def _source_sum(values: Iterable[float]) -> float:
    """Match Excel's source range order, without Python 3.12+ compensated sum."""
    total = 0.0
    for value in values:
        total += value
    return total


def _validate(inputs: ReactionInput, foundation: dict, reactions: dict) -> None:
    _finite(asdict(inputs), "0620入力")
    if inputs.geometry.unit_weight_footing <= 0:
        raise InputError("0620: フーチングの単位体積重量は正値が必要です")
    hashes = [result.get("provenance", {}).get("input_sha256") for result in (foundation, reactions)]
    if all(hashes) and hashes[0] != hashes[1]:
        raise InputError("0620: 0500と0600の入力SHA256が一致しません")


def _prepare(inputs: ReactionInput, foundation: dict, reactions: dict,
             *, spring_set: dict | None) -> tuple[dict, list]:
    """Transfer current values; leave the single-track choice to the caller."""
    geometry, handoff = inputs.geometry, reactions["macro_handoff_single"]
    cells: dict[str, dict[str, Any]] = {name: {} for name in ("骨組図", "荷重計算", "荷重図", "荷重組合せ")}
    transfers = []

    def transfer(sheet: str, cell: str, source: str, value: Any,
                 precision: str = "Double", unit: str = "m") -> None:
        cells[sheet][cell] = value
        transfers.append({"sheet": sheet, "cell": cell, "source": source,
                          "value": value, "precision": precision, "unit": unit})

    for prefix, column, count in (("b", "E", 9), ("w", "M", 9), ("h", "U", 6)):
        for index in range(1, count + 1):
            field = f"{prefix}{index}"
            transfer("骨組図", f"{column}{index + 3}", f"input.geometry.{field}", getattr(geometry, field))
    transfer("骨組図", "B16", "input.下部構造.杭種.選択値", "直接基礎", "text", "")
    for component, field, cell in (("柱", "xC", "M13"), ("フーチング", "hG", "U10")):
        transfer("骨組図", cell, f"0600.macro_handoff_single.{component}.{field}", handoff[component][field], "VBA Single")
    spring_components = ({(item["term"], item["component"]): item for item in spring_set["components"]}
                         if spring_set is not None else None)
    for column, term in (("L", "long_term"), ("T", "short_term")):
        for row, spring in ((142, "Kv"), (143, "Ks"), (144, "Kr")):
            if spring_components is None:
                transfer("骨組図", f"{column}{row}", f"0500.macro_handoff_single.{term}.{spring}",
                         foundation["macro_handoff_single"][term][spring], "VBA Single", "kN m/rad" if spring == "Kr" else "kN/m")
            else:
                component = spring_components[term, spring]
                transfer("骨組図", f"{column}{row}", component["source_path"], component["value"],
                         component["precision"], component["unit"])
    _frame(cells["骨組図"])

    for field, cell, unit in (("df1", "K18", "m"), ("df2", "K19", "m"),
                              ("hw1", "K20", "m"), ("hw2", "K21", "m"), ("hw3", "K22", "m"),
                              ("unit_weight_body", "V18", "kN/m3"), ("unit_weight_footing", "V19", "kN/m3"),
                              ("unit_weight_soil", "V20", "kN/m3"), ("unit_weight_displaced_soil", "V21", "kN/m3")):
        transfer("荷重計算", cell, f"input.geometry.{field}", getattr(geometry, field), unit=unit)
    for side, bearings, position_column, factor_column, d1_first, d2_first in (
        ("B", inputs.dead.b, "G", "J", 43, 84), ("C", inputs.dead.c, "Y", "AB", 53, 94),
    ):
        for index, bearing in enumerate(bearings):
            source = f"input.dead.{side.lower()}[{index}]"
            transfer("荷重計算", f"{position_column}{index + 5}", f"{source}.position", bearing.position)
            transfer("荷重計算", f"O{d1_first + index}", f"{source}.d1", bearing.d1, unit="kN")
            transfer("荷重計算", f"O{d2_first + index}", f"{source}.d2", bearing.d2, unit="kN")
            transfer("荷重計算", f"{factor_column}{index + 5}", f"0600.macro_handoff_single.複線分担率[{index}].R{side}",
                     handoff["複線分担率"][index][f"R{side}"], "VBA Single", "1")
    for component, ncell, xcell in (("フーチング", "AB35", "P36"), ("桁受け", "O63", "V63"),
                                   ("はり", "O64", "V64"), ("上載土", "AB74", "P75"),
                                   ("高水位", "AB112", "P113"), ("平水位", "AB117", "P118"),
                                   ("低水位", "AB122", "P123")):
        for field, cell, unit in (("N", ncell, "kN"), ("xC", xcell, "m")):
            transfer("荷重計算", cell, f"0600.macro_handoff_single.{component}.{field}", handoff[component][field], "VBA Single", unit)
    transfer("荷重計算", "T363", "0600.macro_handoff_single.桁受け.hG", handoff["桁受け"]["hG"], "VBA Single")
    for kind, group, track, first in (("列車荷重", "安全性", "複線", 134), ("列車荷重", "使用性", "単線", 161),
                                     ("衝撃荷重", "安全性", "複線", 218), ("衝撃荷重", "使用性", "単線", 245)):
        for offset, side in ((0, "RB"), (10, "RC")):
            transfer("荷重計算", f"M{first + offset}", f"0600.macro_handoff_single.{kind}.{group}.{track}.{side}",
                     handoff[kind][group][track][side], "VBA Single", "kN")
    for side, row in (("RB", 188), ("RC", 198)):
        transfer("荷重計算", f"M{row}", f"0600.macro_handoff_single.地震列車.{side}", handoff["地震列車"][side], "VBA Single", "kN")
    for index in range(8):
        for side, force_column, height_column in (("RB", "P", "T"), ("RC", "X", "AB")):
            for group, column, unit in (("直角荷重強度", force_column, "kN"), ("直角荷重位置", height_column, "m")):
                transfer("荷重計算", f"{column}{275 + index}", f"0600.macro_handoff_single.{group}[{index}].{side}",
                         handoff[group][index][side], "VBA Single", unit)
    _dead_environment(cells["荷重計算"], cells["骨組図"])
    return cells, transfers


def _frame(c: dict) -> None:
    c.update(L80=c["U9"] + c["U8"], L81=c["U10"], L82=0.0)
    c["L79"] = c["L80"] + c["U7"] + c["U6"] + c["U5"]
    for row in range(79, 83):
        c[f"F{row}"], c[f"I{row}"] = row - 78, 0.0
    c.update({f"A{row}": "" if row <= 82 else "×" for row in range(80, 86)})
    c.update(I90=c["E9"], P90=c["M9"])
    c.update(O91=c["I90"], S91=c["P90"], O92=1.0, Q92=12.0, S92=c["I90"], W92=c["P90"], Z92=3.0)
    c["AB91"] = R(c["O91"] * c["S91"], 3)
    c["AB92"] = R(c["O92"] / c["Q92"] * c["S92"] * c["W92"] ** c["Z92"], 5)
    if c["AB91"] <= 0 or c["AB92"] <= 0:
        raise InputError("0620: 丸め後の柱断面積・断面二次モーメントは正値が必要です")
    c.update(J99=1.1, U100=2.0, W100=3.0, U101=4.0, W101=3.0,
             M105=25.0, M106=2.5, Q106=10.0, S106=7.0, M108=25.0, M109=2.5, Q109=10.0, S109=7.0,
             M111=30.0, T111=0.8, M112=2.8, Q112=0.8, AA112=10.0, AC112=7.0,
             S147=8.0, S148=8.0, S149=243952.0, S150=0.0, S151=2.8, S152=6.0, S153=10.0, S154=50.0)
    c.update(R100=c["J99"], R101=c["J99"])
    c["AB100"] = R((math.pi / 4) * c["R100"] ** c["U100"] * c["W100"], 3)
    c["AB101"] = R((math.pi / 64) * c["R101"] ** c["U101"] * c["W101"], 5)
    c["W111"], c["W112"] = R(c["M111"] * c["T111"], 1), R(c["M112"] * c["Q112"], 2)


def _dead_environment(c: dict, f: dict) -> None:
    c.update(J32=f["M9"], N32=f["E9"], R32=c["V18"])
    c["AB32"] = R(c["J32"] * c["N32"] * c["R32"], 2)
    for nrow, mrow in ((35, 36), (74, 75), (112, 113), (117, 118), (122, 123)):
        c[f"J{mrow}"] = c[f"AB{nrow}"]
        c[f"AB{mrow}"] = R(c[f"J{mrow}"] * c[f"P{mrow}"], 2)
        c[f"A{nrow}"], c[f"A{mrow}"] = "", "×" if c[f"AB{mrow}"] == 0 else ""
    c.update(J37=f["U9"] + f["U8"], N37=f["E10"] + f["E11"] + f["E12"], R37=c["V19"])
    c.update(J38=f["U9"], N38=c["N37"], R38=c["R37"])
    for row, height in ((76, c["K18"] + f["U8"]), (77, c["K18"]), (78, c["K19"] + f["U8"]), (79, c["K19"])):
        c.update({f"J{row}": height, f"N{row}": c["N38"], f"R{row}": c["V20"]})
    for row, height in ((114, c["K20"]), (119, c["K21"]), (124, c["K22"])):
        c.update({f"J{row}": height, f"N{row}": c["N79"], f"R{row}": -10.0})
    for row in (37, 38, 76, 77, 78, 79, 114, 119, 124):
        c[f"AB{row}"] = R(c[f"J{row}"] * c[f"N{row}"] * c[f"R{row}"], 2)
        c[f"A{row}"] = "×"
    for index in range(10):
        # Excel arithmetic cell references convert a blank position to zero.
        arm = c[f"G{5 + index}"] or 0.0
        for first in (43, 53, 84, 94):
            c[f"V{first + index}"] = arm
    for row in (*range(43, 65), *range(84, 104)):
        c[f"AA{row}"] = R(c[f"V{row}"] * c[f"O{row}"], 2)
        c[f"A{row}"] = "×" if c[f"O{row}"] == 0 else ""
    for first, end, total in ((43, 65, 65), (84, 104, 104)):
        for column in ("O", "AA"):
            c[f"{column}{total}"] = _source_sum(c[f"{column}{row}"] for row in range(first, end))
    c.update(L67=c["O65"], R67=c["AB32"], W67=f["U5"] + f["U6"])
    c["AB67"], c["AB68"] = R(c["L67"] - c["R67"] * c["W67"], 2), c["AA65"]
    _horizontal_inertia(c, f)


def _train_tables(c: dict, single_b: tuple[float, ...], single_c: tuple[float, ...]) -> dict:
    """Evaluate the five actual source tables for an explicitly selected rate."""
    for index, (b, side_c) in enumerate(zip(single_b, single_c), 5):
        c[f"M{index}"] = c[f"P{index}"] = b
        c[f"AE{index}"] = c[f"AH{index}"] = side_c
    tables = {}
    for name, first, columns in (("train_ultimate", 134, ("J", "AB")), ("train_service", 161, ("M", "AE")),
                                  ("train_earthquake", 188, ("P", "AH")), ("impact_ultimate", 218, ("J", "AB")),
                                  ("impact_service", 245, ("M", "AE"))):
        details = []
        for side_index, column in enumerate(columns):
            for index in range(10):
                row = first + side_index * 10 + index
                c[f"M{row}"] = c[f"M{first + side_index * 10}"]
                c[f"R{row}"] = c[f"{column}{index + 5}"]
                c[f"V{row}"] = R(c[f"M{row}"] * c[f"R{row}"], 2)
                c[f"Z{row}"] = c[f"V{84 + side_index * 10 + index}"]
                c[f"AD{row}"] = R(c[f"Z{row}"] * c[f"M{row}"], 2)
                c[f"A{row}"] = "×" if c[f"V{row}"] == 0 else ""
                details.append({"side": "B" if side_index == 0 else "C", "bearing": index + 1, "source_row": row,
                                "upstream_N": c[f"M{row}"], "factor": c[f"R{row}"], "N": c[f"V{row}"],
                                "arm": c[f"Z{row}"], "source_M": c[f"AD{row}"]})
        total_row = first + 20
        # Preserve the original rectangular SUM's row-major operand order.
        c[f"V{total_row}"] = _source_sum(c[f"{column}{row}"] for row in range(first, total_row) for column in ("V", "Z", "AD"))
        c[f"AD{total_row}"] = _source_sum(c[f"AD{row}"] for row in range(first, total_row))
        tables[name] = {"rows": details, "source_total_row": total_row,
                        "compatibility_total": c[f"V{total_row}"], "compatibility_total_unit": None,
                        "distributed_force_sum": sum(row["N"] for row in details),
                        "arm_sum": sum(row["arm"] for row in details),
                        "source_moment_sum": c[f"AD{total_row}"]}
    return tables


def _horizontal_inertia(c: dict, f: dict) -> None:
    for row in range(275, 278):
        c[f"A{row}"] = "" if c[f"P{row}"] > 0 and c[f"X{row}"] > 0 else "×"
    c.update(K294=c["P278"], P294=c["X278"], K296=c["P278"], P296=c["T278"], R297=c["X278"], W297=c["AB278"])
    c["AB294"], c["AB297"] = c["K294"] + c["P294"], c["K296"] * c["P296"] + c["R297"] * c["W297"]
    for source, hrow, first, second in ((279, 307, 309, 310), (280, 322, 324, 325),
                                      (281, 338, 340, 341), (282, 350, 352, 353)):
        c.update({f"L{hrow}": c[f"P{source}"], f"Q{hrow}": c[f"X{source}"],
                  f"L{first}": c[f"P{source}"], f"Q{first}": c[f"T{source}"],
                  f"R{second}": c[f"X{source}"], f"W{second}": c[f"AB{source}"]})
        c[f"AB{hrow}"] = c[f"L{hrow}"] + c[f"Q{hrow}"]
        c[f"AB{second}"] = c[f"L{first}"] * c[f"Q{first}"] + c[f"R{second}"] * c[f"W{second}"]
    c.update(Q303=1.5, Q318=3.0, P334=1.0, P346=0.3, P358=1.0)
    c.update(O314=c["Q303"], R314=f["E9"], O329=c["Q318"], R329=f["E9"])
    c["AB314"], c["AB329"] = c["O314"] * c["R314"], c["O329"] * c["R329"]
    c["M363"] = c["O63"]
    c["Y363"] = R(c["T363"] * c["M363"], 2)
    c.update({f"A{row}": "×" if c["M363"] == 0 else "" for row in range(360, 365)})
    for row, width, depth in ((367, f["M4"], f["E4"]),
                              (369, f["M4"] - f["M7"] - f["M8"], f["E4"] - f["E7"] - f["E8"]),
                              (371, f["M9"], f["E9"])):
        c.update({f"N{row}": width, f"R{row}": depth, f"V{row}": c["V18"]})
        c[f"AB{row}"] = R(c[f"N{row}"] * c[f"R{row}"] * c[f"V{row}"], 2)
    c["A369"] = c["A370"] = "×" if c["AB369"] == c["AB371"] else ""
    c.update(J376=c["AB35"], P376=c["V19"], S377=c["V19"], W377=c["V21"])
    c["AB377"] = R(c["J376"] / c["P376"] * (c["S377"] - c["W377"]), 2)


def _groups(c: dict, tables: dict) -> tuple[dict, list, list, dict]:
    def pair(n: str, moment: str) -> dict:
        return {"N": c[n], "M": c[moment], "source_cells": {"N": n, "M": moment}}

    dead_rows = {name: [{"side": "B" if index < 10 else "C", "bearing": index % 10 + 1,
                         "N": c[f"O{row}"], "arm": c[f"V{row}"], "M": c[f"AA{row}"], "source_row": row}
                        for index, row in enumerate(range(first, first + 20))]
                 for name, first in (("D1", 43), ("D2", 84))}
    vertical = {"fixed": {"rows": dead_rows["D1"], "column": {"intensity": c["AB32"], "source_cell": "AB32"},
                           "top": pair("AB67", "AB68"), "footing": pair("AB35", "AB36"),
                           "pedestal": pair("O63", "AA63"), "beam": pair("O64", "AA64")},
                "additional": {"rows": dead_rows["D2"], "top": pair("O104", "AA104"), "soil": pair("AB74", "AB75")},
                "water": {name: pair(f"AB{row}", f"AB{row + 1}") for name, row in (("high", 112), ("normal", 117), ("low", 122))},
                "train": {name: tables[f"train_{name}"] for name in ("ultimate", "service", "earthquake")},
                "impact": {name: tables[f"impact_{name}"] for name in ("ultimate", "service")}}
    labels = ("遠心荷重 安全性", "遠心荷重 使用性", "遠心荷重 疲労", "車両横荷重", "風荷重 列車あり",
              "風荷重 列車なし", "桁荷重慣性力 Kh=1.00", "列車荷重慣性力 Kh=0.30")
    horizontal = [{"id": index + 1, "label": label, "source_row": row,
                   "B": {"H": c[f"P{row}"], "height": c[f"T{row}"]},
                   "C": {"H": c[f"X{row}"], "height": c[f"AB{row}"]},
                   "status": "unconnected_source_load" if index < 3 else "aggregated"}
                  for index, (label, row) in enumerate(zip(labels, range(275, 283)))]
    aggregates = [{"id": index + 4, "label": labels[index + 3], "H": c[f"AB{hrow}"], "M": c[f"AB{mrow}"],
                   "source_cells": {"H": f"AB{hrow}", "M": f"AB{mrow}"}}
                  for index, (hrow, mrow) in enumerate(((294, 297), (307, 310), (322, 325), (338, 341), (350, 353)))]
    inertia = {"Kh": c["P358"], "pedestal": {"H": c["M363"], "height": c["T363"], "M": c["Y363"]},
               "beam_top": c["AB367"], "beam_bottom": c["AB369"], "column": c["AB371"], "footing": c["AB377"]}
    return vertical, horizontal, aggregates, inertia


def _combinations(c: dict, vertical: dict, aggregates: list, inertia: dict) -> tuple[list, list]:
    linked = {11: vertical["fixed"], 12: vertical["additional"], 13: vertical["water"]["high"],
              14: vertical["water"]["normal"], 15: vertical["water"]["low"], 16: vertical["train"]["ultimate"],
              22: vertical["impact"]["ultimate"], 28: aggregates[0], 29: aggregates[1], 30: aggregates[2],
              31: vertical["train"]["earthquake"], 32: aggregates[3], 33: aggregates[4], 34: inertia}
    basics = []
    for index, (row, printed, label, condition, track, spring) in enumerate(BASIC_ROWS, 1):
        c.update({f"F{row}": printed, f"H{row}": label, f"Q{row}": condition, f"Y{row}": track, f"AB{row}": spring})
        basic = {"id": index, "source_row": row, "printed_number": printed, "label": label, "condition": condition,
                 "track": track, "spring_case": spring, "status": "calculated_group" if row in linked else "template_row_only"}
        if row in linked:
            basic["loads"] = linked[row]
        else:
            basic["note"] = "元表の方向別・使用性複線ケースに対応する個別荷重表は未計算。選択単線の表とは区別。"
        basics.append(basic)
    combinations = []
    for index, (column, printed, title, coefficients) in enumerate(COMBINATION_ROWS, 1):
        c[f"{column}7"] = printed
        c.update({f"{column}{row}": value for row, value in zip(range(11, 35), coefficients)})
        combinations.append({"id": index, "source_column": column, "printed_number": printed,
                             "title": title, "coefficients": list(coefficients)})
    return basics, combinations


def _finish(inputs: ReactionInput, foundation: dict, reactions: dict, cells: dict, transfers: list,
            factors_b: tuple[float, ...], factors_c: tuple[float, ...], selection: dict,
            *, spring_set: dict | None) -> dict:
    """Finish common calculations for a choice whose evaluation policy is explicit."""
    c, f = cells["荷重計算"], cells["骨組図"]
    tables = _train_tables(c, factors_b, factors_c)
    for side, column, values in (("B", "M", factors_b), ("C", "AE", factors_c)):
        for index, value in enumerate(values):
            transfers.append({"sheet": "荷重計算", "cell": f"{column}{index + 5}",
                              "source": f"single_track_selection.factors_{side}[{index}]", "value": value,
                              "precision": "Double", "unit": "1", "source_unit": selection["source_unit"]})
    vertical, horizontal, aggregates, inertia = _groups(c, tables)
    basics, combinations = _combinations(cells["荷重組合せ"], vertical, aggregates, inertia)
    frame = {"nodes": [{"id": row - 78, "x": f[f"I{row}"], "y": f[f"L{row}"], "source_row": row} for row in range(79, 83)],
             "shape_eccentricity": f["M13"],
             "section": {"width": f["I90"], "depth": f["P90"], "area": f["AB91"], "inertia": f["AB92"], "footing": "rigid"},
             "materials": {"body": {"fck": 25.0, "Ec": 2.5e7}, "footing": {"fck": 25.0, "Ec": 2.5e7}},
             "springs": {term: {name: f[f"{column}{row}"] for row, name in ((142, "Kv"), (143, "Ks"), (144, "Kr"))}
                         for column, term in (("L", "long_term"), ("T", "short_term"))}}
    frame = build_frame_model(asdict(inputs.geometry), frame, "w")
    if spring_set is not None:
        frame["spring_provenance"] = {
            "direction": spring_set["direction"],
            "support_node_id": frame["support_node_id"],
            "components": [dict(item) for item in spring_set["components"]],
        }
    result = {"schema_version": 1, "stage": "0620", "input": asdict(inputs), "cells": cells, "transfers": transfers,
              "frame": frame, "vertical": vertical, "horizontal": horizontal, "horizontal_aggregates": aggregates,
              "wind_body": {"with_train": c["AB314"], "without_train": c["AB329"], "unit": "kN/m"},
              "inertia": inertia, "single_track_selection": selection, "basic_cases": basics, "combinations": combinations,
              "units": {"length": "m", "force": "kN", "moment": "kN m", "area": "m2", "inertia": "m4",
                        "line_load": "kN/m", "unit_weight": "kN/m3", "compatibility_total": None},
              "provenance": {"source_workbook": ".claude/docs/Example橋脚/0620_直角方向荷重.xls", "source_sha256": SOURCE_SHA256,
                             "source_vba": [".claude/docs/Example橋脚/wiki/evidence/vba/input/直角荷重.bas"],
                             "dependencies": ["current input", "0500.macro_handoff_single", "0600.macro_handoff_single"],
                             "method": "元セル式を明示的に再計算。実行時Excel・証拠JSON参照なし。",
                             "rounding": "元ROUND箇所の15有効桁正規化。上流Singleと最終分担率Doubleを区別。",
                             "blank_normalization": "入力の空D1/D2・分担率は既存0600のReactionInput契約どおり0に正規化。空の支承位置はNoneを保持し、参照式では0として計算。",
                             "separated_totals": "V/Z/AD別の合計は元式の説明用整理で、元式を補正した合計ではありません。D2行fallback時のV列合計は設計に使える分担率による鉛直力を表しません。",
                             "selection_policy": selection.get("policy"),
                             "selection_order": "元マクロの保存荷重による事前選択から順序変更。現在の入力・上流荷重を転記した後のMD1/MD2/MLで評価。",
                             "combination_scope": "元表係数のみ。方向別未計算行はtemplate_row_only。構造解析なし。"},
              "warnings": [*inputs.warnings,
                           *[f"0500: {item}" for item in foundation.get("warnings", [])],
                           *[f"0600: {item}" for item in reactions.get("warnings", [])],
                           "単線選択は元マクロの保存荷重による事前選択から順序変更し、現在の入力・上流荷重で評価します。他の互換式は維持します。",
                           "C側支承の荷重モーメント腕は元式どおりB側支承位置を参照します。",
                           "列車・衝撃のAD列は分担前反力×腕です。V総和は力・腕・モーメントの混合集計であり、物理量として使用しません。",
                           "遠心荷重3ケースは元表で集約・基本ケースに接続されていません。曲線半径が0という意味ではありません。",
                           "24基本行の印字番号は重複し、元表にない方向別荷重表は計算済みとして扱いません。",
                           "0620は荷重・骨組条件と元表の組合せ係数を作成し、構造解析・部材照査は実施しません。"],
              "inactive_source_cells": {"骨組図": ["AB100", "AB101", "W111", "W112", *[f"S{row}" for row in range(147, 155)]],
                                        "荷重計算": [f"AB{row}" for row in (37, 38, 76, 77, 78, 79, 114, 119, 124)]}}
    if selection["fallback_to_d2"]:
        result["warnings"].append("単線候補は採択されずkeyi=0となったため、元Range.Cells(0,c)の互換動作で現在D2行のkN値を率セルへ転記しています。正常な単線分担率の選択ではなく、該当V列合計も設計に使える分担率による鉛直力を表しません。")
    if spring_set is not None:
        result["provenance"]["dependencies"] = [
            "current input", "0500.long_term", "0500.short_term", "0600.macro_handoff_single",
        ]
        result["provenance"]["rounding"] = (
            "元ROUND箇所の15有効桁正規化。0500の線路直角方向ばねは正規Double値。"
            "0600の上流Singleと最終分担率Doubleを区別。"
        )
        result["warnings"].append("基礎ばねは0500の線路直角方向・長短期の正規Double値を使用します。")
    _finite(result)
    return result
