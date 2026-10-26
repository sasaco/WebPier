"""0400 照査の前提（構造細目） (decision 73, ADR-0012): the detailing checks of the column (4.2), the beam (4.3) and
the footing (4.4) that the bars and the dimensions decide, from the input alone, and the 中間帯鉄筋 of the column
(ties). A 場所打ち杭 adds the 杭の構造細目 (4.5, decision 98), whose hoops read 1/β of SOIL-JR's .sdc (0500).

The result has a judgement of every check (``ok``) and ``engineering_status``: ok when every check WebPier judges is
satisfied, else not_ok. The checks that use section forces are Capacita's and only referred to (ADR-0012); 9) (the
upper limit of the shear capacity) prints its value and its sign and is not judged (owner 2026-10-21).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...inputs import PierInput, choices
from .beam import BeamDetailing, beam_detailing
from .column import ColumnDetailing, column_detailing
from ..pile_springs import GroundSprings
from .common import need
from .footing import FootingDetailing, footing_detailing
from .pile import DIRECTIONS, PileDetailing, pile_detailing


@dataclass(frozen=True)
class DetailingResult:
    column: ColumnDetailing
    beam: BeamDetailing
    footing: FootingDetailing
    pile: PileDetailing | None  # a 場所打ち杭's (decision 98); None for any other 基礎形式
    # 片持ち梁の照査.外観の照査: whether 0910 has 13.6 使用性, which moves the section 4.3 refers to (13.8 or 13.9)
    cantilever_appearance: bool
    engineering_status: str  # "ok" or "not_ok"


def calculate_detailing(pier: PierInput, springs: GroundSprings | None = None) -> DetailingResult:
    """The checks of *pier*; *springs* (calc.pile_springs.GroundSprings of 0500) give 1/β to a 場所打ち杭's."""
    column, beam, footing = column_detailing(pier), beam_detailing(pier), footing_detailing(pier)
    pile = None
    if pier.substructure.foundation == choices.CAST_IN_PLACE_PILE:
        pile = pile_detailing(pier, _inverse_betas(springs))
    ok = column.ok and beam.ok and footing.ok and (pile is None or pile.ok)
    appearance = need(pier.cantilever_check.appearance, "片持ち梁の照査.外観の照査")
    return DetailingResult(column=column, beam=beam, footing=footing, pile=pile,
                           cantilever_appearance=appearance == choices.APPEARANCE_CHECKED,
                           engineering_status="ok" if ok else "not_ok")


def _inverse_betas(springs: GroundSprings | None) -> Sequence[tuple[str, float]]:
    """1/β of each direction of the .sdc, by the words of the report."""
    assert springs is not None, "a 場所打ち杭's 0400 is calculated once 0500 is complete (pipeline.stages)"
    return [(words, springs.direction(name).inverse_beta) for name, words in DIRECTIONS]
