"""0711 線路方向・0721 線路直角方向の耐震性能照査: Aggre-SE's report is the whole report (decision 56, ADR-0009).

WebPier draws nothing: no heading, no section number (Example2's 10.5 応答値の算定 and 10.6 応答値一覧表 were written
onto Aggre-SE's pages by hand), no page is chosen, reordered or turned. The report is the bytes of the ``report.pdf``
the Aggre-SE runner returned (pipeline.aggrese), which the report receives as ``SEISMIC_CHECK``. A pile foundation on G3〜G5
(decision 97) has WebPier's pages of the 応答変位法 before it (``render_response_check``), Aggre-SE's report then as it is;
they have no grid Excel workbook (its role, 0711.xlsx, is the one of Aggre-SE's summary workbook).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ...calc.response_displacement import ResponseDisplacementResult
from ..assembly import write_as_is
from .frame_report import Manuscript, Unit
from .ground_displacement import response_displacement
from .insertion import Insertion, render_with_pages

SEISMIC_CHECK = "seismic_check"  # Aggre-SE's report (0711, 0721)


def render_seismic_check(path: str | Path, pages: Mapping[str, bytes]) -> Path:
    """Aggre-SE's report as the report at *path*, as it is; atomically replaces *path*."""
    if set(pages) != {SEISMIC_CHECK}:
        raise ValueError(f"耐震性能照査の計算書には Aggre-SE の帳票だけを受け取ります: {'・'.join(sorted(pages))}")
    return write_as_is(pages[SEISMIC_CHECK], path)


def content(stage_id: str, result: ResponseDisplacementResult, first_case: int) -> tuple[Unit, ...]:
    m = Manuscript(f"{stage_id}/")
    response_displacement(m, result, first_case)
    return tuple(m.units)


def _insertions(units: tuple[Unit, ...]) -> tuple[Insertion, ...]:
    return (Insertion(SEISMIC_CHECK, units[-1].key),)


def render_response_check(stage_id: str, result: ResponseDisplacementResult, first_case: int, path: str | Path,
                          pages: Mapping[str, bytes]) -> Path:
    """The pages of the 応答変位法, then Aggre-SE's report as it is (decision 97); atomically replaces *path*."""
    if set(pages) != {SEISMIC_CHECK}:
        raise ValueError(f"耐震性能照査の計算書には Aggre-SE の帳票だけを受け取ります: {'・'.join(sorted(pages))}")
    units = content(stage_id, result, first_case)
    return render_with_pages(units, _insertions(units), pages, path)
