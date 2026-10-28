"""FrameWeb Define, Combine and Pickup: Example2 08 pp.8-9 to 8-11 and its FrameWeb file, Example橋脚4 表2.3.2.

FrameWeb analyses each load case once per spring set and combines the responses linearly: a Define row lists
the load cases it may take (a negative number is the same case reversed, FrameWeb takes the worse), a Combine
row multiplies Defines by coefficients, a Pickup row lists the Combines it envelopes.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from frameweb_support import D, EXAMPLE2, PEDESTAL, example2_cases, first_placing, longitudinal
from webpier.calc.longitudinal import Basis, BasicCase, Check, Layout
from webpier.calc.longitudinal.combinations import EXTRACTION_NAMES
from webpier.core.errors import InputError
from webpier.export.frameweb import build_frameweb


# Decision 120 (Example橋脚4 表2.3.2): 48 combinations — each check made at low and high water and for the 列車の配置
# ①②③ where it applies — and 8 pickups of those; Example2 8-10/8-11 have 16 combinations (classification 3), so the
# Combine and Pickup tables are checked against the calc result, not against Example2.


def auxiliary_defines(result):
    """The Define of each serviceability impact load case, after the basic cases: I2s of ①, ② and ③ (decision 120)."""
    first = len(result.basic_cases) + 1
    return {(BasicCase.IMPACT_DOUBLE, layout): first + index for index, layout in enumerate(Layout)}


@pytest.fixture(scope="module")
def result():
    return longitudinal()


@pytest.fixture(scope="module")
def full(result):
    return build_frameweb(result)


@pytest.fixture(scope="module")
def current(full):
    """The file of ① only, as Example2's (decision 102)."""
    return first_placing(full)


def coefficients(row):
    return {key: value for key, value in row.items() if key.startswith("C")}


def test_defines_take_each_basic_case_and_the_serviceability_impacts(full, result):
    # One Define per basic case, the horizontal ones also reversed (−n); after them one per I2s of ①, ② and ③.
    assert len(result.basic_cases) == 38 and len(full["define"]) == 41
    for basic in result.basic_cases:
        n = basic.number
        assert full["define"][str(n)] == ({"row": n, "C1": n, "C2": -n} if basic.horizontal else {"row": n, "C1": n})
    assert [full["define"][str(n)] for n in (39, 40, 41)] == [{"row": n, "C1": n} for n in (39, 40, 41)]


def test_the_defines_of_the_example2_cases_are_those_of_example2(current):
    # The cases Example2 still has (decision 120 (g): not 9 and 11) keep its Define: n, and −n for 13-20.
    number_of = example2_cases(current)
    for example, ours in number_of.items():
        expected = {key: value // abs(value) * int(number_of[str(abs(value))]) for key, value in
                    coefficients(EXAMPLE2["define"][example]).items()}
        assert coefficients(current["define"][ours]) == expected, example


def test_the_combine_and_pickup_counts(full):
    assert list(full["combine"]) == [str(n) for n in range(1, 49)]
    assert list(full["pickup"]) == [str(n) for n in range(1, 9)]


def test_combines_carry_the_printed_factors(full, result):
    define_of = {(d.case, d.layout): d.number for d in result.define_cases}
    auxiliary = auxiliary_defines(result)
    for combination in result.combinations:
        row = full["combine"][str(combination.number)]
        expected = {}
        for component in combination.components:
            key = (component.case, component.source.layout)
            define = define_of[key] if component.basis is Basis.BASIC else auxiliary[key]
            expected[f"C{define}"] = component.factor.value
        assert coefficients(row) == expected
        assert row["row"] == combination.number
        assert all(component.factor.digits in (1, 2) for component in combination.components)


@pytest.mark.parametrize("number", [1, 16, 35])
def test_combine_coefficients_are_those_of_the_table(full, result, number):
    # Each load case's factor is the calc coefficient of its basic case (表2.3.2): 1 is 破壊 列車最大 低水位 ①, 16 破壊
    # 制動最大 死荷重低減 高水位 ①, 35 縁応力度 低水位 ②. The serviceability I (printed 0.75 ρs on the basic I2-2,
    # Define 13) is analysed as I2s of ② (Define 40) with ρs = 1.0 (8-5: 0.75 i in the girder coefficient).
    combination = result.combinations[number - 1]
    expected = {f"C{basic.number}": coefficient.value
                for basic, coefficient in zip(result.basic_cases, combination.coefficients, strict=True)
                if coefficient is not None}
    if number == 35:
        assert expected.pop("C13") == 0.75
        expected["C40"] = 1
    assert coefficients(full["combine"][str(number)]) == expected
    assert {1: {"C1": 1.1, "C2": 1.2, "C5": 1, "C7": 1, "C9": 1.35, "C12": 1.35, "C19": 1},
            16: {"C1": 0.9, "C2": 0.8, "C3": 1, "C7": 1, "C9": 1.23, "C31": 1},
            35: {"C1": 1, "C2": 1, "C5": 1, "C6": 1, "C10": 1, "C17": 1, "C40": 1}}[number] == expected


def test_combine_names(full):
    # The check, then the water level and the 列車の配置 where the check is made for them (decisions 102, 120).
    names = [full["combine"][str(n)]["name"] for n in range(1, 49)]
    assert len(set(names)) == 48
    assert {n: names[n - 1] for n in (1, 6, 16, 25, 31, 32, 33, 34, 40, 44, 47, 48)} == {
        1: "破壊 列車最大 低水位 両側の桁", 6: "破壊 列車最大 高水位 終点側の桁", 16: "破壊 制動最大 死荷重低減 高水位 両側の桁",
        25: "破壊 ﾛﾝｸﾞ最大 死荷重低減 低水位 両側の桁", 31: "破壊 雪最大 低水位", 32: "破壊 雪最大 高水位", 33: "長期支持",
        34: "ひび割れ・短期支持 縁応力度 低水位 両側の桁", 40: "ひび割れ 永久荷重 低水位", 44: "ひび割れ 変動荷重 終点側の桁",
        47: "損傷 列車最大 終点側の桁", 48: "損傷 雪最大"}


def test_pickups_are_the_extractions(full, result):
    # The 8 groups of 8-11 (使用性（損傷） is the R5 name, decision 73), each with the combinations of its checks: 安全性
    # （安定） takes the safety combinations and 短期支持性能 the edge-stress ones (decision 120).
    pickups = full["pickup"]
    assert [(row["row"], row["name"]) for row in pickups.values()] == [
        (e.number, EXTRACTION_NAMES[e.group]) for e in result.extractions]
    assert [row["name"] for row in pickups.values()] == [
        "安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "使用性（損傷）", "安全性（安定）", "長期支持性能", "短期支持性能"]
    for e in result.extractions:
        assert coefficients(pickups[str(e.number)]) == {f"C{i}": c for i, c in enumerate(e.combinations, 1)}
    assert [tuple(coefficients(row).values()) for row in pickups.values()] == [
        tuple(range(1, 33)), tuple(range(34, 40)), (40, 41), (42, 43, 44), (45, 46, 47, 48), tuple(range(1, 33)), (33,),
        tuple(range(34, 40))]


def native_vector(document, combine, sign):
    """Σ coefficient × load of one Combine, with each Define taking alternative 1 (sign +1) or its last (−1)."""
    vector = {}
    for key, factor in coefficients(document["combine"][str(combine)]).items():
        define = coefficients(document["define"][key[1:]])
        reference = define[f"C{len(define)}"] if sign < 0 else define["C1"]
        case = document["load"][str(abs(reference))]
        scale = D(factor) * (1 if reference > 0 else -1)
        for row in case.get("load_node", []):
            for axis in ("tx", "ty", "rz"):
                if row[axis] is not None:
                    add(vector, (case["fix_node"], "node", row["n"], axis), scale * D(row[axis]))
        for row in case.get("load_member", []):
            add(vector, (case["fix_node"], "member", row["m1"], row["direction"]), scale * D(row["P1"]))
    return vector


def add(vector, key, amount):
    vector[key] = vector.get(key, Decimal(0)) + amount


def resolved_vector(result, combination, sign):
    springs = {"long_term": 1, "short_term": 2}
    vector, count = {}, {}
    for component in combination.signed(sign):
        spring = springs[component.source.spring.value]
        for p in component.points:
            for axis, amount in (("tx", D(p.h.value)), ("ty", D(p.n.value)), ("rz", D(p.m.value))):
                key = (spring, "node", str(p.node), axis)
                add(vector, key, amount)
                count[key] = count.get(key, 0) + 1
        for line in component.line_loads:
            for member in line.members:
                key = (spring, "member", str(member), "gy")
                add(vector, key, D(line.n.value))
                count[key] = count.get(key, 0) + 1
    return vector, count


@pytest.mark.parametrize("changes", [{}, PEDESTAL], ids=["current", "pedestal"])
def test_every_combination_and_direction_is_the_resolved_combination(changes):
    # The calc rounds each resolved action once (factor × printed action -> 2 decimals); FrameWeb multiplies the
    # printed action by the printed factor exactly. They differ by at most 0.005 per resolved action, never more,
    # and the load points, members and spring sets are the same. The reversed direction (Define −n) reverses
    # only the horizontal cases, as Combination.signed(−1).
    result = longitudinal(**changes)
    document = build_frameweb(result)
    states = 0
    for combination in result.combinations:
        for sign in combination.signs:
            native = native_vector(document, combination.number, sign)
            resolved, count = resolved_vector(result, combination, sign)
            assert {k for k, v in native.items() if v} == {k for k, v in resolved.items() if v}, combination.number
            for key, amount in resolved.items():
                assert abs(native.get(key, Decimal(0)) - amount) <= Decimal("0.005") * count[key], (combination, key)
            states += 1
    # 44 combinations with a horizontal case in both directions, 4 without (長期支持 and 変動作用 ①②③; decisions 102,
    # 120)
    assert states == 44 * 2 + 4


def test_reversal_is_only_for_the_horizontal_cases(full, result):
    for basic in result.basic_cases:
        assert ("C2" in full["define"][str(basic.number)]) is basic.horizontal
        if basic.horizontal:
            case = full["load"][str(basic.number)]
            assert all(row["ty"] is None and row["rz"] is None for row in case["load_node"])  # H only


def test_zero_coefficients_are_left_out_and_an_empty_combination_is_an_error():
    # ρs must be positive (decision 37), but a factor is printed with 2 decimals: ρs = 0.004 prints 0.00, and
    # 0.75 × 0.004 = 0.003 -> 0.00. The serviceability train and impact then add nothing. The edge-stress combinations
    # keep their other actions; 変動作用 (L2 + I2 only, decision 120) has nothing, and FrameWeb drops an empty Combine,
    # so Pickup 4 would fail.
    result = longitudinal(**{"上部構造/列車/荷重修正係数/使用性": 0.004})
    variable = [c for c in result.combinations if c.check is Check.CRACK_VARIABLE]  # ①, ② and ③
    assert [[k.factor.value for k in c.components] for c in variable] == [[0, 0]] * 3
    with pytest.raises(InputError, match=f"combine.{variable[0].number}"):
        build_frameweb(result)


def test_the_printed_numbers_must_be_in_order(result):
    shuffled = replace(result, combinations=(result.combinations[1], result.combinations[0], *result.combinations[2:]))
    with pytest.raises(ValueError, match="combinations"):
        build_frameweb(shuffled)


def test_every_use_of_an_action_must_be_the_same_action(result):
    # A Define stands for one load case: a combination using another action under the same case and basis
    # cannot share it.
    combination = result.combinations[0]
    d1 = combination.components[0]
    other = replace(d1, source=replace(d1.source, points=d1.source.points[:1]))
    changed = replace(combination, components=(other, *combination.components[1:]))
    with pytest.raises(ValueError, match="combination 1"):
        build_frameweb(replace(result, combinations=(changed, *result.combinations[1:])))
