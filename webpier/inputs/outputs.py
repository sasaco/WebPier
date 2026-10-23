"""The 出力項目 of the input (CONTEXT.md, decision 72, ADR-0011): which reports a generation makes.

Each item is true or false (``outputs.<key>``); an item may be true only when every item it uses is true, so the
chosen items are closed under use. Which stages an item makes is the registry's (pipeline.stages.OUTPUT_STAGES), which
checks that a stage reads only the stages of its own item and of the items it uses. Captions live in the editor.
"""

from __future__ import annotations

from dataclasses import dataclass

from .choices import PILE_FOUNDATIONS


@dataclass(frozen=True)
class OutputItem:
    key: str
    requires: tuple[str, ...]  # the items whose results it uses; each must be chosen with it


_FRAMES = ("longitudinal_frame_analysis", "transverse_frame_analysis")
_NONLINEAR = ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis")

OUTPUT_ITEMS = (
    OutputItem("detailing", ()),  # 0400 (decision 73: the input alone)
    OutputItem("ground_model", ()),  # 0500
    OutputItem("reactions", ()),  # 0600
    OutputItem("longitudinal", ("ground_model", "reactions")),  # 0610
    OutputItem("longitudinal_frame_analysis", ("longitudinal",)),  # 0611, 0612
    OutputItem("transverse", ("ground_model", "reactions")),  # 0620
    OutputItem("transverse_frame_analysis", ("transverse",)),  # 0621, 0622
    OutputItem("longitudinal_seismic", ("ground_model", "reactions")),  # 0710 (decision 78: without 0610)
    OutputItem("longitudinal_nonlinear_analysis", ("longitudinal_seismic",)),  # 0711
    OutputItem("transverse_seismic", ("ground_model", "reactions")),  # 0720 (decision 78: without 0620)
    OutputItem("transverse_nonlinear_analysis", ("transverse_seismic",)),  # 0721
    OutputItem("footing", (*_FRAMES, *_NONLINEAR)),  # 0800, 0810, 0820
    OutputItem("cantilever", _NONLINEAR),  # 0900, 0910
)
OUTPUT_KEYS = tuple(item.key for item in OUTPUT_ITEMS)
_BY_KEY = {item.key: item for item in OUTPUT_ITEMS}

# The items a pile foundation can make so far (roadmap pile-foundation-roadmap.md; widened a stage at a time): 0400,
# 0500 (SOIL-JR's ground model, decision 85), 0600 (which does not read the foundation), 0610, 0620 (the frame on the
# piles, decision 88) and the frame analyses 0611, 0612, 0621, 0622 (decision 89).
PILE_OUTPUT_KEYS: tuple[str, ...] = ("detailing", "ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis",
                                     "transverse", "transverse_frame_analysis")


def foundation_makes(foundation: str | None, key: str) -> bool:
    """Whether a generation can make the item *key* for the 基礎形式 (a direct foundation makes every item)."""
    return foundation not in PILE_FOUNDATIONS or key in PILE_OUTPUT_KEYS


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
