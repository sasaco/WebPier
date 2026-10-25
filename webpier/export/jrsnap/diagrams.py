"""Which combination's analysis data each basic case of the 荷重図 is drawn from (decision 51).

JRSNAP writes one .ndt per combination and writes the loads of a basic case the combination does not use as 0 (0720:
CASE-6, the down track, in the .ndt of combination 1; CASE-5, the up track, in that of combination 2). So the page of
each basic case is taken from the .ndt of the first combination, by number, that uses it.
"""

from __future__ import annotations

from typing import Any


def diagram_combinations(model: Any, *, used_only: bool = False) -> tuple[tuple[int, int], ...]:
    """(basic case number, combination number), in case order; combinations are numbered from 1 in model order.

    ``ValueError`` when a basic case is used by no combination (it would be drawn with no loads), unless *used_only*: the
    NDU of one push of a pile foundation (decision 93) leaves out the cases of the other push, which are drawn from the
    NDU of that one.
    """
    found = []
    for index, case in enumerate(model.cases):
        using = [number for number, combination in enumerate(model.combinations, 1) if combination.coefficients[index]]
        if not using and used_only:
            continue
        if not using:
            raise ValueError(f"基本ケース{case.number}（{case.title}）を使う組合せがありません")
        found.append((case.number, using[0]))
    return tuple(found)
