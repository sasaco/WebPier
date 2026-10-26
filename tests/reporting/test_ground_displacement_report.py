"""The 地盤変位 in the reports (decision 97): 10.5 / 11.5 表層地盤の挙動 and the pages of the 応答変位法 before Aggre-SE's.

The values are made up here (calc.ground_displacement and calc.response_displacement are tested on their own); what is checked
is what the pages say, in the order of Example橋脚4 IV-3〜6 and IV-55〜58, and that Aggre-SE's report follows as it is.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest

from webpier.calc.ground_displacement import DISPLACEMENT, PERIOD, GroundDisplacement, GroundPoint, SurfaceLayer
from webpier.calc.response_displacement import InertiaResponse, response_displacement as respond
from webpier.core.printed import LENGTH, UNIT_WEIGHT, Precision
from webpier.reporting.stages.frame_report import Manuscript, semantic_records
from webpier.reporting.stages.ground_displacement import response_displacement, surface_ground
from webpier.reporting.stages.seismic_check import SEISMIC_CHECK, render_pile_seismic_check

KH, TEQ, VS = Precision(3, ""), Precision(3, "s"), Precision(0, "m/s")
LAYERS = (SurfaceLayer(0, "表層", LENGTH(0), LENGTH(2.7), UNIT_WEIGHT(17.0), VS(170)),
          SurfaceLayer(1, "第2層", LENGTH(2.7), LENGTH(3.75), UNIT_WEIGHT(15.0), VS(120)))
GROUND = GroundDisplacement(LAYERS, Decimal("1.0"), PERIOD(0.5335),
                            (GroundPoint(LENGTH(0), DISPLACEMENT(17.11), DISPLACEMENT(220.34)),
                             GroundPoint(LENGTH(2.7), DISPLACEMENT(16.81), DISPLACEMENT(216.49)),
                             GroundPoint(LENGTH(6.45), DISPLACEMENT(0), DISPLACEMENT(0))), ())


def texts(units):
    return {record["id"]: record["text"] for record in semantic_records(units)}


def test_the_surface_ground_has_the_layers_the_formulas_tg_ag_and_the_profile():
    m = Manuscript("0710/")
    surface_ground(m, GROUND, "10.5")
    found = texts(m.units)
    assert found["0710/ground.heading"] == "10.5 表層地盤の挙動"
    assert "表層" in found["0710/ground.layers"] and "120" in found["0710/ground.layers"]
    assert "0.064" in found["0710/ground.l1"] and "0.413" in found["0710/ground.l2"]
    assert "0.5335" in found["0710/ground.surface"] and "220.34" in found["0710/ground.surface"]
    assert "6.450" in found["0710/ground.profile"] and "216.49" in found["0710/ground.profile"]


def _result(kh_l2: float):
    inertia = InertiaResponse(1, "線路方向(Case1_ρm10_αf1_正向)", TEQ(1.138), KH(0.408), KH(0.378), KH(kh_l2))
    return respond(inertia, PERIOD(0.5335), 5)


def test_the_response_pages_have_the_inertia_the_factors_and_the_cases_from_the_first_case():
    m = Manuscript("0711/")
    response_displacement(m, _result(0.428), 5)
    found = texts(m.units)
    assert found["0711/response.heading"] == "応答変位法による設計応答値の算定"
    assert "1.138" in found["0711/response.inertia"] and "0.428" in found["0711/response.inertia"]
    assert "1.067" in found["0711/response.factors"] and "-0.63" in found["0711/response.factors"]
    assert "0711/response.yielded" in found  # L2 past the bend: νU = 1.0
    cases = found["0711/response.cases"]
    assert "L1地震動 ①" in cases and "L2地震動 ④" in cases and "L2地震動 ③" not in cases
    assert cases.index("5L1") < cases.index("11L2")  # the Cases go on from the first one


def test_without_a_yield_the_rule_of_the_bend_is_not_printed():
    m = Manuscript("0711/")
    response_displacement(m, _result(0.400), 5)
    assert "0711/response.yielded" not in texts(m.units)


def _pdf(text: str) -> bytes:
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), text)
        return document.tobytes()


def _pile(response):
    """The result of 0711 of a 場所打ち杭 with the 応答変位法 (decision 98: beside the minimum bars of the pile head reaction)."""
    import json
    from decimal import Decimal

    from webpier.calc.detailing.pile import PileSeismicResult, minimum_bars
    from webpier.inputs import parse_input
    data = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "pile_seismic.json").read_text(encoding="utf-8"))
    return PileSeismicResult(minimum_bars(parse_input(data), "線路方向", Decimal("3000")), response)


def test_the_report_is_webpiers_pages_then_aggreses_report(tmp_path: Path):
    path = render_pile_seismic_check("0711", _pile(_result(0.428)), 5, tmp_path / "0711.pdf",
                                     {SEISMIC_CHECK: _pdf("AGGRESE")})
    with pymupdf.open(path) as document:
        pages = [page.get_text() for page in document]
    found = next(index for index, page in enumerate(pages) if page.strip() == "AGGRESE")
    assert "応答変位法による設計応答値の算定" in pages[0] and 0 < found < len(pages) - 1
    assert "杭頭反力の最大値から定める最小鉄筋量" in pages[-1]


def test_only_aggreses_report_is_taken(tmp_path: Path):
    with pytest.raises(ValueError, match="Aggre-SE の帳票だけを受け取ります"):
        render_pile_seismic_check("0711", _pile(_result(0.428)), 5, tmp_path / "0711.pdf", {})
