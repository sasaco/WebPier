"""Decision 69 in the 0610, 0620, 0710 and 0720 reports: without snow, no 雪荷重 item, case or row; the items and
cases after it move up. The layout and hand checks of the ``no_snow`` variant run with the other frame variants."""

from __future__ import annotations

from frame_report_cases import chain, transverse_chain
from webpier.reporting.stages import longitudinal, seismic_longitudinal, seismic_transverse, transverse


def texts(found: list[dict[str, str]]) -> dict[str, str]:
    return {record["id"]: record["text"] for record in found}


def test_0610_has_no_snow_item_and_17_basic_cases():
    pier, reaction, result, _ = chain("no_snow")
    printed = texts(longitudinal.semantic_records(result, reaction, pier))
    assert not any(key.startswith("0610/snow.") for key in printed)
    assert (printed["0610/train.heading"], printed["0610/impact.heading"], printed["0610/horizontal.heading"]) == (
        "(4) 列車荷重", "(5) 衝撃荷重", "(6) 水平荷重")
    assert "8.2 (5) 3)，4) の値に" in printed["0610/combination.note"]
    basic = printed["0610/basic"]
    assert "雪荷重" not in basic and basic.endswith("17ﾛﾝｸﾞﾚｰﾙ縦荷重復旧性　1.0LR1")
    assert "雪荷重" not in printed["0610/define"] and "雪荷重" not in printed["0610/combination"]


def test_0620_has_no_snow_item_and_14_basic_cases():
    pier, reaction, result, _ = transverse_chain("no_snow")
    printed = texts(transverse.semantic_records(result, reaction, pier))
    assert not any(key.startswith("0620/snow.") for key in printed)
    assert [printed[f"0620/{key}.heading"] for key in ("train", "impact", "lateral", "wind")] == [
        "(4) 列車荷重", "(5) 衝撃荷重", "(6) 車両横荷重", "(7) 風荷重"]
    basic = printed["0620/basic"]
    assert "雪荷重" not in basic and basic.endswith("14風荷重列車荷重がない場合2")
    # Define 6 is the single-track train: basic case 6 (up) or 7 (down); the winds are 13 and 14 in either sign
    define = printed["0620/define"]
    assert "667L1列車荷重単線" in define and define.endswith("1214-14W2風荷重列車荷重がない場合")


def test_0710_and_0720_have_no_snow_case():
    pier, _, _, seismic = chain("no_snow")
    printed = texts(seismic_longitudinal.semantic_records(seismic, pier))
    assert "雪荷重" not in printed["0710/basic"]
    assert "1 + 2 + 3 + 4 + 5 + 6 + 7" in printed["0710/combination"]
    pier, _, _, seismic = transverse_chain("no_snow")
    printed = texts(seismic_transverse.semantic_records(seismic, pier))
    assert "雪荷重" not in printed["0720/basic"]
    assert [printed[f"0720/{key}"] for key in ("train.heading", "girder.heading", "train_inertia.heading")] == [
        "(4) 列車荷重", "(5) 地震時桁荷重慣性力", "(6) 地震時列車荷重慣性力"]
    assert printed["0720/inertia.source"].startswith("(5)，(6) は")
    combinations = printed["0720/combination"]
    assert "1 + 2 + 3 + 4 + 6 + 7 + 8" in combinations and "1 + 2 + 3 + 5 + 6 + 7 + 8" in combinations
