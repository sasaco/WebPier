"""0600 superstructure reactions and pier self weight.

``calculate_reaction`` returns every value the 0600 report prints and that the
later stages (0610, 0620, 0710, 0720) take over, as Printed values.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import InputError
from ...inputs import PierInput
from .dead import DeadResult, calculate_dead
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


def calculate_reaction(pier: PierInput) -> ReactionResult:
    try:
        dead = calculate_dead(pier)
        self_weight = calculate_self_weight(pier)
        train = calculate_train(pier, dead)
        return ReactionResult(
            dead=dead, self_weight=self_weight, train=train,
            longitudinal=calculate_longitudinal(pier, dead, train),
            transverse=calculate_transverse(pier, dead.origin.pier, dead.end.pier, train),
        )
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError(f"0600: 入力が大きすぎるため計算できません（{exc}）") from exc


__all__ = ["ReactionResult", "calculate_reaction"]
