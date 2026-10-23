"""The acceptances recorded before decisions 72 and 84 still belong to the inputs they were recorded from."""

import json
from pathlib import Path

import pytest

from recorded_input_support import before_piles, input_sha256s, upgrade_to_piles
from webpier.core.integrity import sha256

ROOT = Path(__file__).parents[2]
# SHA256 of the inputs as they were before the pile foundation (HEAD of 2026-10-23, before decision 84); the
# project's own pre/input.json is not here: its owner edits it (the 出力項目 …), so its bytes are no fixture
BEFORE = {
    "tests/fixtures/inputs/current.json": "1cbfb7c8fd7d51d3c5965a84514f6aa6e0c9307daef0f5956cdd482526dfc4fa",
    "tests/fixtures/acceptance/footing/input.json": "c525986407504f65cf159f3e408435c5013397fa05dfc3ae2790ceadbcc6da01",
}


@pytest.mark.parametrize("path", BEFORE)
def test_the_input_is_still_the_one_an_earlier_acceptance_was_recorded_from(path):
    data = (ROOT / path).read_bytes()
    assert BEFORE[path] in input_sha256s(data)
    assert sha256(data) in input_sha256s(data)


@pytest.mark.parametrize("change", [
    lambda d: d["下部構造"].update(基礎形式="場所打ち杭"),
    lambda d: d["杭基礎"].update(杭長=19.0),
    lambda d: d["地盤データ"]["層"][1].update(De=0.5),
], ids=["pile foundation", "entered pile item", "entered De"])
def test_a_pile_foundation_or_an_entered_pile_item_is_no_older_input(change):
    document = json.loads((ROOT / "tests/fixtures/inputs/current.json").read_bytes().decode("utf-8"))
    change(document)
    changed = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").replace("\n", "\r\n").encode("utf-8")
    assert BEFORE["tests/fixtures/inputs/current.json"] not in input_sha256s(changed)


@pytest.mark.parametrize("data", [b'{"schema_version": 2}\n', b"[]\n"])
def test_an_input_without_the_pile_foundation_has_no_older_form(data):
    assert input_sha256s(data) == {sha256(data)}


def test_upgrading_the_input_of_before_the_pile_foundation_gives_the_input_of_today():
    """The way back and the way forward are inverses on the checked-in input (decision 84)."""
    data = (ROOT / "tests/fixtures/inputs/current.json").read_bytes()
    today = json.loads(data.decode("utf-8"))
    before = json.loads(before_piles(data).decode("utf-8"))
    assert "杭基礎" not in before and "杭種" in before["下部構造"]
    assert upgrade_to_piles(before) == today
    assert list(upgrade_to_piles(before)) == list(today)
    assert list(upgrade_to_piles(before)["下部構造"]) == list(today["下部構造"])
