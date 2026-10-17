"""0600 dead and snow loads at the four supports, and the train share of each bearing.

The origin girder rests on A (far end) and B (this pier); the end girder on C
(this pier) and D (far end). B and C are summed from their bearing slots; A and
D are entered as totals. Printed digits follow Example2 07 7-1/7-3.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.printed import FORCE, Precision, Printed
from ...inputs import PierInput
from ...inputs.model import Bearing, EndReaction
from .._exact import put, total

SHARE = Precision(3, "")  # train share of a bearing, and the number of loaded tracks (07 7-3)


@dataclass(frozen=True)
class SupportLoads:
    """Dead and snow loads at one support."""

    d1: Printed  # fixed dead load D1
    d2: Printed  # additional dead load D2
    snow2: Printed  # snow, 2-year return period (S2)
    snow10: Printed  # snow, 10-year return period (S10)
    snow30: Printed  # snow, 30-year return period (S30)


@dataclass(frozen=True)
class BearingLoads:
    """One occupied bearing slot of B or C."""

    slot: int  # index of the input slot (0..9); empty slots are skipped
    bearing: Bearing  # the entered position, loads and per-track shares (L1..L4, None = no such track)
    double: Printed  # share when both tracks are loaded: L1 + L2


@dataclass(frozen=True)
class GirderDead:
    """Loads of one girder: its far support (A or D) and its support on this pier (B or C)."""

    far: SupportLoads  # A (origin girder) or D (end girder), entered totals
    pier: SupportLoads  # B (origin girder) or C (end girder), sums of the bearings
    bearings: tuple[BearingLoads, ...]  # occupied bearing slots on this pier
    track_total: Printed  # Σ double shares: the number of loaded tracks (07 7-3 "2.000")


@dataclass(frozen=True)
class DeadResult:
    origin: GirderDead
    end: GirderDead
    superstructure: Printed  # DU = D1 + D2 at B and C: girder dead load on the pier (RC標準 解4.4.4)


def _far(end: EndReaction) -> SupportLoads:
    return SupportLoads(end.d1, end.d2, end.snow2, end.snow10, end.snow30)


def _girder(far: EndReaction, slots: tuple[Bearing | None, ...]) -> GirderDead:
    bearings = tuple(
        BearingLoads(slot=index, bearing=bearing, double=put(SHARE, total((bearing.shares.l1, bearing.shares.l2))))
        for index, bearing in enumerate(slots) if bearing is not None)

    def summed(field: str) -> Printed:
        return put(FORCE, total(getattr(item.bearing, field) for item in bearings))

    pier = SupportLoads(*(summed(field) for field in ("d1", "d2", "snow2", "snow10", "snow30")))
    return GirderDead(far=_far(far), pier=pier, bearings=bearings,
                      track_total=put(SHARE, total(item.double for item in bearings)))


def calculate_dead(pier: PierInput) -> DeadResult:
    reactions = pier.reactions
    origin = _girder(reactions.a, reactions.b)
    end = _girder(reactions.d, reactions.c)
    superstructure = put(FORCE, total((origin.pier.d1, origin.pier.d2, end.pier.d1, end.pier.d2)))
    return DeadResult(origin=origin, end=end, superstructure=superstructure)
