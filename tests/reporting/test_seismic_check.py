"""0711 and 0721: the report is Aggre-SE's report, byte for byte (decision 56, ADR-0009)."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen import canvas

from webpier.calc.detailing.pile import PileSeismicResult, minimum_bars
from webpier.inputs import parse_input
from webpier.reporting.stages.seismic_check import PILE_ANCHOR_BAR, SEISMIC_CHECK, render_pile_seismic_check, render_seismic_check


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


def stand_in(mark: str) -> bytes:
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    page.drawString(60, 780, mark)
    page.showPage()
    page.save()
    return stream.getvalue()


def pile_result() -> PileSeismicResult:
    data = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "pile_seismic.json").read_text(encoding="utf-8"))
    return PileSeismicResult(minimum_bars(parse_input(data), "線路直角方向", Decimal("2345.678")), None)


def pages_of(path: Path) -> list[str]:
    with pymupdf.open(path) as pdf:
        return [page.get_text() for page in pdf]


def test_a_cast_in_place_pile_has_the_minimum_bars_after_aggre_ses_report_and_its_cut_off_last(tmp_path: Path):
    """Decision 98: Aggre-SE's report, WebPier's page of (1) of the sample 0440 2.4, the 杭の段落とし計算書."""
    path = render_pile_seismic_check("0721", pile_result(), None, tmp_path / "0721.pdf",
                             {SEISMIC_CHECK: stand_in("FAKE AGGRESE"), PILE_ANCHOR_BAR: stand_in("FAKE ANCHOR")})
    found = pages_of(path)
    assert "FAKE AGGRESE" in found[0] and "FAKE ANCHOR" in found[-1]
    middle = "".join(found[1:-1])
    # Pvmax 2345.678 → 2345.68; As' = 0.0104 × 2345.68 × 10³／(0.85 × 30.0 + 0.008 × 345) = 24395.07／28.26 = 863.2
    assert "杭頭反力の最大値から定める最小鉄筋量" in middle and "2345.68" in middle and "Ｌ２応答時：線路直角方向" in middle
    assert "863.2" in middle and "15884.0" in middle  # As of D32 − 20 本 = 794.2 × 20
    alone = pages_of(render_pile_seismic_check("0721", pile_result(), None, tmp_path / "alone.pdf",
                                       {SEISMIC_CHECK: stand_in("FAKE AGGRESE")}))
    assert "FAKE AGGRESE" in alone[0] and "FAKE ANCHOR" not in "".join(alone)


@pytest.mark.parametrize("pages", [{}, {PILE_ANCHOR_BAR: b"%PDF"}, {SEISMIC_CHECK: b"%PDF", "data_check": b"%PDF"}])
def test_a_pile_takes_aggre_ses_reports_only(tmp_path: Path, pages):
    with pytest.raises(ValueError, match="Aggre-SE の帳票だけを受け取ります"):
        render_pile_seismic_check("0711", pile_result(), None, tmp_path / "0711.pdf", pages)
