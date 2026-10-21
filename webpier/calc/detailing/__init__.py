"""0400 照査の前提（構造細目） (decision 73, ADR-0012): the detailing checks of the column (4.2), the beam (4.3) and
the footing (4.4) that the bars and the dimensions decide, from the input alone, and the 中間帯鉄筋 of the column
(ties).

The result has a judgement of every check (``ok``) and ``engineering_status``: ok when every check WebPier judges is
satisfied, else not_ok. The checks that use section forces are Capacita's and only referred to (ADR-0012); 9) (the
upper limit of the shear capacity) prints its value and its sign and is not judged (owner 2026-10-21).
"""

from __future__ import annotations

from dataclasses import dataclass

from ...inputs import PierInput, choices
from .beam import BeamDetailing, beam_detailing
from .column import ColumnDetailing, column_detailing
from .common import need
from .footing import FootingDetailing, footing_detailing


@dataclass(frozen=True)
class DetailingResult:
    column: ColumnDetailing
    beam: BeamDetailing
    footing: FootingDetailing
    # 片持ち梁の照査.外観の照査: whether 0910 has 13.6 使用性, which moves the section 4.3 refers to (13.7 or 13.8)
    cantilever_appearance: bool
    engineering_status: str  # "ok" or "not_ok"


def calculate_detailing(pier: PierInput) -> DetailingResult:
    column, beam, footing = column_detailing(pier), beam_detailing(pier), footing_detailing(pier)
    ok = column.ok and beam.ok and footing.ok
    appearance = need(pier.cantilever_check.appearance, "片持ち梁の照査.外観の照査")
    return DetailingResult(column=column, beam=beam, footing=footing,
                           cantilever_appearance=appearance == choices.APPEARANCE_CHECKED,
                           engineering_status="ok" if ok else "not_ok")
