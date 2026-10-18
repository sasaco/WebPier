"""0711 線路方向・0721 線路直角方向の耐震性能照査: Aggre-SE's report is the whole report (decision 56, ADR-0009).

WebPier draws nothing: no heading, no section number (Example2's 10.5 応答値の算定 and 10.6 応答値一覧表 were written
onto Aggre-SE's pages by hand), no page is chosen, reordered or turned. The report is the bytes of the ``report.pdf``
the Aggre-SE runner returned (pipeline.aggrese), which the report receives as ``SEISMIC_CHECK``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..assembly import write_as_is

SEISMIC_CHECK = "seismic_check"  # Aggre-SE's report (0711, 0721)


def render_seismic_check(path: str | Path, pages: Mapping[str, bytes]) -> Path:
    """Aggre-SE's report as the report at *path*, as it is; atomically replaces *path*."""
    if set(pages) != {SEISMIC_CHECK}:
        raise ValueError(f"耐震性能照査の計算書には Aggre-SE の帳票だけを受け取ります: {'・'.join(sorted(pages))}")
    return write_as_is(pages[SEISMIC_CHECK], path)
