"""0600 superstructure reactions and pier self weight.

``calculate_reaction`` returns every value the 0600 report prints and that the
later stages (0610, 0620, 0710, 0720) take over, as Printed values. With a load
model (decision 70) ``calculate_dead_reaction`` gives the dead loads D1 and D2 and
the self weight only: the train, the snow and the forces of the girders are the
load model's, and the input does not have them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import InputError
from ...inputs import PierInput
from .dead import DeadLoadsResult, DeadResult, calculate_dead, calculate_dead_loads
from .longitudinal import LongitudinalResult, calculate_longitudinal
from .self_weight import SelfWeightResult, calculate_self_weight
from .train import TrainResult, calculate_train
from .transverse import TransverseResult, calculate_transverse


@dataclass(frozen=True)
class ReactionResult:
    dead: DeadResult  # dead and snow loads at A..D, bearing shares, track totals
    self_weight: SelfWeightResult  # pier parts, soil, buoyancy, pier-bottom and footing-centre aggregates
    train: TrainResult  # train loading, girder impact tables, seismic train
    longitudinal: LongitudinalResult  # forces on the girders and at the bearings on this pier
    transverse: TransverseResult  # transverse forces, heights and moments at B and C


def _too_large(exc: Exception) -> InputError:
    return InputError(f"0600: 入力が大きすぎるため計算できません（{exc}）")


@dataclass(frozen=True)
class DeadReactionResult:
    """0600 with a load model (decision 70)."""

    dead: DeadLoadsResult  # D1 and D2 at A..D and at each bearing
    self_weight: SelfWeightResult


def calculate_dead_reaction(pier: PierInput) -> DeadReactionResult:
    try:
        return DeadReactionResult(dead=calculate_dead_loads(pier), self_weight=calculate_self_weight(pier))
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise _too_large(exc) from exc


def calculate_reaction(pier: PierInput) -> ReactionResult:
    try:
        dead = calculate_dead(pier)
        self_weight = calculate_self_weight(pier)
        train = calculate_train(pier, dead, self_weight)
        return ReactionResult(
            dead=dead, self_weight=self_weight, train=train,
            longitudinal=calculate_longitudinal(pier, dead, train),
            transverse=calculate_transverse(pier, dead.origin.pier, dead.end.pier, train),
        )
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise _too_large(exc) from exc


__all__ = ["DeadReactionResult", "ReactionResult", "calculate_dead_reaction", "calculate_reaction"]
