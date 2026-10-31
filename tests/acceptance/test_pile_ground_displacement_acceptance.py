"""The record of scripts/accept_pile_ground_displacement.py (decision 97): the real SoilStructure, JRSNAP and Aggre-SE made 0711 and
0721 of a pile foundation on G4 with the 応答変位法. Here the generator must still write the NDUs of the 応答変位法 that were analyzed,
byte for byte, from the input, the .sdc SOIL-JR returned, the 地盤変位 SoilStructure returned and the inertia Case Aggre-SE returned
(all kept in the record). The analyses and the checks are not run again (they need the runners)."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from recorded_input_support import input_sha256s, with_steel_cutoff
from webpier.calc.ground_displacement import DISPLACEMENT, PERIOD, GroundDisplacement, GroundPoint, SurfaceLayer
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.response_displacement import InertiaResponse, KH, PERIOD as TEQ, response_displacement
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.integrity import file_sha256, load_json, sha256
from webpier.core.printed import LENGTH, UNIT_WEIGHT, Precision
from webpier.export.soiljr import parse_sdc
from webpier.inputs import choices, parse_input
from webpier.pipeline.stages import STAGES

ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "tests" / "fixtures" / "acceptance" / "pile_ground_displacement"
RECORD = json.loads((EVIDENCE / "record.json").read_text(encoding="utf-8"))
REDO = ("受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_pile_ground_displacement.py "
        "--overwrite")
PILES = STAGES.for_foundation(choices.CAST_IN_PLACE_PILE)
VS = Precision(0, "m/s")


def test_the_record_was_accepted_and_is_of_the_input_kept_beside_it():
    assert RECORD["kind"] == "pile_ground_displacement_acceptance" and RECORD["schema_version"] == 1
    assert RECORD["accepted"] is True and RECORD["failures"] == [] and RECORD["seismic_check_judged"] is False
    assert RECORD["input"]["sha256"] in input_sha256s((ROOT / RECORD["input"]["path"]).read_bytes()), f"入力が変わっています。{REDO}"
    assert RECORD["input"]["kept_sha256"] in input_sha256s((EVIDENCE / RECORD["input"]["kept"]).read_bytes())
    assert set(RECORD["stages"]) == {"0711", "0721"} and set(RECORD["runners"]) == {"soilstructure", "aggrese"}


@pytest.mark.parametrize("helper", sorted(RECORD["helpers"]))
def test_the_recorded_helpers_are_the_files_of_this_checkout(helper):
    assert file_sha256(ROOT / helper) == RECORD["helpers"][helper], f"{helper} が変わっています。{REDO}"


@pytest.mark.parametrize("stage,inertia", [("0711", 4), ("0721", 8)])
def test_every_case_was_aggregated_and_each_of_the_response_was_analyzed_as_written(stage, inertia):
    item = RECORD["stages"][stage]
    assert len(item["cases"]) == item["analysis_ok_messages"] == inertia + len(item["ndus"])
    assert item["first_case"] == inertia + 1 and all("応答変位法" in name for name in item["cases"][inertia:])
    for ndu in item["ndus"]:
        assert ndu["db1"]["kaiseki_flg"] != 1  # the load increment
        applied = -float(ndu["edspx"]) if ndu["reverse"] else float(ndu["edspx"])
        assert ndu["db1"]["head_delta_g"] == pytest.approx(applied, abs=1e-5)
    for correction in item["corrections"]:
        assert correction["ours"] == correction["hand"]


def _ground(recorded) -> GroundDisplacement:
    def point(value):
        return GroundPoint(LENGTH(value["depth"]), DISPLACEMENT(value["l1"]), DISPLACEMENT(value["l2"]))

    layers = tuple(SurfaceLayer(layer["index"], layer["name"], LENGTH(layer["top"]), LENGTH(layer["thickness"]),
                                UNIT_WEIGHT(layer["unit_weight"]), VS(layer["velocity"])) for layer in recorded["layers"])
    return GroundDisplacement(layers, Decimal(repr(recorded["region_coefficient"])), PERIOD(recorded["period"]),
                              tuple(point(value) for value in recorded["profile"]),
                              tuple(point(value) for value in recorded["nodes"]))


@pytest.mark.parametrize("stage,source", [("0711", "0710"), ("0721", "0720")])
def test_the_ndus_of_the_response_are_what_the_generator_writes_now(stage, source):
    pier = parse_input(with_steel_cutoff(load_json((EVIDENCE / RECORD["input"]["kept"]).read_bytes())))  # decision 126
    sdc = (EVIDENCE / "ground.sdc").read_bytes()
    pile_ground = calculate_pile_ground(pier)
    foundation = PileFoundation(pile_ground, parse_sdc(sdc))
    calculate = {"0710": calculate_seismic_longitudinal, "0720": calculate_seismic_transverse}[source]
    ground = _ground(RECORD["ground"][source]["result"])
    seismic = replace(calculate(pier, foundation, calculate_reaction(pier)), ground_displacement=ground)
    results = {"0500": SimpleNamespace(sdc=sdc, ground=pile_ground), source: seismic}
    recorded = RECORD["stages"][stage]
    inertia = recorded["inertia"]
    found = response_displacement(InertiaResponse(inertia["case"], inertia["name"], TEQ(inertia["teq"]), KH(inertia["kheq"]),
                                                  KH(inertia["kh_l1"]), KH(inertia["kh_l2"])), ground.period,
                                  recorded["first_case"])
    written = PILES.get(stage).nonlinear_analysis.response.ndus(results, pier, found)
    assert [(name, sha256(content)) for name, content in written] == [
        (ndu["name"], ndu["sha256"]) for ndu in recorded["ndus"]], f"{stage} の応答変位法の NDU が変わりました。{REDO}"
