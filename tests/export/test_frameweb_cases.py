"""FrameWeb Define, Combine and Pickup: Example2 08 pp.8-9 to 8-11 and its FrameWeb file.

FrameWeb analyses each load case once per spring set and combines the responses linearly: a Define row lists
the load cases it may take (a negative number is the same case reversed, FrameWeb takes the worse), a Combine
row multiplies Defines by coefficients, a Pickup row lists the Combines it envelopes.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from frameweb_support import D, EXAMPLE2, L08, PEDESTAL, longitudinal
from webpier.calc.longitudinal import Basis
from webpier.core.errors import InputError
from webpier.export.frameweb import build_frameweb


@pytest.fixture(scope="module")
def result():
    return longitudinal()


@pytest.fixture(scope="module")
def current(result):
    return build_frameweb(result)


def test_defines_are_those_of_example2_and_the_serviceability_impacts(current):
    # 8-9: Define 1-20 take basic case n; 13-20 also −n (the horizontal cases in both directions).
    assert {n: current["define"][n] for n in map(str, range(1, 21))} == EXAMPLE2["define"]
    printed = L08["define_cases"]["rows"]
    assert [[current["define"][str(row["no"])][f"C{i}"] for i in range(1, len(row["C"]) + 1)] for row in printed] == [
        row["C"] for row in printed]
    assert current["define"]["21"] == {"row": 21, "C1": 21}
    assert current["define"]["22"] == {"row": 22, "C1": 22}
    assert list(current["define"]) == [str(n) for n in range(1, 23)]


def coefficients(row):
    return {key: value for key, value in row.items() if key.startswith("C")}


def test_combines_are_those_of_example2_with_the_serviceability_impacts(current):
    # 8-10 prints 0.75 on I1 / I2 in combinations 5, 7, 15, 16: 0.75 ρs × the basic I. The calc takes the
    # serviceability impact (0.75 i in the girder coefficient) times ρs = 1.00, so these combinations reference
    # Define 21 / 22 with ρs instead. Every other coefficient is the printed one.
    replaced = {"5": ("C12", "C22"), "7": ("C11", "C21"), "15": ("C11", "C21"), "16": ("C11", "C21")}
    assert list(current["combine"]) == [str(n) for n in range(1, 17)]
    for number, example in EXAMPLE2["combine"].items():
        expected = coefficients(example)
        if number in replaced:
            basic, auxiliary = replaced[number]
            assert expected.pop(basic) == 0.75
            expected[auxiliary] = 1
        assert coefficients(current["combine"][number]) == dict(sorted(expected.items(), key=lambda i: int(i[0][1:])))
        assert current["combine"][number]["row"] == int(number)


def test_combines_carry_the_printed_factors(current, result):
    for combination in result.combinations:
        row = current["combine"][str(combination.number)]
        expected = {}
        for component in combination.components:
            define = component.case.value if component.basis is Basis.BASIC else {11: 21, 12: 22}[component.case.value]
            expected[f"C{define}"] = component.factor.value
        assert coefficients(row) == expected
        assert all(component.factor.digits in (1, 2) for component in combination.components)


def test_combine_names(current):
    rows = {row["no"]: row for row in L08["combinations"]["combination_table"]["rows"]}
    assert [current["combine"][str(n)]["name"] for n in range(1, 17)] == [
        "破壊 列車最大", "破壊 制動最大", "破壊 ﾛﾝｸﾞ最大", "破壊 雪最大", "ひび割れ 縁応力度", "ひび割れ 永久荷重",
        "ひび割れ 変動荷重", "損傷 列車最大", "損傷 雪最大", "地盤の安定 列車最大", "地盤の安定 制動最大",
        "地盤の安定 ﾛﾝｸﾞ最大", "地盤の安定 雪最大", "長期支持", "短期支持 低水位", "短期支持 高水位"]
    for n in range(1, 14):  # 8-10 performance item and remark
        assert current["combine"][str(n)]["name"] == f"{rows[n]['performance_item']} {rows[n]['remark']}"


def test_pickups_are_those_of_8_11(current):
    printed = L08["extraction_cases"]["rows"]
    assert {n: coefficients(row) for n, row in current["pickup"].items()} == {
        n: coefficients(row) for n, row in EXAMPLE2["pickup"].items()}
    renamed = {"復旧性（損傷）": "使用性（損傷）"}  # the R5 name of the sample's H16 extraction case (decision 73)
    assert [(row["row"], row["name"]) for row in current["pickup"].values()] == [
        (row["no"], renamed.get(row["name"], row["name"])) for row in printed]


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
    assert states == 12 * 2 + 4  # 12 combinations with a horizontal case in both directions, 4 without


def test_reversal_is_only_for_the_horizontal_cases(current):
    for number, define in current["define"].items():
        assert coefficients(define) == ({"C1": int(number), "C2": -int(number)} if 13 <= int(number) <= 20
                                        else {"C1": int(number)})
    for number in range(13, 21):
        case = current["load"][str(number)]
        assert all(row["ty"] is None and row["rz"] is None for row in case["load_node"])  # H only


def test_zero_coefficients_are_left_out_and_an_empty_combination_is_an_error():
    # ρs must be positive (decision 37), but a factor is printed with 2 decimals: ρs = 0.004 prints 0.00, and
    # 0.75 × 0.004 = 0.003 -> 0.00. The serviceability train and impact then add nothing. Combinations 5, 15 and 16
    # keep their other actions; combination 7 (L1 + I1 only) has nothing, and FrameWeb drops an empty Combine, so
    # Pickup 4 would fail.
    result = longitudinal(**{"上部構造/列車/荷重修正係数/使用性": 0.004})
    assert [c.factor.value for c in result.combinations[6].components] == [0, 0]
    with pytest.raises(InputError, match="combine.7"):
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
