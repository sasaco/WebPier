"""The record of scripts/accept_pile_seismic.py (decision 93): the real JRSNAP analyzed the three NDUs of tests/fixtures/inputs/
pile_seismic.json. Here the generator must still write those NDUs byte for byte, so that the record
keeps describing what it writes. The analyses are not run again (they need JRSNAP)."""

import json
from pathlib import Path

from recorded_input_support import input_sha256s
from webpier.calc.column_rebar import column_layout
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.integrity import file_sha256, load_json, sha256
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, write_pile_ndu
from webpier.export.jrsnap.build_pile import build_pile_ndu
from webpier.export.soiljr import parse_sdc
from webpier.export.soiljr.sdc_seismic import parse_seismic
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
RECORD = json.loads((FIXTURES / "acceptance" / "pile_seismic" / "record.json").read_text(encoding="utf-8"))


def test_the_record_is_of_the_input_and_was_accepted():
    assert RECORD["accepted"] is True and RECORD["failures"] == []
    assert RECORD["input"]["sha256"] in input_sha256s((FIXTURES / "inputs" / "pile_seismic.json").read_bytes())
    for name, item in RECORD["ndus"].items():
        assert item["analysis_ok_messages"] == len(item["cases"]) == len(item["db1_sha256"]) == 4, name


def test_the_generator_still_writes_the_analyzed_ndus():
    """From the .sdc SOIL-JR returned for the input (kept beside the record), as the 0710 and 0720 stages build them."""
    data = (FIXTURES / "acceptance" / "pile_seismic" / "pile_seismic.sdc").read_bytes()
    pier = parse_input(load_json((FIXTURES / "inputs" / "pile_seismic.json").read_bytes()))
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc(data))
    reaction = calculate_reaction(pier)
    layout, springs = column_layout(pier), parse_seismic(data)
    written = {}
    for profile, calculate, names in ((LONGITUDINAL, calculate_seismic_longitudinal, ("線路方向.ndu",)),
                                      (TRANSVERSE, calculate_seismic_transverse, ("線路直角方向.ndu", "線路直角方向_逆向.ndu"))):
        result = calculate(pier, foundation, reaction)
        for reverse, name in zip((False, True), names):
            written[name] = write_pile_ndu(build_pile_ndu(profile, pier, layout, result, springs, reverse=reverse))
    assert set(written) == set(RECORD["ndus"])
    for name, item in RECORD["ndus"].items():
        assert sha256(written[name]) == item["sha256"], name
