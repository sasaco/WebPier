"""0600 input contracts, independently of the 0500 ground-data parser."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import importlib
import json
from pathlib import Path

import pytest

from src.inputs import InputError
from src.reaction_inputs import ReactionInput, SNOW_LOAD_CASES, SnowReactions


# Fixed historical input from fa27cca^, independent of the working input.
SOURCE = Path(__file__).resolve().parent / "fixtures" / "baseline_input.json"


@pytest.fixture
def source():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def parse(data):
    # Import inside the test so a missing implementation is a test failure,
    # never an accidental collection-error Red.
    return importlib.import_module("src.reaction_inputs").parse_reaction_input(data)


def put(data, path, value):
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize("value", ["missing", None, 0, 1, 1.234])
def test_recovery_brake_coefficient_is_optional_and_preserves_explicit_values(source, value):
    support = source["上部構造"]["支承データ"]["終点側"]
    if value != "missing":
        support["復旧性制動係数"] = value
    original = deepcopy(source)
    spans = parse(source).spans
    assert spans.c.recovery_brake_coefficient == (None if value == "missing" else value)
    assert spans.b.recovery_brake_coefficient is None
    assert source == original


@pytest.mark.parametrize("value", [-.1, True, "1", "-", {}, float("inf"), float("nan")])
def test_recovery_brake_coefficient_rejects_invalid_value_with_path(source, value):
    source["上部構造"]["支承データ"]["終点側"]["復旧性制動係数"] = value
    with pytest.raises(InputError, match=r"上部構造\.支承データ\.終点側\.復旧性制動係数"):
        parse(source)


def test_existing_input_and_frozen_model(source):
    result = parse(source)
    assert result.geometry.b1 == 2.2
    assert result.geometry.w8 == 7
    assert result.geometry.h6 == 2
    assert result.geometry.unit_weight_body == 24.5
    assert result.geometry.unit_weight_soil == 18
    assert result.spans.b.span == 27
    assert result.spans.c.span == 25.2
    assert result.spans.b.bearing == "固定"
    assert result.spans.c.bearing == "可動"
    assert result.spans.b.f == 0.375
    assert result.train.length == 16.4
    assert result.train.axle_load == 170
    assert result.train.n == 10
    assert result.dead.a.d1 == 890
    assert result.dead.d.d1 == 840
    assert len(result.dead.b) == len(result.dead.c) == 10
    assert result.dead.b[0].position == -2.441
    assert result.dead.b[0].factors == (0.5, 0, 0, 0)
    with pytest.raises(FrozenInstanceError):
        result.train.n = 20


@pytest.mark.parametrize("side,other,attribute", [("起点側", "終点側", "b"), ("終点側", "起点側", "c")])
@pytest.mark.parametrize("missing", [None, "missing"])
def test_support_position_uses_explicit_values_and_only_defaults_missing(source, side, other, attribute, missing):
    source["上部構造"]["起点側"]["桁長"]["L2"] = 0.575
    source["上部構造"]["終点側"]["桁長"]["L1"] = 0.375
    source["上部構造"][other]["支承位置_f"] = 0.4
    if missing == "missing":
        del source["上部構造"][side]["支承位置_f"]
    else:
        source["上部構造"][side]["支承位置_f"] = None
    before = deepcopy(source)
    assert getattr(parse(source).spans, attribute).f == 0.55
    assert source == before
    source["上部構造"][side]["支承位置_f"] = 0
    assert getattr(parse(source).spans, attribute).f == 0


def test_both_missing_support_positions_retain_legacy_length_fallback(source):
    for side in ("起点側", "終点側"):
        source["上部構造"][side].pop("支承位置_f", None)
    parsed = parse(source)
    assert parsed.spans.b.f == source["上部構造"]["起点側"]["桁長"]["L2"]
    assert parsed.spans.c.f == source["上部構造"]["終点側"]["桁長"]["L1"]


@pytest.mark.parametrize("bad", [True, "0.4", {}, float("nan"), float("inf")])
def test_explicit_invalid_support_position_is_not_hidden_by_fallback(source, bad):
    source["上部構造"]["起点側"]["支承位置_f"] = bad
    with pytest.raises(InputError, match="支承位置_f"):
        parse(source)


@pytest.mark.parametrize("side", ["起点側", "終点側"])
@pytest.mark.parametrize("bad", ["missing", None, True, False, "2.5", -1,
                                  float("nan"), float("inf"), {}, []])
def test_hs_requires_an_explicit_finite_nonnegative_number(source, side, bad):
    span = source["上部構造"][side]
    if bad == "missing":
        del span["重心高_hs"]
    else:
        span["重心高_hs"] = bad
    with pytest.raises(InputError, match=f"上部構造.{side}.重心高_hs"):
        parse(source)


def test_bc_cached_totals_and_unrelated_ground_fields_are_not_inputs(source):
    expected = parse(source)
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        for point in points:
            source["上部工反力"][side].setdefault(point, {})["合計"] = {
                "固定死荷重_D1": 9999, "付加死荷重_D2": 9999,
                "列車分担": {f"L{i}": 9999 for i in range(1, 5)},
            }
    wet = source["地盤データ"]["層"][0]["単位体積重量"]["湿潤"]
    source["地盤データ"] = {"層": [{"単位体積重量": {"湿潤": wet}}]}
    assert parse(source) == expected
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        for point in points:
            del source["上部工反力"][side][point]["合計"]
    assert parse(source) == expected


def test_changed_details_negative_position_and_recomputed_end_reactions(source):
    source["上部工反力"]["起点側"]["B支点"]["支承"][0]["固定死荷重_D1"] = 900
    source["上部工反力"]["起点側"]["B支点"]["支承"][0]["支承位置"] = -9
    source["上部工反力"]["終点側"]["C支点"]["支承"][0]["付加死荷重_D2"] = 25
    source["上部工反力"]["終点側"].setdefault("D支点", {})["合計"] = {"固定死荷重_D1": 123}
    result = parse(source)
    assert result.dead.b[0].d1 == 900
    assert result.dead.b[0].position == -9
    assert result.dead.a.d1 == 1320
    assert result.dead.d.d1 == 123
    assert result.dead.d.d2 == 25


@pytest.mark.parametrize("side,point,inner", [("起点側", "A支点", "a"), ("終点側", "D支点", "d")])
def test_manual_end_reactions_use_zero_negative_and_blank_fallback(source, side, point, inner):
    baseline = getattr(parse(source).dead, inner)
    total = source["上部工反力"][side].setdefault(point, {})["合計"] = {
        "固定死荷重_D1": 0, "付加死荷重_D2": -12.5,
    }
    result = getattr(parse(source).dead, inner)
    assert (result.d1, result.d2) == (0, -12.5)
    total["固定死荷重_D1"] = None
    assert getattr(parse(source).dead, inner).d1 == baseline.d1
    del total["付加死荷重_D2"]
    assert getattr(parse(source).dead, inner) == baseline


@pytest.mark.parametrize("bad", [True, "12", "-", float("nan"), float("inf")])
def test_invalid_manual_end_reaction_has_full_input_path(source, bad):
    source["上部工反力"]["起点側"].setdefault("A支点", {})["合計"] = {"固定死荷重_D1": bad}
    with pytest.raises(InputError, match=r"上部工反力.起点側.A支点.合計.固定死荷重_D1"):
        parse(source)


def test_empty_bearings_and_unconsumed_lines(source):
    factors = source["上部工反力"]["起点側"]["B支点"]["支承"][0]["列車分担"]
    factors.update(L2=0.25, L3=0.125, L4=0.0625)
    result = parse(source)
    assert result.dead.b[2].position is None
    assert result.dead.b[2].d1 == result.dead.b[2].d2 == 0
    assert result.dead.b[2].factors == (0, 0, 0, 0)
    assert result.dead.b[0].factors == (0.5, 0.25, 0.125, 0.0625)
    assert any("L3" in warning and "L4" in warning and "0600" in warning for warning in result.warnings)


@pytest.fixture
def distribution_source(source):
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        for row in source["上部工反力"][side][point]["支承"]:
            row["列車分担"] = dict.fromkeys(("L1", "L2", "L3", "L4"))
    return source


@pytest.mark.parametrize("side,point,attribute", [("起点側", "B支点", "b"), ("終点側", "C支点", "c")])
@pytest.mark.parametrize("second", [(0.02, -0.25, 0.5, 0.75), (0.5, -0.125, 0.5, -0.25)])
def test_signed_train_distributions_preserve_zero_and_nonzero_totals(distribution_source, side, point, attribute, second):
    first = (-0.02, 0.25, -0.5, -0.75)
    rows = distribution_source["上部工反力"][side][point]["支承"]
    for row, values in zip(rows, (first, second)):
        row["列車分担"] = dict(zip(("L1", "L2", "L3", "L4"), values))
    before = deepcopy(distribution_source)
    parsed = getattr(parse(distribution_source).dead, attribute)
    assert parsed[0].factors == first
    assert parsed[1].factors == second
    assert all(row.factors == (0, 0, 0, 0) for row in parsed[2:])
    assert tuple(sum(row.factors[i] for row in parsed) for i in range(4)) == tuple(a + b for a, b in zip(first, second))
    assert distribution_source == before


@pytest.mark.parametrize("side,point", [("起点側", "B支点"), ("終点側", "C支点")])
@pytest.mark.parametrize("line", ["L1", "L2", "L3", "L4"])
@pytest.mark.parametrize("bad", [True, "0.25", "-", {}, float("nan"), float("inf"), -float("inf")])
def test_signed_train_distributions_still_require_finite_numbers(distribution_source, side, point, line, bad):
    distribution_source["上部工反力"][side][point]["支承"][0]["列車分担"][line] = bad
    with pytest.raises(InputError) as failure:
        parse(distribution_source)
    assert f"上部工反力.{side}.{point}.支承[0].列車分担.{line}" in str(failure.value)


def test_zero_h3_negative_water_and_two_axle_branch(source):
    source["下部構造"]["寸法"]["高さ"]["H3"] = 0
    source["下部構造"]["水位"]["高水位_hw1"] = -2
    source["上部構造"]["列車"]["軸距"]["a2"] = 0
    source["上部構造"]["列車"]["編成数"] = 200
    result = parse(source)
    assert result.geometry.h3 == 0
    assert result.geometry.hw1 == -2
    assert result.train.a2 == 0
    assert result.train.n == 200


@pytest.mark.parametrize(("path", "value", "label"), [
    (("schema_version",), True, "schema_version"),
    (("schema_version",), 2, "schema_version"),
    (("下部構造", "杭種", "選択値"), "場所打ち杭", "下部構造.杭種.選択値"),
    (("上部構造", "起点側", "桁長", "スパン長"), 0, "上部構造.起点側.桁長.スパン長"),
    (("上部構造", "終点側", "遠心", "曲線半径"), -1, "曲線半径"),
    (("上部構造", "起点側", "遠心", "列車速度"), False, "列車速度"),
    (("上部構造", "支承データ", "起点側", "支承名"), "未設定", "支承名"),
    (("上部構造", "支承データ", "起点側", "摩擦係数_μ"), -0.1, "摩擦係数_μ"),
    (("上部構造", "列車", "1両の長さ", "値"), 0, "1両の長さ"),
    (("上部構造", "列車", "1両の長さ", "値"), 8, "1両の長さ"),
    (("上部構造", "列車", "軸距", "a1_連結部"), 0, "a1_連結部"),
    (("上部構造", "列車", "軸距", "a2"), -1, "軸距.a2"),
    (("上部構造", "列車", "軸重", "地震以外", "値"), 0, "地震以外"),
    (("上部構造", "列車", "編成数"), 0, "編成数"),
    (("上部構造", "列車", "編成数"), 201, "編成数"),
    (("上部構造", "列車", "編成数"), 1.5, "編成数"),
    (("上部構造", "列車", "編成数"), True, "編成数"),
    (("下部構造", "寸法", "側面", "B1"), 0, "B1"),
    (("下部構造", "寸法", "正面", "W8"), 0, "W8"),
    (("下部構造", "寸法", "側面", "B4"), 2, "B1"),
    (("下部構造", "寸法", "正面", "W4"), 8, "W1"),
    (("下部構造", "寸法", "高さ", "H4"), 0, "H4"),
    (("下部構造", "寸法", "高さ", "H6"), float("nan"), "H6"),
    (("下部構造", "水位", "高水位_hw1"), float("inf"), "高水位_hw1"),
    (("下部構造", "単位体積重量", "梁・躯体"), "24.5", "梁・躯体"),
    (("上部工反力", "起点側", "B支点", "支承"), [], "支承"),
    (("上部工反力", "起点側", "B支点", "支承", 0, "支承位置"), True, "支承位置"),
    (("上部工反力", "起点側", "B支点", "支承", 0, "固定死荷重_D1"), -1, "固定死荷重_D1"),
    (("上部工反力", "起点側", "B支点", "支承", 0, "付加死荷重_D2"), -1, "付加死荷重_D2"),
])
def test_invalid_values_include_the_input_path(source, path, value, label):
    put(source, path, value)
    with pytest.raises(InputError, match=label):
        parse(source)


def test_missing_input_includes_full_japanese_path(source):
    del source["上部構造"]["終点側"]["高さ"]["h3"]
    with pytest.raises(InputError, match=r"上部構造.終点側.高さ.h3"):
        parse(source)


@pytest.mark.parametrize("side", ["起点側", "終点側"])
@pytest.mark.parametrize("bad", [None, "missing", True, "0.5", -1, float("nan"), float("inf")])
def test_h4_requires_an_explicit_valid_number_without_fixed_fallback(source, side, bad):
    heights = source["上部構造"][side]["高さ"]
    if bad == "missing":
        del heights["h4"]
    else:
        heights["h4"] = bad
    with pytest.raises(InputError, match=f"上部構造.{side}.高さ.h4"):
        parse(source)


@pytest.mark.parametrize("side,point", [("起点側", "B支点"), ("終点側", "C支点")])
@pytest.mark.parametrize("bad", ["missing", True, "0.5", "-", float("nan"), float("inf")])
def test_d2_position_rejects_invalid_or_missing_value_without_fixed_fallback(source, side, point, bad):
    row = source["上部工反力"][side][point]["支承"][1]
    if bad == "missing":
        del row["支承位置"]
    else:
        row["支承位置"] = bad
    with pytest.raises(InputError, match="支承位置"):
        parse(source)


def test_load_utf8_and_invalid_json(tmp_path, source):
    module = importlib.import_module("src.reaction_inputs")
    path = tmp_path / "入力.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8-sig")
    assert module.load_reaction_input(path) == parse(source)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(InputError, match="JSON"):
        module.load_reaction_input(path)


SNOW_KEYS = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")


def snow_records(data):
    for side, local, end in (("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")):
        yield from data["上部工反力"][side][local]["支承"]
        yield data["上部工反力"][side].setdefault(end, {}).setdefault("合計", {})


def test_snow_case_names_and_legacy_constructor_are_compatible(source):
    assert SNOW_LOAD_CASES == (
        ("雪荷重_2年確率", "雪荷重 2年確率"),
        ("雪荷重_10年確率", "雪荷重 10年確率"),
        ("雪荷重_30年確率", "雪荷重 30年確率"),
    )
    assert isinstance(SNOW_LOAD_CASES, tuple)
    assert all(isinstance(case, tuple) for case in SNOW_LOAD_CASES)
    inputs = parse(source)
    legacy = ReactionInput(inputs.geometry, inputs.spans, inputs.train, inputs.dead, ("legacy",))
    assert legacy.warnings == ("legacy",)
    assert legacy.snow == SnowReactions()
    assert set(vars(inputs.dead.b[0])) == {"position", "d1", "d2", "factors"}


def test_missing_and_null_snow_are_frozen_and_do_not_mutate_input(source):
    for record in snow_records(source):
        for key in SNOW_KEYS:
            record.pop(key, None)
    before = deepcopy(source)
    missing = parse(source)
    assert source == before
    assert missing.snow == SnowReactions()
    for record in snow_records(source):
        record.update(dict.fromkeys(SNOW_KEYS))
    before = deepcopy(source)
    blank = parse(source)
    assert source == before
    assert blank == missing
    with pytest.raises(FrozenInstanceError):
        blank.snow.a = (0, 0, 0)
    with pytest.raises(TypeError):
        blank.snow.b[0][0] = 1


def test_partial_snow_and_signed_end_inputs_preserve_explicit_zero(source):
    for record in snow_records(source):
        for key in SNOW_KEYS:
            record.pop(key, None)
    source["上部工反力"]["起点側"]["B支点"]["支承"][9][SNOW_KEYS[2]] = 9
    source["上部工反力"]["終点側"]["C支点"]["支承"][0][SNOW_KEYS[1]] = 7
    source["上部工反力"]["起点側"]["A支点"]["合計"].update({SNOW_KEYS[0]: 0, SNOW_KEYS[2]: -2})
    source["上部工反力"]["終点側"]["D支点"]["合計"].update({SNOW_KEYS[0]: -3, SNOW_KEYS[1]: None})
    before = deepcopy(source)
    result = parse(source).snow
    assert source == before
    assert result.b[9] == (0, 0, 9)
    assert result.c[0] == (0, 7, 0)
    assert result.a == (0, None, -2)
    assert result.d == (-3, None, None)


@pytest.mark.parametrize("key", SNOW_KEYS)
@pytest.mark.parametrize("side,point,detail", [
    ("起点側", "B支点", True), ("終点側", "C支点", True),
    ("起点側", "A支点", False), ("終点側", "D支点", False),
])
@pytest.mark.parametrize("bad", [
    True, False, "12", "-", "", [], {}, float("nan"), float("inf"), float("-inf"),
    pytest.param(10**400, id="integer-overflow"),
])
def test_invalid_snow_has_its_full_input_path(source, key, side, point, detail, bad):
    parent = source["上部工反力"][side].setdefault(point, {})
    if detail:
        parent["支承"][9][key] = bad
        path = rf"上部工反力\.{side}\.{point}\.支承\[9\]\.{key}"
    else:
        parent.setdefault("合計", {})[key] = bad
        path = rf"上部工反力\.{side}\.{point}\.合計\.{key}"
    with pytest.raises(InputError, match=path):
        parse(source)


@pytest.mark.parametrize("key", SNOW_KEYS)
@pytest.mark.parametrize("side,point", [("起点側", "B支点"), ("終点側", "C支点")])
def test_negative_snow_detail_is_rejected(source, key, side, point):
    source["上部工反力"][side][point]["支承"][0][key] = -0.1
    with pytest.raises(InputError, match=rf"上部工反力\.{side}\.{point}\.支承\[0\]\.{key}"):
        parse(source)


@pytest.mark.parametrize("bad", [None, [], False, "-"])
@pytest.mark.parametrize("side,point", [("起点側", "A支点"), ("終点側", "D支点")])
@pytest.mark.parametrize("level", ["point", "total"])
def test_snow_does_not_relax_parent_object_validation(source, bad, side, point, level):
    if level == "point":
        source["上部工反力"][side][point] = bad
        path = f"上部工反力.{side}.{point}"
    else:
        source["上部工反力"][side].setdefault(point, {})["合計"] = bad
        path = f"上部工反力.{side}.{point}.合計"
    with pytest.raises(InputError, match=path):
        parse(source)


def test_snow_optional_fields_do_not_relax_required_dead_input(source):
    row = source["上部工反力"]["起点側"]["B支点"]["支承"][0]
    row[SNOW_KEYS[0]] = 1
    del row["固定死荷重_D1"]
    with pytest.raises(InputError, match=r"上部工反力.起点側.B支点.支承\[0\].固定死荷重_D1"):
        parse(source)


@pytest.mark.parametrize("side,point", [("起点側", "B支点"), ("終点側", "C支点")])
@pytest.mark.parametrize("bad", [None, [], True, "-"])
@pytest.mark.parametrize("level", ["point", "rows", "row"])
def test_snow_does_not_relax_bearing_parent_validation(source, side, point, bad, level):
    if level == "point":
        source["上部工反力"][side][point] = bad
    elif level == "rows":
        source["上部工反力"][side][point]["支承"] = bad
    else:
        source["上部工反力"][side][point]["支承"][9] = bad
    before = deepcopy(source)
    with pytest.raises(InputError, match=rf"上部工反力\.{side}\.{point}\.支承"):
        parse(source)
    assert source == before
