"""Independent revised combinations on historical raw reactions and coefficients.

Only the user-requested longitudinal combination cells are replaced. The
historical moving loads, impacts, braking bases and all other Excel evidence
remain the expectations. This oracle deliberately supports snow-free EA-17
fixtures only; asymmetric snow and other vehicles have separate tests.
"""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, localcontext
import struct


def _round(value):
    with localcontext():
        return float(Decimal(format(value, ".15g")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _single(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def _dead_points(data):
    points = {}
    for side, inner, outer in (("起点側", "B", "A"), ("終点側", "C", "D")):
        branch = data["上部工反力"][side]
        rows = branch[f"{inner}支点"]["支承"]
        points[inner] = tuple(sum(row[key] or 0 for row in rows) for key in ("固定死荷重_D1", "付加死荷重_D2"))
        total = branch.get(f"{outer}支点", {}).get("合計", {})
        points[outer] = tuple(total.get(key) if total.get(key) is not None else fallback
                              for key, fallback in zip(("固定死荷重_D1", "付加死荷重_D2"), points[inner]))
        for row in [*rows, total]:
            assert all(row.get(f"雪荷重_{year}年確率") in (None, 0) for year in (2, 10, 30))
    return points


def _bearing(applied, remote, local, mu, bearing):
    half = applied / 2
    fixed_candidate = _round(applied - .5 * mu * remote)
    movable_friction = _round(mu * local)
    movable_floor = _round(mu * half)
    fixed = max(fixed_candidate, half)
    movable = min(half, max(movable_friction, movable_floor))
    return fixed if bearing == "固定" else movable, (fixed_candidate, half, half, movable_friction, movable_floor)


def combination_expectations(case, input_data=None):
    data = case["input"] if input_data is None else input_data
    structure = data["上部構造"]
    assert structure["列車"]["車両名"] == "EA-17"
    rho = structure["列車"]["荷重修正係数"]["安全性(破壊)"]
    dead = _dead_points(data)
    tables = case["formula_values"]["列車荷重"]
    original = case["formula_values"]["線路荷重"]
    # Explicit specification, independent of the production combination table.
    verticals = ((1, 1, None, 0, False), (1, 1, "service", 1, True),
                 (1.1, 1.2, "ultimate", 1.1, True), (1.1, 1.2, "ultimate", 1, True),
                 (1.1, 1.2, "ultimate", 1.1, True), (1.1, 1.2, "ultimate", 1, True),
                 (1.1, 1.2, "ultimate", 1, True), (1, 1, "ultimate", 1, True))
    horizontal = ((.8, 0), (1, 0), (0, 1), (0, 1.1), (1, 1), (1.1, 1), (1, 1.1), (1, 1))
    vertical_cells = {
        "B": (("Z87", "Z94"), ("L133", "L142"), ("L184", "L194"), ("L237", "L247"),
              ("L295", "L305"), ("L349", "L359"), ("AC402", "AC411"), ("L454", "L464")),
        "C": (("Z106", "Z113"), ("L156", "L164"), ("L209", "L219"), ("L262", "L272"),
              ("L320", "L330"), ("L374", "L384"), ("AC425", "AC434"), ("L479", "L489")),
    }
    candidate_rows = {
        "B": ((91, 92, 97, 98, 99), (137, 138, 145, 146, 147), (188, 189, 197, 198, 199),
              (241, 242, 250, 251, 252), (299, 300, 308, 309, 310), (353, 354, 362, 363, 364),
              (406, 407, 414, 415, 416), (458, 459, 467, 468, 469)),
        "C": ((110, 111, 116, 117, 118), (160, 161, 167, 168, 169), (213, 214, 222, 223, 224),
              (266, 267, 275, 276, 277), (324, 325, 333, 334, 335), (378, 379, 387, 388, 389),
              (429, 430, 437, 438, 439), (483, 484, 492, 493, 494)),
    }
    force_rows = {"B": (101, 149, 201, 254, 312, 366, 418, 471),
                  "C": (120, 171, 226, 279, 337, 391, 441, 496)}
    columns = {"A": "R", "B": "V", "C": "Z", "D": "AD"}
    updates, single, snow_single = {}, [{} for _ in range(8)], [{}, {}]
    for side, outer, side_name, lr_cell, lr08_cell, brake_cell, start_cell, public_col in (
        ("B", "A", "起点側", "AC22", "AC30", "AC44", "AC50", "T"),
        ("C", "D", "終点側", "AC24", "AC32", "AC46", "AC52", "X"),
    ):
        support = structure["支承データ"][side_name]
        mu, bearing = support["摩擦係数_μ"], support["支承名"]
        lr, braking = original[lr_cell], max(original[brake_cell], original[start_cell])
        for index, ((d1, d2, group, gamma, impact), (lr_factor, brake_factor)) in enumerate(zip(verticals, horizontal)):
            loads = []
            for point in (outer, side):
                load = d1 * dead[point][0] + d2 * dead[point][1]
                if group:
                    coefficient_row = 72 if group == "ultimate" else 79
                    column = columns[point]
                    raw = case["independent_reactions"][f"R{point}"]
                    tracks = tables["M4" if side == "B" else "M5"]
                    coefficient = tables[f"{column}{coefficient_row}"] if impact else 0
                    live = raw * tracks * (1 + coefficient)
                    factor = (_round(rho * gamma) if group == "ultimate"
                              else structure["列車"]["荷重修正係数"]["使用性"] * gamma)
                    load += factor * live
                loads.append(load)
            brake_scale = _round(rho * brake_factor) / rho if rho else 0
            applied = (original[lr08_cell] if index == 0 else lr_factor * lr) + brake_scale * braking
            force, candidates = _bearing(applied, *loads, mu, bearing)
            updates.update(zip(vertical_cells[side][index], loads))
            updates.update((f"AC{row}", value) for row, value in zip(candidate_rows[side][index], candidates))
            updates[f"K{force_rows[side][index]}"] = force
            updates[f"{public_col}{545 + index}"] = force
            single[index][f"R{side}"] = _single(force)
        for index, (d1, d2) in enumerate(((1.1, 1.2), (1, 1))):
            loads = [d1 * dead[point][0] + d2 * dead[point][1] for point in (outer, side)]
            force, _ = _bearing(lr, *loads, mu, bearing)
            snow_single[index][f"R{side}"] = _single(force)
    return {"formula_updates": updates, "single": single, "snow_single": snow_single}


def revised_reaction_case(case):
    revised = deepcopy(case)
    expected = combination_expectations(case)
    revised["formula_values"]["線路荷重"].update(expected["formula_updates"])
    for index, forces in enumerate(expected["single"]):
        for side, column in (("B", "T"), ("C", "X")):
            cell = f"{column}{545 + index}"
            revised["public_values"]["線路荷重"][cell] = expected["formula_updates"][cell]
            revised["public_single"]["線路荷重"][cell] = forces[f"R{side}"]
    return revised, expected["snow_single"]
