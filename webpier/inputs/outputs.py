"""The 出力項目 of the input (CONTEXT.md, decision 72, ADR-0011): which reports a generation makes.

Each item is true or false (``outputs.<key>``); an item may be true only when every item it uses is true, so the
chosen items are closed under use. Which stages an item makes is the registry's (pipeline.stages.OUTPUT_STAGES), which
checks that a stage reads only the stages of its own item and of the items it uses. Captions live in the editor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputItem:
    key: str
    requires: tuple[str, ...]  # the items whose results it uses; each must be chosen with it


_FRAMES = ("longitudinal_frame_analysis", "transverse_frame_analysis")
_NONLINEAR = ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis")

OUTPUT_ITEMS = (
    OutputItem("ground_model", ()),  # 0500
    OutputItem("reactions", ()),  # 0600
    OutputItem("longitudinal", ("ground_model", "reactions")),  # 0610
    OutputItem("longitudinal_frame_analysis", ("longitudinal",)),  # 0611, 0612
    OutputItem("transverse", ("ground_model", "reactions")),  # 0620
    OutputItem("transverse_frame_analysis", ("transverse",)),  # 0621, 0622
    OutputItem("longitudinal_seismic", ("longitudinal",)),  # 0710
    OutputItem("longitudinal_nonlinear_analysis", ("longitudinal_seismic",)),  # 0711
    OutputItem("transverse_seismic", ("transverse",)),  # 0720
    OutputItem("transverse_nonlinear_analysis", ("transverse_seismic",)),  # 0721
    OutputItem("footing", (*_FRAMES, *_NONLINEAR)),  # 0800, 0810, 0820
    OutputItem("cantilever", _NONLINEAR),  # 0900, 0910
)
OUTPUT_KEYS = tuple(item.key for item in OUTPUT_ITEMS)
_BY_KEY = {item.key: item for item in OUTPUT_ITEMS}


def requires(key: str) -> tuple[str, ...]:
    """The items *key* uses directly."""
    return _BY_KEY[key].requires


def uses(key: str) -> frozenset[str]:
    """Every item *key* uses, directly or through another item."""
    found: set[str] = set()
    pending = list(requires(key))
    while pending:
        item = pending.pop()
        if item not in found:
            found.add(item)
            pending.extend(requires(item))
    return frozenset(found)


def users(key: str) -> tuple[str, ...]:
    """The items that use *key*, directly or through another item, in table order."""
    return tuple(item for item in OUTPUT_KEYS if key in uses(item))
