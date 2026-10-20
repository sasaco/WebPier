"""0600 dead and snow loads at the four supports, and the train share of each bearing.

The origin girder rests on A (far end) and B (this pier); the end girder on C
(this pier) and D (far end). B and C are summed from their bearing slots; A and
D are entered as totals. Printed digits follow Example2 07 7-1/7-3.

With a load model (decision 70) the snow and the train shares are the load model's: ``calculate_dead_loads`` gives
D1 and D2 alone, in the same shape.
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


SNOW_FIELDS = ("snow2", "snow10", "snow30")


@dataclass(frozen=True)
class DeadResult:
    origin: GirderDead
    end: GirderDead

    @property
    def snow(self) -> bool:
        """Whether a bearing on this pier carries snow (decision 69): without, no snow case is made from 0610 on."""
        return any(getattr(item.bearing, field).value for girder in (self.origin, self.end)
                   for item in girder.bearings for field in SNOW_FIELDS)


def _far(end: EndReaction) -> SupportLoads:
    return SupportLoads(end.d1, end.d2, end.snow2, end.snow10, end.snow30)


def _girder(far: EndReaction, slots: tuple[Bearing | None, ...]) -> GirderDead:
    bearings = tuple(
        BearingLoads(slot=index, bearing=bearing, double=put(SHARE, total((bearing.shares.l1, bearing.shares.l2))))
        for index, bearing in enumerate(slots) if bearing is not None)

    def summed(field: str) -> Printed:
        return put(FORCE, total(getattr(item.bearing, field) for item in bearings))

    pier = SupportLoads(*(summed(field) for field in ("d1", "d2", *SNOW_FIELDS)))
    return GirderDead(far=_far(far), pier=pier, bearings=bearings,
                      track_total=put(SHARE, total(item.double for item in bearings)))


def calculate_dead(pier: PierInput) -> DeadResult:
    reactions = pier.reactions
    origin = _girder(reactions.a, reactions.b)
    end = _girder(reactions.d, reactions.c)
    return DeadResult(origin=origin, end=end)


@dataclass(frozen=True)
class DeadLoads:
    """D1 and D2 at one support (decision 70)."""

    d1: Printed
    d2: Printed


@dataclass(frozen=True)
class BearingDead:
    slot: int  # index of the input slot (0..9); empty slots are skipped
    bearing: Bearing  # the entered position and dead loads


@dataclass(frozen=True)
class GirderDeadLoads:
    far: DeadLoads  # A or D, entered totals
    pier: DeadLoads  # B or C, sums of the bearings
    bearings: tuple[BearingDead, ...]


@dataclass(frozen=True)
class DeadLoadsResult:
    origin: GirderDeadLoads
    end: GirderDeadLoads


def _girder_dead(far: EndReaction, slots: tuple[Bearing | None, ...]) -> GirderDeadLoads:
    bearings = tuple(BearingDead(index, bearing) for index, bearing in enumerate(slots) if bearing is not None)
    pier = DeadLoads(*(put(FORCE, total(getattr(item.bearing, field) for item in bearings)) for field in ("d1", "d2")))
    return GirderDeadLoads(far=DeadLoads(far.d1, far.d2), pier=pier, bearings=bearings)


def calculate_dead_loads(pier: PierInput) -> DeadLoadsResult:
    """D1 and D2 at the four supports, without the snow and the train shares (decision 70)."""
    reactions = pier.reactions
    return DeadLoadsResult(origin=_girder_dead(reactions.a, reactions.b), end=_girder_dead(reactions.d, reactions.c))
