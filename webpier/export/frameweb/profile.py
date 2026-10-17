"""What differs between the directions of a FrameWeb input: the labels and the spring sets.

The shared code reads the calc result by its structure (basic cases, Define cases, combinations, extractions)
and takes everything stage-specific from a ``Profile``: the FrameWeb names of the load cases, of the load cases
added for a factor on another action than the basic one, of the combinations and pickups, and which FrameWeb
spring set each spring term of the stage is. A second direction is a second profile, not a branch; its entry
point reads its result into ``cases.Source`` (0620: Define cases with alternatives over basic cases) and shares
the tables, the document and the validator.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

LONG_TERM = 1  # FrameWeb fix_node set of the long-term springs (8-9 バネ 1)
SHORT_TERM = 2  # short-term springs (8-9 バネ 2)


@dataclass(frozen=True)
class Label:
    symbol: str
    name: str


@dataclass(frozen=True)
class Profile:
    loads: Mapping[Enum, Label]  # by basic case
    auxiliary: Mapping[tuple[Enum, Enum], Label]  # by (basic case, basis) for a factor on another action
    combinations: Mapping[int, str]  # by combination number
    extractions: Mapping[int, str]  # by extraction number
    springs: Mapping[Enum, int]  # spring term of the stage -> LONG_TERM / SHORT_TERM
    basic: Enum  # the basis meaning "the basic action itself"
