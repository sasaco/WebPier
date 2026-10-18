"""0711 and 0721: the report is Aggre-SE's report, byte for byte (decision 56, ADR-0009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from webpier.reporting.stages.seismic_check import SEISMIC_CHECK, render_seismic_check


def test_the_report_is_the_given_pdf_as_it_is(tmp_path: Path):
    path = tmp_path / "0711_線路方向非線形解析.pdf"
    path.write_bytes(b"old")
    assert render_seismic_check(path, {SEISMIC_CHECK: b"%PDF-1.4 Aggre-SE"}) == path
    assert path.read_bytes() == b"%PDF-1.4 Aggre-SE"
    assert sorted(item.name for item in tmp_path.iterdir()) == [path.name]


@pytest.mark.parametrize("pages", [{}, {"load_diagram": b"%PDF"}, {SEISMIC_CHECK: b"%PDF", "data_check": b"%PDF"}])
def test_only_aggre_ses_report_is_taken(tmp_path: Path, pages):
    path = tmp_path / "0711.pdf"
    with pytest.raises(ValueError, match="Aggre-SE の帳票だけを受け取ります"):
        render_seismic_check(path, pages)
    assert not path.exists()
