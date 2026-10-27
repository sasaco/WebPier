"""The 出力項目 of the input (CONTEXT.md, decision 72, ADR-0011): which reports a generation makes.

Each item is true or false (``outputs.<key>``); an item may be true only when every item it uses is true, so the
chosen items are closed under use. The footing uses either group of analyses or both (decision 110): the frame
analyses of both directions for its checks other than the seismic ones, the nonlinear analyses of both directions for
the seismic ones (``footing_parts``). Which stages an item makes is the registry's (pipeline.stages.OUTPUT_STAGES), which
checks that a stage reads only the stages of its own item and of the items it uses. Captions live in the editor.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from .choices import CAST_IN_PLACE_PILE, PILE_FOUNDATIONS, STEEL_SOIL_CEMENT_PILE


@dataclass(frozen=True)
class OutputItem:
    key: str
    requires: tuple[str, ...]  # the items whose results it uses; each must be chosen with it
    either: tuple[tuple[str, ...], ...] = ()  # groups of items it uses: at least one group must be chosen whole


@dataclass(frozen=True)
class FootingParts:
    """The parts of the footing (0800, 0810, 0820) a choice of items makes (decision 110): the checks other than the
    seismic ones with the frame analyses of both directions, the seismic ones with their nonlinear analyses."""

    frames: bool
    seismic: bool


_FRAMES = ("longitudinal_frame_analysis", "transverse_frame_analysis")
_NONLINEAR = ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis")

OUTPUT_ITEMS = (
    OutputItem("detailing", ()),  # 0400 (decision 73: the input alone; a 場所打ち杭's also 0500, FOUNDATION_REQUIRES)
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
    OutputItem("footing", (), (_FRAMES, _NONLINEAR)),  # 0800, 0810, 0820 (decision 110)
    OutputItem("cantilever", _NONLINEAR),  # 0900, 0910
)
OUTPUT_KEYS = tuple(item.key for item in OUTPUT_ITEMS)
_BY_KEY = {item.key: item for item in OUTPUT_ITEMS}

# The items a pile foundation can make so far (roadmap pile-foundation-roadmap.md; widened a stage at a time): 0400,
# 0500 (SOIL-JR's ground model, decision 85), 0600 (which does not read the foundation), 0610, 0620 (the frame on the
# piles, decision 88), the frame analyses 0611, 0612, 0621, 0622 (decision 89), the seismic loads 0710, 0720 (decision 93) and
# the static nonlinear analyses with their seismic checks 0711, 0721 (decision 94) and the footing 0800, 0810, 0820 (decision 96).
PILE_OUTPUT_KEYS: tuple[str, ...] = ("detailing", "ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis",
                                     "transverse", "transverse_frame_analysis", "longitudinal_seismic",
                                     "longitudinal_nonlinear_analysis", "transverse_seismic",
                                     "transverse_nonlinear_analysis", "footing")
# The items only a 場所打ち杭 makes so far: the NDU of the piles of 0710 and 0720 is made for it only (decision 93), and so
# are the analyses and checks of that NDU (decision 94).
CAST_IN_PLACE_ONLY: tuple[str, ...] = ("longitudinal_seismic", "longitudinal_nonlinear_analysis", "transverse_seismic",
                                       "transverse_nonlinear_analysis", "footing")
# The items an item uses besides the table's for a 基礎形式: the 杭の構造細目 of a 場所打ち杭 in 0400 read 1/β of SOIL-JR's
# ground model, 0500 (decision 98).
FOUNDATION_REQUIRES: dict[str | None, dict[str, tuple[str, ...]]] = {CAST_IN_PLACE_PILE: {"detailing": ("ground_model",)}}


def foundation_makes(foundation: str | None, key: str) -> bool:
    """Whether a generation can make the item *key* for the 基礎形式 (a direct foundation makes every item)."""
    if foundation == STEEL_SOIL_CEMENT_PILE and key in CAST_IN_PLACE_ONLY:
        return False
    return foundation not in PILE_FOUNDATIONS or key in PILE_OUTPUT_KEYS


def requires(key: str, foundation: str | None = None) -> tuple[str, ...]:
    """The items *key* uses directly, each of which must be chosen with it, for the 基礎形式 *foundation* (None: as the
    table has them)."""
    return _BY_KEY[key].requires + FOUNDATION_REQUIRES.get(foundation, {}).get(key, ())


def either(key: str) -> tuple[tuple[str, ...], ...]:
    """The groups of items *key* uses of which at least one must be chosen whole (none: no such rule)."""
    return _BY_KEY[key].either


def available(key: str, chosen: Collection[str], foundation: str | None = None) -> bool:
    """Whether *key* may be chosen with the items *chosen*: every item it requires, and a whole group of ``either``."""
    groups = either(key)
    return (all(item in chosen for item in requires(key, foundation))
            and (not groups or any(all(item in chosen for item in group) for group in groups)))


def footing_parts(chosen: Collection[str]) -> FootingParts:
    """The parts of the footing the items *chosen* make (decision 110); neither when the footing is not chosen."""
    def whole(group: tuple[str, ...]) -> bool:
        return "footing" in chosen and all(item in chosen for item in group)
    return FootingParts(frames=whole(_FRAMES), seismic=whole(_NONLINEAR))


def uses(key: str, foundation: str | None = None) -> frozenset[str]:
    """Every item *key* uses or may use (each item of its ``either`` groups), directly or through another item, for
    the 基礎形式 *foundation*."""
    found: set[str] = set()
    pending = [*requires(key, foundation), *(item for group in either(key) for item in group)]
    while pending:
        item = pending.pop()
        if item not in found:
            found.add(item)
            pending.extend((*requires(item, foundation), *(other for group in either(item) for other in group)))
    return frozenset(found)


def users(key: str, foundation: str | None = None) -> tuple[str, ...]:
    """The items that use *key*, directly or through another item, in table order, for the 基礎形式 *foundation*."""
    return tuple(item for item in OUTPUT_KEYS if key in uses(item, foundation))
