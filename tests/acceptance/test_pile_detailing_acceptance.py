"""The real-app acceptance of the 杭の構造細目 of a 場所打ち杭 and its cut-off (decision 98, scripts/accept_pile_detailing.py).

The record was made with the real SOIL-JR, JRSNAP and Aggre-SE runners; the pickup, the NDU, the project and the .sdc they
returned are kept beside it, and are read again here with WebPier's own reading (the runners are not run again): Pvmax from the
pickup with the pile rows of the NDU, and the 1/β of the .sdc in the shear span ratio of 0400."""

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from recorded_input_support import input_sha256s
from webpier.calc.detailing.pile import pile_head_reaction
from webpier.core.integrity import file_sha256, load_json
from webpier.export.soiljr import parse_sdc
from webpier.pipeline.fempython import member_forces

ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "tests" / "fixtures" / "acceptance" / "pile_detailing"
RECORD = load_json((EVIDENCE / "record.json").read_bytes())
REDO = "scripts/accept_pile_detailing.py --overwrite で取り直してください。"
SEISMIC_PICKUP = 2


def test_the_record_was_accepted_and_is_of_the_input():
    assert RECORD["accepted"] is True and RECORD["failures"] == [] and RECORD["aggrese_judged"] is False
    assert RECORD["input"]["sha256"] in input_sha256s((ROOT / RECORD["input"]["path"]).read_bytes()), f"入力が変わっています。{REDO}"
    for helper, sha in RECORD["helpers"].items():
        assert file_sha256(ROOT / helper) == sha, f"{helper} が変わっています。{REDO}"


def test_the_kept_files_are_those_of_the_record():
    assert file_sha256(EVIDENCE / "ground.sdc") == RECORD["ground_sdc_sha256"]
    for direction in RECORD["directions"].values():
        for name, sha in direction["files"].items():
            assert file_sha256(EVIDENCE / name) == sha


def test_the_inverse_beta_of_the_kept_sdc_is_the_recorded_one():
    springs = parse_sdc((EVIDENCE / "ground.sdc").read_bytes())
    assert {name: springs.direction(sdc).inverse_beta for name, sdc in (("線路方向", "橋軸方向"), ("線路直角方向", "直角方向"))} \
        == RECORD["inverse_beta"]


@pytest.mark.parametrize("words", ["線路方向", "線路直角方向"])
def test_webpiers_reading_of_the_kept_pickup_gives_the_recorded_pvmax(words):
    """WebPier reads the pickup by the elements of the NDU's model; here the rows are those the project names (dgMemberFirst,
    dgMemberNumber), which the acceptance found to be the first elements of the pile rows of the NDU."""
    direction = RECORD["directions"][words]
    xml = (EVIDENCE / f"{words}.xml").read_bytes().decode("cp932")
    firsts = [int(item) for item in re.findall(r"<int>([^<]*)</int>", re.search(r"<dgMemberFirst>([\s\S]*?)</dgMemberFirst>", xml)[1])]
    piles = [int(float(item)) for item in re.findall(r"<float>([^<]*)</float>",
                                                     re.search(r"<dgMemberNumber>([\s\S]*?)</dgMemberNumber>", xml)[1])]
    assert [str(first) for first in firsts] == direction["rows"]
    lines = member_forces((EVIDENCE / f"{words}_Aggre-SE.pik").read_bytes(), firsts, SEISMIC_PICKUP)
    pvmax = pile_head_reaction([(lines[first], count) for first, count in zip(firsts, piles)])
    assert float(pvmax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) == direction["pvmax"]
    assert abs(direction["pvmax"] - direction["pvmax_found"]) <= 0.006
    assert direction["check_8"] and direction["anchor_pages"] and len(direction["minimum_page"]) == 1
