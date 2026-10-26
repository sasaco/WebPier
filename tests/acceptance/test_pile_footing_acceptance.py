"""The record of scripts/accept_pile_footing.py (decision 96): the real FEMPython, JRSNAP, Aggre-SE and Capacita made 0800, 0810 and 0820 of
tests/fixtures/inputs/pile_seismic.json. Here, from the files the runners returned (kept beside the record) and the .sdc SOIL-JR
returned, the generator must still find in 0800 the section forces the record holds and write the WDJs Capacita checked byte for byte,
so that the record keeps describing what it writes. The runners are not run again."""

import json
from pathlib import Path

import pytest

from recorded_input_support import input_sha256s
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_footing import calculate_footing, complete_footing
from webpier.calc.pile_footing_check import calculate_pile_footing_check
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.calc.transverse import calculate_transverse
from webpier.core.integrity import file_sha256, load_json, sha256
from webpier.export.capacita.pile_footing_wdj import build_pile_footing_wdj, write_pile_footing_wdj
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input
from webpier.pipeline.stages import pile_footing_forces

FIXTURES = Path(__file__).parents[1] / "fixtures"
EVIDENCE = FIXTURES / "acceptance" / "pile_footing"
RECORD = json.loads((EVIDENCE / "record.json").read_text(encoding="utf-8"))
STEMS = {"longitudinal": "線路方向", "transverse": "線路直角方向"}


def test_the_record_is_of_the_input_and_was_accepted():
    assert RECORD["accepted"] is True and RECORD["failures"] == [] and RECORD["capacita_judged"] is False
    assert RECORD["input"]["sha256"] in input_sha256s((FIXTURES / "inputs" / "pile_seismic.json").read_bytes())
    for name, item in RECORD["directions"].items():
        assert item["worst"]["reading"] <= 0.06 and item["worst"]["head"] <= 0.06 and item["worst"]["moment_shear"] <= 0.2, name
        assert all(count >= 1 for count in item["report"]["pages"].values()), name


@pytest.fixture(scope="module")
def rebuilt():
    pier = parse_input(load_json((FIXTURES / "inputs" / "pile_seismic.json").read_bytes()))
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc((EVIDENCE / "ground.sdc").read_bytes()))
    reaction = calculate_reaction(pier)
    along, across = calculate_longitudinal(pier, foundation, reaction), calculate_transverse(pier, foundation, reaction)
    seismic = {"longitudinal": calculate_seismic_longitudinal(pier, foundation, reaction),
               "transverse": calculate_seismic_transverse(pier, foundation, reaction)}
    bases = calculate_footing(pier, along, across)
    found = {}
    for direction in STEMS:
        stem, basis = STEMS[direction], getattr(bases, direction)
        found[direction] = pile_footing_forces(basis, (EVIDENCE / f"{stem}.pik").read_bytes(),
                                               (EVIDENCE / f"{stem}_Aggre-SE.pik").read_bytes(), seismic[direction].frame)
    return pier, complete_footing(bases, found["longitudinal"], found["transverse"])


@pytest.mark.parametrize("direction", STEMS)
def test_the_generator_finds_the_forces_the_record_holds(rebuilt, direction):
    _, result = rebuilt
    points = getattr(result, direction).points
    recorded = RECORD["directions"][direction]["points"]
    assert [point.point.name for point in points] == [item["name"] for item in recorded]
    for point, item in zip(points, recorded):
        assert point.point.width.be.value == item["be"]
        for force, expected in zip(point.forces, item["forces"]):
            assert (force.case.value, force.pickup, force.md.value, force.md_combination) == (
                expected["case"], expected["pickup"], expected["md"], expected["md_combination"])
            assert (None if force.vd is None else force.vd.value) == expected["vd"]


@pytest.mark.parametrize("direction", STEMS)
def test_the_generator_still_writes_the_wdj_capacita_checked(rebuilt, direction):
    pier, result = rebuilt
    wdj = write_pile_footing_wdj(build_pile_footing_wdj(calculate_pile_footing_check(pier, getattr(result, direction))))
    assert sha256(wdj) == RECORD["directions"][direction]["wdj"]["sha256"]
