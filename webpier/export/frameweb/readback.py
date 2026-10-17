"""Readback of a FrameWeb file through FrameWebforCS.Headless: did it read what we wrote? (README FrameWeb)

``FrameWebforCS.Headless.exe run`` turns the saved FrameWeb document into FEMPython requests, calculates every load
case and evaluates Define / Combine / Pickup. Its envelope (stdout) and ``result.json`` are compared here with the
document we wrote:

- the nodes and members come back (FEMPython may add generated nodes where a partial member load starts or ends);
- a load case without rows is skipped and a Define whose cases are all skipped is dropped (FrameWeb's behaviour,
  README FrameWeb); every other case, Define, Combine and Pickup comes back;
- for every calculated case, the support reactions balance the loads we wrote (horizontal and vertical totals),
  so a load that was dropped or misread shows;
- a combination's vertical reaction is factor × our loads unrounded, which differs from the printed total of the
  calculation only by the rounding of each factored action (decision 38).

This is a check that the file is read correctly, not a structural analysis or a design check. Running the program
is scripts/check_frameweb_headless.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

TOLERANCE = 1e-9  # relative, of the float sums of the solver (the real runs balance within 1e-12)


class ReadbackError(ValueError):
    """FrameWebforCS.Headless did not read the document as written."""


def _rows(case: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    return list(case.get("load_node") or ()), list(case.get("load_member") or ())


def _empty_cases(document: Mapping[str, Any]) -> list[str]:
    return [key for key, case in document["load"].items() if not any(_rows(case))]


def _define_cases(define: Mapping[str, Any]) -> list[str]:
    return [str(abs(int(value))) for key, value in define.items() if key.startswith("C")]


def expected_counts(document: Mapping[str, Any]) -> dict[str, Any]:
    empty = _empty_cases(document)
    without = [key for key, define in document["define"].items() if set(_define_cases(define)) <= set(empty)]
    return {"nodes": len(document["node"]), "members": len(document["member"]), "load_cases": len(document["load"]),
            "empty_load_cases": empty, "defines": len(document["define"]), "defines_without_loads": without,
            "combines": len(document["combine"]), "pickups": len(document["pickup"])}


def _same(label: str, written: list[str], read: list[str]) -> None:
    if read != written:
        raise ReadbackError(f"{label}が一致しません（書いた {written}、読込み {read}）")


def compare_counts(document: Mapping[str, Any], envelope: Mapping[str, Any],
                   result: Mapping[str, Any]) -> dict[str, Any]:
    """The counts that came back; raise ``ReadbackError`` when the run failed or anything is missing."""
    if envelope.get("ok") is not True or envelope.get("executionStatus") != "success" or envelope.get("errors"):
        raise ReadbackError(f"FrameWebforCS.Headless が成功していません: {envelope.get('errors')}")
    analysis, derived = result["analysisResultSet"], result["derived"]
    nodes, members = analysis["topology"]["nodes"], analysis["topology"]["members"]
    summary = {"nodes": len(nodes), "members": len(members), "cases": len(analysis["cases"]),
               "results": len(analysis["results"]), "pickups": len(derived["pickups"]),
               "skippedLoadCases": len(result["skippedLoadCases"])}
    if any(envelope["summary"].get(key) != value for key, value in summary.items()):
        raise ReadbackError(f"summary が result.json と一致しません（summary {envelope['summary']}、result {summary}）")
    expected = expected_counts(document)
    empty, without = expected["empty_load_cases"], expected["defines_without_loads"]
    original = [str(node["node_id"]) for node in nodes if not node.get("generated")]
    _same("節点", list(document["node"]), original)
    _same("部材", list(document["member"]), [str(member["member_id"]) for member in members])
    _same("飛ばした荷重ケース", empty, [str(case) for case in result["skippedLoadCases"]])
    _same("計算した荷重ケース", [key for key in document["load"] if key not in empty],
          [str(case["case_id"]) for case in analysis["cases"]])
    _same("Define", [key for key in document["define"] if key not in without],
          [str(define["id"]) for define in derived["defines"]])
    _same("Combine", list(document["combine"]), [str(c["id"]) for c in derived["combines"]])
    _same("Pickup", list(document["pickup"]), [str(p["id"]) for p in derived["pickups"]])
    return {"nodes": len(original), "generated_nodes": len(nodes) - len(original), "members": len(members),
            "calculated_cases": len(analysis["cases"]), "skipped_load_cases": empty,
            "defines": len(derived["defines"]), "combines": len(derived["combines"]),
            "pickups": len(derived["pickups"])}


def _length(document: Mapping[str, Any], member: str) -> float:
    row = document["member"][member]
    start, end = document["node"][str(row["ni"])], document["node"][str(row["nj"])]
    return float(((end["x"] - start["x"]) ** 2 + (end["y"] - start["y"]) ** 2) ** 0.5)


def applied_totals(document: Mapping[str, Any], case_id: str) -> tuple[float, float]:
    """Σ of the global x and y forces we wrote for a case: node loads and trapezoidal member loads (mark 2)."""
    nodes, members = _rows(document["load"][case_id])
    fx = sum(float(row["tx"] or 0) for row in nodes)
    fy = sum(float(row["ty"] or 0) for row in nodes)
    for row in members:
        if row["mark"] != 2:
            raise ReadbackError(f"荷重ケース {case_id}: 部材荷重の種類 {row['mark']} には対応していません")
        if row["direction"] not in ("gx", "gy"):
            raise ReadbackError(f"荷重ケース {case_id}: 部材荷重の向き {row['direction']} には対応していません")
        loaded = _length(document, str(row["m1"])) - row["L1"] - row["L2"]
        total = (row["P1"] + row["P2"]) / 2 * loaded
        if row["direction"] == "gx":
            fx += total
        else:
            fy += total
    return fx, fy


def check_equilibrium(document: Mapping[str, Any], result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """For every calculated case, Σ support reactions = −Σ loads we wrote, in x and in y."""
    by_case = {str(item["case_id"]): item for item in result["analysisResultSet"]["results"]}
    checked = []
    for case in result["analysisResultSet"]["cases"]:
        case_id = str(case["case_id"])
        if case_id not in by_case:
            raise ReadbackError(f"荷重ケース {case_id} の結果がありません")
        applied = applied_totals(document, case_id)
        reactions = tuple(sum(item["components"][name] for item in by_case[case_id]["support_reactions"])
                          for name in ("fx", "fy"))
        symbol = document["load"][case_id].get("symbol")
        for name, load, held in zip(("fx", "fy"), applied, reactions):
            if abs(load + held) > TOLERANCE * (1 + abs(load)):
                raise ReadbackError(f"荷重ケース {case_id}（{symbol}）: 荷重 {name} = {load} が反力 {name} = {held} と"
                                    "釣り合いません")
        checked.append({"case": case_id, "symbol": symbol, "applied": list(applied), "reactions": list(reactions)})
    return checked


ROUNDING = Decimal("0.005")  # the most a printed factored action differs from factor × action (decision 38)


def _decimal(value: float) -> Decimal:
    return Decimal(repr(float(value)))


def combination_vertical(combination: Any, document: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Decision 38 on one 0610 combination: FrameWeb's combined vertical reaction against the printed total.

    The calculation prints each factored action rounded; FrameWeb combines factor × action unrounded. So the
    combined reaction must be the unrounded sum, and it differs from the printed total only by each action's
    rounding, at most 0.005 per printed intensity (a line load's difference is multiplied by its length). The
    combination must have one vertical result (its alternatives differ only horizontally).
    """
    printed = unrounded = largest = Decimal(0)
    for component in combination.components:
        factor = _decimal(component.factor.value)
        pairs = [(point.n, source.n, Decimal(1)) for point, source in zip(component.points, component.source.points)]
        pairs += [(line.n, source.n, sum(_decimal(_length(document, str(member))) for member in line.members))
                  for line, source in zip(component.line_loads, component.source.line_loads)]
        for value, source, length in pairs:
            shown, exact = _decimal(value.value), factor * _decimal(source.value)
            largest = max(largest, abs(shown - exact))
            printed += shown * length
            unrounded += exact * length
    if largest > ROUNDING:
        raise ReadbackError(f"Combine {combination.number}: 印字桁への丸めの差 {largest} が 0.005 を超えます")
    combine = next(item for item in result["derived"]["combines"] if str(item["id"]) == str(combination.number))
    high, low = (sum(_decimal(entry["components"]["fy"]) for entry in combine["reactions"][key])
                 for key in ("fy_max", "fy_min"))
    if high != low:
        raise ReadbackError(f"Combine {combination.number}: 鉛直反力の最大と最小が異なります（{high}、{low}）")
    if abs(high - unrounded) > Decimal(str(TOLERANCE)) * (1 + abs(unrounded)):
        raise ReadbackError(f"Combine {combination.number}: 鉛直反力 {high} が係数×荷重の和 {unrounded} と異なります")
    return {"combine": combination.number, "printed": float(printed), "unrounded": float(unrounded),
            "frameweb": float(high), "difference": float(printed - high), "largest_action_difference": float(largest)}
