"""The ground springs a load case is analysed with follow the nature of its loads (decision 36).

Long rail forces act for a long time: long-term springs (8-9 バネ 1). Braking and starting and the other live
loads (train, impact, centrifugal, vehicle lateral) are short-term (バネ 2); a case with a long rail force and
braking is short-term. Decision 36 names only these; dead loads, buoyancy and snow are long-term and wind
short-term, as the Example2 FrameWeb files save them (08 / 09 frameWebForJS.json). Shared by every direction.
"""

from __future__ import annotations

from enum import Enum


class SpringTerm(Enum):
    LONG = "long_term"  # バネ 1 of 8-9
    SHORT = "short_term"  # バネ 2


class Nature(Enum):
    DEAD = "dead"  # fixed and additional dead loads
    WATER = "water"  # buoyancy
    SNOW = "snow"
    LONG_RAIL = "long_rail"  # long rail longitudinal force
    TRAIN = "train"
    IMPACT = "impact"
    BRAKING = "braking"  # braking and starting
    CENTRIFUGAL = "centrifugal"
    LATERAL = "lateral"  # vehicle lateral force
    WIND = "wind"


LONG_TERM_NATURES = frozenset({Nature.DEAD, Nature.WATER, Nature.SNOW, Nature.LONG_RAIL})


def spring_term(natures: frozenset[Nature]) -> SpringTerm:
    """Long-term only if every load of the case is long-term."""
    if not natures:
        raise ValueError("a load case needs the nature of its loads")
    return SpringTerm.LONG if natures <= LONG_TERM_NATURES else SpringTerm.SHORT
