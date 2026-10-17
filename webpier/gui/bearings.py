"""Editing the bearing slots and the values the editor writes on request (decision 5).

Each pier-side support has ten slots. A slot with every value blank is saved as null, an empty slot (CONTEXT.md
空き支承枠); typing into it creates the bearing with the other values blank, which the editor marks as missing
until they are entered. Nothing is implied: "B7と同じ" writes B9 := B7 and "B/Cと同じ" writes the A/D totals as
the sums of the printed B/C values, as explicit input values.
"""

from __future__ import annotations

from typing import Any

from ..core.errors import InputError
from ..core.printed import Printed
from ..core.reader import Reader
from ..inputs.fields import LOAD, LOAD_KEYS, SNOW_KEYS, read
from .document import EditorError, JsonPath

__all__ = ["LOAD_KEYS", "SNOW_KEYS", "SUPPORTS", "SLOT_LEAVES", "missing", "same_as_b7", "same_as_bearings",
           "set_value", "state"]

SUPPORTS = {"起点側": ("A支点", "B支点"), "終点側": ("D支点", "C支点")}  # side: (girder end, pier bearings)
SLOT_LEAVES: tuple[JsonPath, ...] = (("支承位置",), *((key,) for key in LOAD_KEYS),
                                     *(("列車分担", track) for track in ("L1", "L2", "L3", "L4")))
B7 = ("下部構造", "寸法", "側面", "B7")


def _slots(data: Any, side: str) -> list:
    return data["上部工反力"][side][SUPPORTS[side][1]]


def _leaf(slot: dict, tail: JsonPath) -> Any:
    for key in tail:
        slot = slot[key]
    return slot


def _empty() -> dict:
    slot: dict[str, Any] = {"支承位置": None, **dict.fromkeys(LOAD_KEYS)}
    slot["列車分担"] = dict.fromkeys(("L1", "L2", "L3", "L4"))
    return slot


def state(slot: dict | None) -> str:
    """empty (null), partial (some values blank) or complete."""
    if slot is None:
        return "empty"
    blank = [_leaf(slot, tail) is None for tail in SLOT_LEAVES if tail[-1] not in ("L3", "L4")]
    return "partial" if any(blank) else "complete"


def set_value(data: Any, side: str, index: int, tail: JsonPath, value: Any) -> None:
    slots = _slots(data, side)
    if slots[index] is None:
        if value is None:
            return
        slots[index] = _empty()
    owner = slots[index]
    for key in tail[:-1]:
        owner = owner[key]
    owner[tail[-1]] = value
    if all(_leaf(slots[index], leaf) is None for leaf in SLOT_LEAVES):
        slots[index] = None


def missing(data: Any, side: str, index: int) -> list[JsonPath]:
    """The blank values of a bearing that has some values entered."""
    slot = _slots(data, side)[index]
    if slot is None:
        return []
    prefix = ("上部工反力", side, SUPPORTS[side][1], index)
    return [(*prefix, *tail) for tail in SLOT_LEAVES if tail[-1] not in ("L3", "L4") and _leaf(slot, tail) is None]


def _printed(root: Reader, *keys: str | int) -> Printed:
    """A required number of the table; a blank or an invalid value is reported with its path."""
    try:
        return read(root.at(*keys))
    except InputError as exc:
        raise EditorError(str(exc)) from None


def same_as_b7(data: Any) -> float:
    """Write B9 := B7."""
    value = _printed(Reader(data), *B7).value
    data["下部構造"]["寸法"]["側面"]["B9"] = value
    return value


def same_as_bearings(data: Any, side: str) -> dict[str, float]:
    """Write the totals of the girder end (A or D) as the sums of the pier bearings (B or C) of *side*."""
    end, support = SUPPORTS[side]
    root = Reader(data)
    used = [index for index, slot in enumerate(_slots(data, side)) if slot is not None]
    if not used:
        raise EditorError(f"上部工反力.{side}.{support}: 支承がありません")
    totals = {}
    for key in LOAD_KEYS:
        parts = [_printed(root, "上部工反力", side, support, index, key) for index in used]
        totals[key] = LOAD.total(parts).value
    data["上部工反力"][side][end] = totals
    return totals
