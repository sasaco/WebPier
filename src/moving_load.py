"""0600 point-load search, preserving VBA Single arithmetic and traversal order.

The objective is the common maximum of RB+RC, not four independent maxima.
Joint membership uses the same millimetre grid as the candidate coordinates;
this deliberately corrects raw Single boundary comparisons in the original VBA.
If that grid collapses a positive joint onto the origin, retain its raw coordinate.
Uniform loading (the VBA W branch) is outside this module's scope.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

from .calculator import vba_single
from .inputs import InputError


@dataclass(frozen=True)
class AxleContribution:
    axle_index: int
    position: float
    side: str
    distance: float
    span: float
    axle_load: float
    reaction: float


@dataclass(frozen=True)
class MovingLoadResult:
    reactions: tuple[float, float, float, float]
    positions: tuple[float, ...]
    axle_positions: tuple[float, ...]
    candidate_count: int
    # Both indices are zero-based; support points run from 0 through 6.
    selected_axle: int | None
    selected_point: int | None
    max_rb_rc: float
    contributions: tuple[AxleContribution, ...]


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label}: 有限の数値が必要です")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{label}: 数値が大きすぎます") from exc
    if not math.isfinite(result) or result < 0:
        raise InputError(f"{label}: 0以上の有限の数値が必要です")
    result = vba_single(result)
    if positive and result <= 0:
        raise InputError(f"{label}: VBA Singleで正の数値が必要です")
    return result


def _axes(n: int, car_length: float, a1: float, a2: float) -> tuple[float, ...]:
    s = vba_single
    a4 = s(s(s(car_length - a1) - a2) - a2) if a2 > 0 else s(car_length - a1)
    if a4 <= 0:
        raise InputError("車両長: a1+2*a2より大きい値が必要です")
    result: list[float] = []
    position = 0.0
    intervals = (a2, a4, a2, a1) if a2 > 0 else (a4, a1)
    for _ in range(n):
        for interval in intervals:
            result.append(position)
            position = s(position + interval)
    return tuple(result)


def _aligned_candidate(
    shifted_axes: tuple[float, ...],
    alignment_position: float,
    bridge_end: float,
) -> tuple[tuple[int, float], ...]:
    s = vba_single
    candidate: list[tuple[int, float]] = []
    for axle, offset in enumerate(shifted_axes):
        # VBA Round is ties-to-even; Excel ROUND is not used here.
        position = s(round(s(alignment_position - offset), 3))
        if position < 0:
            break
        if position <= bridge_end:
            candidate.append((axle, position))
    return tuple(candidate)


def _reactions(
    lengths: tuple[float, ...],
    candidate: tuple[tuple[int, float], ...],
    load: float,
    la: float,
    lb: float,
) -> tuple[tuple[float, float, float, float], tuple[AxleContribution, ...]]:
    s = vba_single
    joint_coordinate = s(round(la, 3))
    if joint_coordinate == 0:
        # A positive joint must remain distinct from the girder origin.
        joint_coordinate = la
    # Remove Single addition noise from the right girder origin, while
    # retaining real sub-millimetre dimensions instead of rounding them away.
    arm_joint = joint_coordinate if abs(la - joint_coordinate) <= abs(la) * 2**-22 else la
    rb = rc = left_load = right_load = 0.0
    terms: list[AxleContribution] = []
    for axle_index, position in candidate:
        left_distance = s(position - lengths[0])
        right_position = s(lb - s(position - arm_joint))
        right_distance = s(right_position - lengths[5])
        # Membership uses the millimetre grid; arm arithmetic remains Single.
        position_coordinate = s(round(position, 3))
        if position_coordinate < joint_coordinate:
            side = "B"
        elif position_coordinate > joint_coordinate:
            side = "C"
        else:
            left = s(s(load * left_distance) / lengths[1])
            right = s(s(load * right_distance) / lengths[4])
            side = "B" if left > right else "C"
        if side == "B":
            distance, span = left_distance, lengths[1]
            contribution = s(s(load * distance) / span)
            rb = s(rb + contribution)
            left_load = s(left_load + load)
        else:
            distance, span = right_distance, lengths[4]
            contribution = s(s(load * distance) / span)
            rc = s(rc + contribution)
            right_load = s(right_load + load)
        terms.append(AxleContribution(axle_index, position, side, distance, span, load, contribution))
    return (s(left_load - rb), rb, rc, s(right_load - rc)), tuple(terms)


def search_reactions(
    lengths: tuple[float, float, float, float, float, float],
    car_count: int,
    car_length: float,
    a1: float,
    a2: float,
    axle_load: float,
) -> MovingLoadResult:
    """Search every axle/point alignment using the original VBA tie rules.

    ``lengths`` are the six consecutive segments: left overhang/span/overhang,
    then right overhang/span/overhang. ``candidate_count`` counts all attempted
    alignments, including duplicates. A zero axle load bypasses the search.
    """
    if not isinstance(lengths, (tuple, list)) or len(lengths) != 6:
        raise InputError("桁長: 6区間の寸法が必要です")
    segments = tuple(_number(value, f"桁長[{i}]", positive=i in (1, 4))
                     for i, value in enumerate(lengths))
    if type(car_count) is not int or not 1 <= car_count <= 200:
        raise InputError("編成数: 1～200の整数が必要です")
    car_length = _number(car_length, "車両長", positive=True)
    a1 = _number(a1, "軸距a1", positive=True)
    a2 = _number(a2, "軸距a2")
    load = _number(axle_load, "軸重")
    if axle_load > 0 and load == 0:
        raise InputError("軸重: 正の入力がVBA Singleの最小値を下回ります")
    axes = _axes(car_count, car_length, a1, a2)
    s = vba_single
    points = [0.0]
    for value in segments:
        points.append(s(points[-1] + value))
    la = s(s(segments[0] + segments[1]) + segments[2])
    lb = s(s(segments[3] + segments[4]) + segments[5])
    best = MovingLoadResult((0.0, 0.0, 0.0, 0.0), (), axes, 0, None, None, 0.0, ())
    if load == 0:
        return best
    attempts = 0
    for axle, anchor in enumerate(axes):
        shifted = tuple(s(position - anchor) for position in axes)
        for point in range(6, -1, -1):
            attempts += 1
            candidate = _aligned_candidate(shifted, points[point], points[6])
            if not candidate:
                continue
            reactions, contributions = _reactions(segments, candidate, load, la, lb)
            score = s(reactions[1] + reactions[2])
            if score > best.max_rb_rc:
                best = MovingLoadResult(
                    reactions, tuple(position for _, position in candidate), axes,
                    0, axle, point, score, contributions,
                )
    if best.selected_axle is None:
        raise InputError("列車反力: 正の軸重に対して有効な最大反力位置がありません（寸法・丸め精度を確認）")
    return replace(best, candidate_count=attempts)
