"""The acceptances recorded before decisions 72 and 84 still belong to the inputs they were recorded from."""

import json
from pathlib import Path

import pytest

from recorded_input_support import (
    BEARING_DEVICES, FORCE_RATIOS, before_bearing_devices, before_custom_tables, before_force_ratios, before_joint,
    before_piles, before_rebar, input_sha256s, upgrade_to_piles, with_bars_in_piles, with_blank_rebar)
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
    before = json.loads(before_piles(before_joint(before_rebar(data))).decode("utf-8"))
    assert "杭基礎" not in before and "杭種" in before["下部構造"]
    upgraded = with_blank_rebar(upgrade_to_piles(before))
    assert upgraded == today
    assert list(upgraded) == list(today)
    assert list(upgraded["下部構造"]) == list(today["下部構造"])


def test_an_input_recorded_before_the_bars_of_the_cast_in_place_pile_is_the_input_without_them():
    """Decisions 91 and 92: the blank 鉄筋.杭 (and the blank bars of the 杭基礎 of decision 91) are no condition of an acceptance
    recorded before them, and entered ones are."""
    data = (ROOT / "tests/fixtures/inputs/current.json").read_bytes()
    older = before_rebar(data)
    document = json.loads(older.decode("utf-8"))
    assert list(document["杭基礎"]["場所打ち杭"]) == ["杭径", "f'ck", "施工条件"] and sha256(older) in input_sha256s(data)
    assert "杭" not in document["鉄筋"]
    assert b"\r\n" in older  # the line ends of the input are kept
    under_91 = json.loads(with_bars_in_piles(data).decode("utf-8"))
    assert list(under_91["杭基礎"]["場所打ち杭"]) == ["杭径", "f'ck", "施工条件", "軸方向鉄筋", "帯鉄筋"]
    assert "杭" not in under_91["鉄筋"] and sha256(with_bars_in_piles(data)) in input_sha256s(data)
    entered = json.loads(data.decode("utf-8"))
    entered["鉄筋"]["杭"]["pure_cover_mm"] = 100.0
    text = (json.dumps(entered, indent=2, ensure_ascii=False) + "\n").replace("\n", "\r\n").encode("utf-8")
    assert before_rebar(text) is None and with_bars_in_piles(text) is None
    assert sha256(older) not in input_sha256s(text) and sha256(with_bars_in_piles(data)) not in input_sha256s(text)


def test_an_input_recorded_before_the_custom_tables_is_rebar_version_3_with_empty_table_overrides():
    """Decision 111: blank custom_tables of the column are no condition of an acceptance recorded before them (rebar
    version 3 with the empty table_overrides in their place), and an entered table is."""
    data = (ROOT / "tests/fixtures/inputs/current.json").read_bytes()
    older = before_custom_tables(data)
    rebar = json.loads(older.decode("utf-8"))["鉄筋"]
    today = json.loads(data.decode("utf-8"))["鉄筋"]
    assert rebar["version"] == 3 and rebar["柱"]["table_overrides"] == {"線路": [], "直角": []}
    assert list(rebar["柱"]) == [("table_overrides" if key == "custom_tables" else key) for key in today["柱"]]
    assert b"\r\n" in older and sha256(older) in input_sha256s(data)  # the line ends of the input are kept
    assert before_custom_tables(older) is None
    entered = json.loads(data.decode("utf-8"))
    entered["鉄筋"]["柱"]["custom_tables"]["線路"] = {"rows": [], "tension_rows": 1}
    text = (json.dumps(entered, indent=2, ensure_ascii=False) + "\n").replace("\n", "\r\n").encode("utf-8")
    assert before_custom_tables(text) is None
    assert BEFORE["tests/fixtures/inputs/current.json"] not in input_sha256s(text)


def test_an_input_recorded_before_decision_125_had_the_bearing_devices_of_decision_59_last_in_each_support():
    """Decision 125 removed 上部構造.支承データ.*.{ゴム支承の箇所数, ストッパーの箇所数, 片持ち梁上のゴム支承,
    片持ち梁上のストッパー}; every recorded input had Example2's counts."""
    data = (ROOT / "tests/fixtures/inputs/current.json").read_bytes()
    older = before_bearing_devices(data)
    support = json.loads(older.decode("utf-8"))["上部構造"]["支承データ"]
    assert support["起点側"] == {"支承名": "可動", "摩擦係数_μ": 0.1, **BEARING_DEVICES["起点側"]}
    assert support["終点側"] == {"支承名": "固定", "摩擦係数_μ": 0.1, "復旧性制動係数": 1.0, **BEARING_DEVICES["終点側"]}
    assert [*BEARING_DEVICES["起点側"].values(), *BEARING_DEVICES["終点側"].values()] == [4, 3, 1, 1, 2, 7, 1, 0]
    assert b"\r\n" in older and sha256(older) in input_sha256s(data)
    assert before_bearing_devices(older) is None  # it has them already
    assert before_bearing_devices(b'{"schema_version": 2}\n') is None and before_bearing_devices(b"[]\n") is None


def test_an_input_recorded_before_the_force_ratios_were_entered_has_none():
    """片持ち梁の照査.疲労.最大変動断面力比 (SA/SC, SB/SC) was entered after decision 125: an acceptance recorded before it
    (under decision 125, or before it with the bearing devices) has the input without them, the rest unchanged."""
    data = (ROOT / "tests/fixtures/inputs/current.json").read_bytes()
    assert json.loads(data.decode("utf-8"))["片持ち梁の照査"]["疲労"][FORCE_RATIOS] == {"A列車": 1.0, "B列車": 1.0}
    without = before_force_ratios(data)
    fatigue = json.loads(without.decode("utf-8"))["片持ち梁の照査"]["疲労"]
    assert list(fatigue) == ["旅客列車本数", "貨物列車本数", "設計耐用年数", "等価繰返し回数"]
    assert b"\r\n" in without and sha256(without) in input_sha256s(data) and before_force_ratios(without) is None
    older = json.loads(before_bearing_devices(data).decode("utf-8"))
    assert FORCE_RATIOS not in older["片持ち梁の照査"]["疲労"]
    assert before_bearing_devices(data) == before_bearing_devices(without)  # the same bytes before decision 125
