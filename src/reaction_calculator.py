"""Excel-independent 0600 reactions and the original VBA outgoing values."""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any

from .calculator import vba_single
from .inputs import InputError
from .moving_load import search_reactions
from .reaction_inputs import ReactionInput, SpanInput, TrainInput
from .reaction_math import excel_round as R
from .reaction_weights import calculate_dead, calculate_snow, calculate_weights


SOURCE_SHA256 = "2c46fd2db477b0de8b04fc00d6c3ad223ba356f7cc2d621ece349ed61ed46f19"
SUPPORTS = ("RA", "RB", "RC", "RD")
LONGITUDINAL_LABELS = (
    "使用性 0.8 LR (1)", "使用性 1.0 LR (2)", "安全性 1.0 B", "安全性 1.1 B",
    "安全性 1.0 LR + 1.0 B", "安全性 1.1 LR + 1.0 B", "安全性 1.0 LR + 1.1 B",
    "復旧性 1.0 LR + 1.0 B", "地震時 桁荷重", "地震時 列車荷重",
)
TRANSVERSE_LABELS = (
    "遠心荷重 安全性・復旧性", "遠心荷重 使用性", "遠心荷重 疲労", "車両横荷重",
    "風荷重 列車あり", "風荷重 列車なし", "地震時 桁荷重", "地震時 列車荷重",
)

# Resolve nominal coefficients before applying them to raw train reactions.
_COMBINATION_FIELDS = (
    "d1_factor", "d2_factor", "live_group", "live_track", "live_factor",
    "include_impact", "snow_key", "lr_factor", "brake_factor",
)
LONGITUDINAL_COMBINATIONS = tuple(dict(zip(_COMBINATION_FIELDS, values)) for values in (
    (1.0, 1.0, None, "double", 0.0, False, "雪荷重_2年確率", 0.8, 0.0),
    (1.0, 1.0, "service", "double", 1.0, True, "雪荷重_2年確率", 1.0, 0.0),
    (1.1, 1.2, "ultimate", "double", 1.1, True, "雪荷重_10年確率", 0.0, 1.0),
    (1.1, 1.2, "ultimate", "double", 1.0, True, "雪荷重_10年確率", 0.0, 1.1),
    (1.1, 1.2, "ultimate", "double", 1.1, True, "雪荷重_10年確率", 1.0, 1.0),
    (1.1, 1.2, "ultimate", "double", 1.0, True, "雪荷重_10年確率", 1.1, 1.0),
    (1.1, 1.2, "ultimate", "double", 1.0, True, "雪荷重_10年確率", 1.0, 1.1),
    (1.0, 1.0, "ultimate", "double", 1.0, True, "雪荷重_10年確率", 1.0, 1.0),
))
LONGITUDINAL_SNOW_COMBINATIONS = tuple(dict(zip(_COMBINATION_FIELDS, values)) for values in (
    (1.1, 1.2, None, "double", 0.0, False, "雪荷重_30年確率", 1.0, 0.0),
    (1.0, 1.0, None, "double", 0.0, False, "雪荷重_30年確率", 1.0, 0.0),
))


def _finite(value: Any, path: str = "0600") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not math.isfinite(value):
        raise InputError(f"{path}: 有限の計算結果が必要です")


def _girder_train_table(inputs: ReactionInput, dead: dict, raw: tuple[float, ...],
                        cells: dict[str, float]) -> dict[str, Any]:
    girder: dict[str, Any] = {}
    train = inputs.train
    spans = (inputs.spans.b, inputs.spans.c)
    factors = {"ultimate": train.factors_ultimate, "service": train.factors_service,
               "fatigue": train.factors_fatigue}
    for group, first in (("ultimate", 67), ("service", 74), ("fatigue", 81)):
        girder[group] = {"single": {}, "double": {}}
        for index, (support, column) in enumerate(zip(SUPPORTS, ("R", "V", "Z", "AD"))):
            span = spans[index // 2]
            total = dead["track_totals"]["B" if index < 2 else "C"]
            coefficient = span.impact
            double_coefficient = R(coefficient * (1 - span.span / 200), 3)
            if group != "ultimate":
                coefficient = R(coefficient * 3 / 4, 3)
                double_coefficient = R(double_coefficient * 3 / 4, 3)
            single = raw[index] * factors[group]
            double = single * total
            for track, load, coeff in (("single", single, coefficient), ("double", double, double_coefficient)):
                girder[group][track][support] = {"train": load, "coefficient": coeff, "impact": R(load * coeff, 1)}
            values = (single, coefficient, R(single * coefficient, 1), total,
                      double, double_coefficient, R(double * double_coefficient, 1))
            for row, value in enumerate(values, first):
                cells[f"{column}{row}"] = value
    return girder


def _pier_train_table(girder: dict, ds: float, du: float,
                      cells: dict[str, float]) -> dict[str, Any]:
    pier: dict[str, Any] = {}
    cells.update(U100=ds, U101=du)
    for group, first in (("ultimate", 105), ("service", 111)):
        pier[group] = {}
        for track, offset in (("single", 0), ("double", 3)):
            loads = girder[group][track]
            load_total = loads["RB"]["train"] + loads["RC"]["train"]
            denominator = load_total + du + ds
            if denominator == 0:
                raise InputError("列車荷重: 衝撃低減式の分母（列車+上部工死荷重+橋脚自重）が0です")
            reduction = 1 - ds / denominator
            pier[group][track] = {}
            for support, column in (("RB", "T"), ("RC", "X")):
                load = loads[support]["train"]
                coefficient = loads[support]["coefficient"] * reduction
                impact = R(load * coefficient, 1)
                pier[group][track][support] = {"train": load, "coefficient": coefficient, "impact": impact}
                for row, value in enumerate((load, coefficient, impact), first + offset):
                    cells[f"{column}{row}"] = value
            cells[f"AB{first + offset}"] = load_total
            cells[f"AB{first + offset + 2}"] = sum(pier[group][track][support]["impact"] for support in ("RB", "RC"))
    return pier


def _train_tables(inputs: ReactionInput, dead: dict, weights: dict,
                  raw: tuple[float, ...]) -> tuple[dict, dict[str, float]]:
    cells: dict[str, float] = {}
    train = inputs.train
    spans = (inputs.spans.b, inputs.spans.c)
    for side, span, row in zip(("B", "C"), spans, (4, 5)):
        cells.update({f"D{row}": span.l1, f"G{row}": span.span, f"J{row}": span.l2,
                      f"M{row}": dead["track_totals"][side], f"S{row}": span.impact})
    cells.update(J7=train.length, J8=train.a1, J9=train.a2, J10=train.axle_load,
                 J11=train.earthquake_load, J12=train.n, J13=train.factors_service,
                 J14=train.factors_ultimate, J15=train.factors_fatigue,
                 O45=train.factors_ultimate, O49=train.factors_service, O53=train.factors_fatigue)
    girder = _girder_train_table(inputs, dead, raw, cells)
    ds = weights["pier_bottom"]["N"]
    du = dead["points"]["B"]["total"] + dead["points"]["C"]["total"]
    pier = _pier_train_table(girder, ds, du, cells)
    earthquake = {}
    for support, span, row in zip(("RB", "RC"), spans, (57, 58)):
        whole = span.l1 + span.span + span.l2
        earthquake[support] = train.earthquake_load * whole * 0.5
        cells.update({f"N{row}": train.earthquake_load, f"R{row}": whole, f"AC{row}": earthquake[support]})
    return {"girder": girder, "pier": pier, "earthquake": earthquake,
            "raw_reactions": dict(zip(SUPPORTS, raw)), "Ds": ds, "Du": du}, cells


def _bearing_force(applied: float, remote: float, local: float, mu: float, bearing: str) -> dict[str, Any]:
    half = applied / 2
    fixed_candidate = R(applied - 0.5 * mu * remote, 2)
    movable_friction = R(mu * local, 2)
    movable_floor = R(mu * half, 2)
    fixed = max(fixed_candidate, half)
    movable = min(half, max(movable_friction, movable_floor))
    return {"force": fixed if bearing == "固定" else movable, "bearing": bearing,
            "applied": applied, "mu": mu, "remote_vertical": remote, "local_vertical": local,
            "half_applied": half, "fixed_candidate": fixed_candidate,
            "movable_friction": movable_friction, "movable_floor": movable_floor,
            "fixed_force": fixed, "movable_force": movable}


def _brake_and_start(vehicle: TrainInput, girder_length: float, reaction_total: float) -> tuple[float, float]:
    if vehicle.name == "EA-17":
        return (R((0.27 + 1 / vehicle.length) * reaction_total, 2),
                R((0.25 + 0.95 / vehicle.length) * reaction_total, 2))
    return (R((0.20 + 0.80 / vehicle.length * girder_length) * vehicle.axle_load, 2),
            R((0.19 + 0.76 / vehicle.length * girder_length) * vehicle.axle_load, 2))


def _braking_scale(vehicle: TrainInput, effective_coefficient: float) -> float:
    if vehicle.name != "EA-17":
        return effective_coefficient
    rho = vehicle.factors_ultimate
    return effective_coefficient / rho if rho > 0 else 0.0


def _resolved_combination(inputs: ReactionInput, nominal: dict) -> dict:
    combination = dict(nominal)
    rho = inputs.train.factors_ultimate
    if nominal["live_group"] == "ultimate":
        effective_live = R(rho * nominal["live_factor"], 2)
        live_scale = effective_live / rho if rho > 0 else 0.0
    else:
        live_scale = nominal["live_factor"]
        effective_live = (inputs.train.factors_service * live_scale
                          if nominal["live_group"] == "service" else live_scale)
    effective_brake = R(rho * nominal["brake_factor"], 2)
    combination.update(effective_live_coefficient=effective_live, live_scale=live_scale,
                       effective_brake_coefficient=effective_brake,
                       brake_scale=_braking_scale(inputs.train, effective_brake))
    return combination


def _longitudinal_vertical(combination: dict, dead: dict, train: dict,
                           snow: dict, support: str, track_total: float) -> float:
    vertical = (combination["d1_factor"] * dead["D1"]
                + combination["d2_factor"] * dead["D2"] + snow[combination["snow_key"]])
    if combination["live_group"] is not None:
        live = train["girder"][combination["live_group"]][combination["live_track"]][support]
        impact = live["coefficient"] if combination["include_impact"] else 0
        live_total = train["raw_reactions"][support] * track_total * (1 + impact)
        vertical += combination["effective_live_coefficient"] * live_total
    return vertical


def _longitudinal(inputs: ReactionInput, dead: dict, train: dict,
                  snow: dict) -> tuple[list[dict], dict, dict, list[dict]]:
    cells: dict[str, float] = {"K7": inputs.train.length}
    rows = [{"case": i + 1, "label": label, "source_row": 545 + i}
            for i, label in enumerate(LONGITUDINAL_LABELS)]
    for row, combination in zip(rows, LONGITUDINAL_COMBINATIONS):
        row["combination"] = _resolved_combination(inputs, combination)
    snow_rows = [
        {"id": case_id, "label": label, "combination": _resolved_combination(inputs, combination)}
        for case_id, label, combination in zip(
            ("safety_lr_s30", "recovery_lr_s30"),
            ("安全性 1.0 LR + S30", "復旧性 1.0 LR + S30"),
            LONGITUDINAL_SNOW_COMBINATIONS,
        )
    ]
    bases = {}
    # Source cells for remote/local verticals and the five branch candidates.
    vertical_cells = {
        "B": (("Z87", "Z94"), ("L133", "L142"), ("L184", "L194"), ("L237", "L247"),
              ("L295", "L305"), ("L349", "L359"), ("AC402", "AC411"), ("L454", "L464")),
        "C": (("Z106", "Z113"), ("L156", "L164"), ("L209", "L219"), ("L262", "L272"),
              ("L320", "L330"), ("L374", "L384"), ("AC425", "AC434"), ("L479", "L489")),
    }
    branch_rows = {
        "B": ((91, 92, 97, 98, 99), (137, 138, 145, 146, 147), (188, 189, 197, 198, 199),
              (241, 242, 250, 251, 252), (299, 300, 308, 309, 310), (353, 354, 362, 363, 364),
              (406, 407, 414, 415, 416), (458, 459, 467, 468, 469)),
        "C": ((110, 111, 116, 117, 118), (160, 161, 167, 168, 169), (213, 214, 222, 223, 224),
              (266, 267, 275, 276, 277), (324, 325, 333, 334, 335), (378, 379, 387, 388, 389),
              (429, 430, 437, 438, 439), (483, 484, 492, 493, 494)),
    }
    output_rows = {"B": (101, 149, 201, 254, 312, 366, 418, 471, 508, 529),
                   "C": (120, 171, 226, 279, 337, 391, 441, 496, 517, 538)}
    for side, span, remote_point, local_support, remote_support, base_row in (
        ("B", inputs.spans.b, "A", "RB", "RA", 4),
        ("C", inputs.spans.c, "D", "RC", "RD", 5),
    ):
        whole = span.l1 + span.span + span.l2
        total_tracks = dead["track_totals"][side]
        lr = R(min(10 * whole, 2000) * total_tracks, 2)
        lr_service = R(min(8 * whole, 2000) * total_tracks, 2)
        single = train["girder"]["ultimate"]["single"]
        vertical_train = single[local_support]["train"] + single[remote_support]["train"]
        brake, start = _brake_and_start(inputs.train, whole, vertical_train)
        braking = max(brake, start)
        braking_factor = _braking_scale(inputs.train, R(inputs.train.factors_ultimate, 2))
        design_braking = braking * braking_factor
        girder = "AB" if side == "B" else "CD"
        eq_dead = R(dead["girders"][girder]["total"] + snow["girders"][girder]["雪荷重_2年確率"], 2)
        eq_train = R(train["earthquake"][local_support] * 2 * 0.2, 2)
        bases[side] = {"length": whole, "track_total": total_tracks, "LR": lr,
                       "LR_service": lr_service, "brake": brake, "start": start,
                       "braking": braking, "braking_factor": braking_factor,
                       "design_braking": design_braking,
                       "braking_rule": "EA-17" if inputs.train.name == "EA-17" else "axle_and_length",
                       "train_reaction_total": vertical_train,
                       "earthquake_dead": eq_dead, "earthquake_train": eq_train}
        cells.update({f"E{base_row}": whole, f"H{base_row}": total_tracks, f"K{base_row}": span.mu})
        for row, value in zip((22, 30, 44, 50, 59, 68) if side == "B" else (24, 32, 46, 52, 61, 70),
                               (lr, lr_service, brake, start, eq_dead, eq_train)):
            cells[f"AC{row}"] = value
        for i, row in enumerate((*rows[:8], *snow_rows)):
            combination = row["combination"]
            # Preserve the service rail force's independent 2000 kN cap.
            rail_force = lr_service if combination["lr_factor"] == 0.8 else combination["lr_factor"] * lr
            brake_coefficient = combination["effective_brake_coefficient"]
            brake_scale, braking_base = combination["brake_scale"], braking
            override = row.get("case") == 8 and span.recovery_brake_coefficient is not None
            if override:
                brake_coefficient = brake_scale = span.recovery_brake_coefficient
                raw_total = train["raw_reactions"][local_support] + train["raw_reactions"][remote_support]
                braking_base = max(_brake_and_start(inputs.train, whole, raw_total))
            braking_contribution = brake_scale * braking_base
            force = rail_force + braking_contribution
            verticals = [
                _longitudinal_vertical(combination, dead["points"][point], train,
                                       snow["points"][point], support, total_tracks)
                for point, support in ((remote_point, remote_support), (side, local_support))
            ]
            detail = _bearing_force(force, *verticals, span.mu, span.bearing)
            detail.update(effective_brake_coefficient=brake_coefficient,
                          brake_scale=brake_scale, braking_base=braking_base,
                          braking_contribution=braking_contribution,
                          recovery_brake_override=override)
            row[side] = detail
            if i >= len(LONGITUDINAL_COMBINATIONS):
                continue
            for cell, value in zip(vertical_cells[side][i], verticals):
                cells[cell] = value
            for cell_row, value in zip(branch_rows[side][i], (detail["fixed_candidate"], detail["half_applied"],
                                                              detail["half_applied"], detail["movable_friction"], detail["movable_floor"])):
                cells[f"AC{cell_row}"] = value
        for i, applied_force in ((8, eq_dead), (9, eq_train)):
            rows[i][side] = {"force": applied_force if span.bearing == "固定" else applied_force / 2,
                             "applied": applied_force, "bearing": span.bearing, "mu": span.mu}
        for i, row in enumerate(rows):
            cells[f"{'T' if side == 'B' else 'X'}{545 + i}"] = row[side]["force"]
            cells[f"K{output_rows[side][i]}"] = row[side]["force"]
    return rows, bases, cells, snow_rows


def _transverse_girder_earthquake(span: SpanInput, dead: dict, snow: float) -> dict:
    force = R(dead["total"] + snow, 2)
    return {"force": force, "height": span.hs, "moment": force * span.hs}


def _transverse(inputs: ReactionInput, dead: dict, train: dict, snow: dict,
                lengths: tuple[float, ...], warnings: list[str]) -> tuple[list[dict], dict, dict, dict]:
    vehicle = inputs.train
    weighted_axle = vehicle.axle_load * vehicle.factors_ultimate
    lateral_axle = R(0.2 * weighted_axle, 2)
    if weighted_axle > 0 and lateral_axle == 0:
        raise InputError("車両横荷重: 正の荷重が小数2桁丸めで0となり、移動荷重探索を成立させられません")
    if vehicle.factors_ultimate == 0:
        warnings.append("安全性荷重修正係数0: 車両横荷重をゼロとし、元VBAの未採択エラーを回避する拡張を適用しました。")
    lateral_length = vba_single(vba_single(vba_single(vehicle.a1) + vba_single(vehicle.a2)) * 2)
    moving = search_reactions(lengths, 1, lateral_length, vehicle.a1, vehicle.a2, lateral_axle)
    cells: dict[str, float] = {"K73": weighted_axle, "S73": lateral_axle,
                              "AB87": moving.reactions[1], "AB94": moving.reactions[2]}
    rows = [{"case": i + 1, "label": label, "source_row": 185 + i} for i, label in enumerate(TRANSVERSE_LABELS)]
    parameters = {"weighted_axle": weighted_axle, "lateral_axle": lateral_axle, "lateral_car_length": lateral_length}
    for index, (side, span, support, source_row) in enumerate((("B", inputs.spans.b, "RB", 4), ("C", inputs.spans.c, "RC", 5))):
        whole = span.l1 + span.span + span.l2
        alpha = 0 if span.radius == 0 else R(span.speed**2 / (127 * span.radius), 3)
        rail_height = span.h1 + span.h2 + span.h3
        centrifugal_height = rail_height + vehicle.height_centrifugal
        wind_with = span.h2 + span.h3 + max(vehicle.height_wind, span.h4)
        wind_without = span.h2 + span.h3 + span.h4
        forces = [R(train["girder"][group]["single"][support]["train"] * alpha, 2)
                  for group in ("ultimate", "service", "fatigue")]
        forces += [moving.reactions[index + 1], R(1.5 * wind_with * whole / 2, 2),
                   R(3 * wind_without * whole / 2, 2),
                   R(dead["points"][side]["total"] + snow["points"][side]["雪荷重_2年確率"], 2),
                   R(train["earthquake"][support] * 0.3, 2)]
        heights = [centrifugal_height] * 3 + [rail_height, wind_with / 2 + span.h1,
                   wind_without / 2 + span.h1, span.hs, rail_height + vehicle.height_seismic]
        earthquake = _transverse_girder_earthquake(span, dead["points"][side],
                                                  snow["points"][side]["雪荷重_2年確率"])
        forces[6], heights[6] = earthquake["force"], earthquake["height"]
        parameters[side] = {"alpha": alpha, "rail_height": rail_height, "wind_with_train_height": wind_with,
                            "wind_without_train_height": wind_without, "radius": span.radius, "speed": span.speed}
        for i, (force, height) in enumerate(zip(forces, heights)):
            rows[i][side] = {"force": force, "height": height}
            for col, value in zip(("P", "T") if side == "B" else ("X", "AB"), (force, height)):
                cells[f"{col}{185 + i}"] = value
        rows[6][side] = earthquake
        rows[7][side]["moment"] = forces[7] * heights[7]
        base = 0 if side == "B" else 25
        cells[f"W{25 + base}"] = alpha
        cells[f"AB{30 + base}"] = centrifugal_height
        for row, force in zip((34, 38, 42), forces[:3]):
            cells[f"AB{row + base}"] = force
        force_rows = (87, 110, 132, 152, 169) if side == "B" else (94, 119, 141, 158, 175)
        height_rows = (89, 112, 134, 154, 171) if side == "B" else (96, 121, 143, 160, 177)
        for row, force in zip(force_rows, forces[3:]):
            cells[f"AB{row}"] = force
        for row, height in zip(height_rows, heights[3:]):
            cells[f"AB{row}"] = height
        cells[f"AB{108 if side == 'B' else 117}"] = wind_with
        cells[f"AB{130 if side == 'B' else 139}"] = wind_without
        for col, value in zip(("E", "H", "K", "N", "Q", "T", "W", "Z", "AC", "AF"),
                              (span.l1, span.span, span.l2, span.radius, span.speed, span.h1, span.h2, span.h3, span.h4, span.hs)):
            cells[f"{col}{source_row}"] = value
    return rows, parameters, asdict(moving), cells


def _handoff(weights: dict, dead: dict, train: dict, longitudinal: list,
             transverse: list, longitudinal_snow: list) -> dict:
    result = {name: {key: vba_single(value) for key, value in values.items()}
              for name, values in weights["components"].items()}
    result.update(列車荷重={}, 衝撃荷重={})
    for group, label in (("ultimate", "安全性"), ("service", "使用性")):
        for target, field in (("列車荷重", "train"), ("衝撃荷重", "impact")):
            result[target][label] = {
                track_label: {support: vba_single(train["pier"][group][track][support][field]) for support in ("RB", "RC")}
                for track, track_label in (("single", "単線"), ("double", "複線"))
            }
    result["地震列車"] = {support: vba_single(value) for support, value in train["earthquake"].items()}
    result["線路荷重強度"] = [{f"R{side}": vba_single(row[side]["force"]) for side in ("B", "C")} for row in longitudinal]
    result["線路雪荷重強度"] = [{f"R{side}": vba_single(row[side]["force"]) for side in ("B", "C")} for row in longitudinal_snow]
    for target, field in (("直角荷重強度", "force"), ("直角荷重位置", "height")):
        result[target] = [{f"R{side}": vba_single(row[side][field]) for side in ("B", "C")} for row in transverse]
    result["複線分担率"] = [{f"R{side}": vba_single(dead["double_track_factors"][side][i]) for side in ("B", "C")} for i in range(10)]
    return result


def calculate_reactions(inputs: ReactionInput) -> dict[str, Any]:
    """Calculate all five 0600 sheets without reading Excel or source evidence."""
    try:
        result = _calculate_reactions(inputs)
        _finite(result)
        return result
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError(f"0600反力計算: 入力または計算結果が数値範囲を超えています（{exc}）") from exc


def _calculate_reactions(inputs: ReactionInput) -> dict[str, Any]:
    _finite(asdict(inputs), "入力")
    dead = calculate_dead(inputs)
    snow = calculate_snow(inputs)
    weights = calculate_weights(inputs.geometry)
    warnings = [*inputs.warnings, *weights["warnings"],
                "列車・車両横荷重はRB+RCの共通最大載荷位置を採用します（各支点別最大ではありません）。",
                "元式の可動支承の下限制御は表示説明の0.1ではなく摩擦係数μを使用します。",
                "遠心作用方向記号は元VBAの転記対象外のため計算には使用しません。",
                "Example橋脚2/07 7-9は原本展開式を採用し、見出しをL＋Iへ整合します。",
                "Example橋脚2/07 7-11は原本展開式を採用し、見出しを側別の復旧性制動係数へ整合します。"]
    spans = (inputs.spans.b, inputs.spans.c)
    lengths = tuple(value for span in spans for value in (span.l1, span.span, span.l2))
    vehicle = inputs.train
    moving = search_reactions(lengths, vehicle.n, vehicle.length, vehicle.a1, vehicle.a2, vehicle.axle_load)
    train, train_cells = _train_tables(inputs, dead, weights, moving.reactions)
    longitudinal, longitudinal_base, longitudinal_cells, longitudinal_snow = _longitudinal(inputs, dead, train, snow)
    transverse, transverse_parameters, lateral, transverse_cells = _transverse(inputs, dead, train, snow, lengths, warnings)
    cells = {"死荷重": dead["cells"], "橋脚自重": weights["cells"], "列車荷重": train_cells,
             "線路荷重": longitudinal_cells, "直角荷重": transverse_cells}
    public_values = {
        **weights["components"],
        "列車反力": {f"{col}{row}": train_cells[f"{col}{row}"] for row in range(105, 117) for col in ("T", "X")},
        "地震列車": {"地震LB": train["earthquake"]["RB"], "地震LC": train["earthquake"]["RC"]},
        "線路荷重": {f"{col}{row}": longitudinal_cells[f"{col}{row}"] for row in range(545, 555) for col in ("T", "X")},
        "直角荷重": {f"{col}{row}": transverse_cells[f"{col}{row}"] for row in range(185, 193) for col in ("P", "T", "X", "AB")},
        "複線分担率": dead["double_track_factors"],
    }
    return {
        "schema_version": 1, "stage": "0600", "input": asdict(inputs),
        "provenance": {"source_workbook": "Example橋脚/0600_上部工反力.xls",
                       "source_sha256": SOURCE_SHA256,
                       "source_vba": ["Example橋脚/wiki/evidence/vba/input/上部工反力.bas",
                                      "Example橋脚/wiki/evidence/vba/0600_上部工反力/列車荷重Module.bas"],
                       "method": "元セル数式の倍精度演算・ROUNDとVBA移動荷重Single演算を維持。桁継目の所属比較だけは載荷座標と同じ0.001mの偶数丸めに統一し、元VBAの境界判定を修正（原点へ丸まる継目は元比較を保持）。Example橋脚2/07に合わせて支承鉛直荷重の組合せを修正。実行時Excel参照なし。",
                       "combination_coefficients": "安全性・復旧性の組合せ係数はρu×γを小数2桁に丸めて採用。基礎列車反力表・入力値は保持。",
                       "handoff": "実VBA Public代入の最終値だけをSingle化。係数・疲労表は表示用倍精度値。",
                       "snow_loads": "ユーザー入力を確率ごとに独立集計し水平荷重へ連携。S2:使用性/地震、S10:安全性/復旧性の列車併用、S30:LR単独。未入力は0、A/D未入力はB/Cの対応確率合計へfallback。元Excelに雪の対応セルはありません。"},
        "units": {"length": "m", "force": "kN", "moment": "kN m", "area": "m2", "volume": "m3",
                  "unit_weight": "kN/m3", "speed": "km/h", "earthquake_train_load": "kN/m"},
        "warnings": tuple(warnings), "dead_loads": dead, "snow_loads": snow, "weights": weights,
        "moving_train": asdict(moving), "moving_lateral": lateral, "train": train,
        "longitudinal": longitudinal, "longitudinal_base": longitudinal_base,
        "longitudinal_snow_cases": longitudinal_snow,
        "transverse": transverse, "transverse_parameters": transverse_parameters,
        "cells": cells, "public_values": public_values,
        "macro_handoff_single": _handoff(weights, dead, train, longitudinal, transverse, longitudinal_snow),
    }
