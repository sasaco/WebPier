"""0620 FrameWeb Define, Combine and Pickup: Example2 09 pp.9-13 to 9-15 and its FrameWeb file.

A Define lists the load cases it may take: Define 9 and 11 take the up or the down track, 13 to 15 either sign
(−n reverses the case). FrameWeb takes the worse alternative of each Define on its own, then sums the Defines of
a Combine with their factors.
"""

from dataclasses import replace
from decimal import Decimal
from itertools import product

import pytest

from frameweb_support import CURVE, D, EXAMPLE2_09, T09, T_PEDESTAL, WIDTHS, ground, transverse
from webpier.calc.transverse import Basis, Define
from webpier.core.errors import InputError
from webpier.export.frameweb import build_frameweb_transverse

SERVICE = {Define.IMPACT_SINGLE: 16, Define.IMPACT_DOUBLE: 17}  # the Defines of the serviceability impacts
SERVICE_ON_A_CURVE = {Define.IMPACT_SINGLE: 18, Define.IMPACT_DOUBLE: 19}


@pytest.fixture(scope="module")
def result():
    return transverse()


@pytest.fixture(scope="module")
def current(result):
    return build_frameweb_transverse(result)


def coefficients(row):
    return {key: value for key, value in row.items() if key.startswith("C")}


def test_defines_are_those_of_example2_and_the_serviceability_impacts(current):
    # 9-13: Define 9 = {9, 10} (single track up or down), 11 = {12, 13}, 13 to 15 in both signs.
    assert {n: current["define"][n] for n in map(str, range(1, 16))} == EXAMPLE2_09["define"]
    printed = T09["define_cases"]["rows"]
    assert [list(coefficients(current["define"][str(row["no"])]).values()) for row in printed] == [
        row["C"] for row in printed]
    # The serviceability impacts (0.75 i in the 0600 girder coefficients) are load cases 18-20 after the 17
    # basic cases, with Defines of their own: up or down, and double.
    assert current["define"]["16"] == {"row": 16, "C1": 18, "C2": 19}
    assert current["define"]["17"] == {"row": 17, "C1": 20}
    assert list(current["define"]) == [str(n) for n in range(1, 18)]
    assert [current["load"][n]["symbol"] for n in ("18", "19", "20")] == ["I1s", "I2s", "I3s"]
    assert [current["load"][n]["name"] for n in ("18", "19", "20")] == [
        "衝撃荷重　使用性　単線　上り", "衝撃荷重　使用性　単線　下り", "衝撃荷重　使用性　複線"]


def test_combines_are_those_of_example2_with_the_serviceability_impacts(current):
    # 9-14 prints 0.75 on I1 / I2 in combinations 5, 7, 15, 16: 0.75 ρs × the basic I. The calc takes the
    # serviceability impact times ρs = 1.00, so these combinations reference Define 16 / 17 instead.
    replaced = {"5": ("C12", "C17"), "7": ("C11", "C16"), "15": ("C11", "C16"), "16": ("C11", "C16")}
    assert list(current["combine"]) == [str(n) for n in range(1, 17)]
    for number, example in EXAMPLE2_09["combine"].items():
        expected = coefficients(example)
        if number in replaced:
            basic, auxiliary = replaced[number]
            assert expected.pop(basic) == 0.75
            expected[auxiliary] = 1
        assert coefficients(current["combine"][number]) == dict(sorted(expected.items(), key=lambda i: int(i[0][1:])))
        assert current["combine"][number]["row"] == int(number)


def define_column(component, service):
    return service[component.define] if component.alternatives[0].basis is Basis.SERVICE_IMPACT else \
        component.define.value


@pytest.mark.parametrize("changes,service", [({}, SERVICE), (CURVE, SERVICE_ON_A_CURVE)], ids=["straight", "curve"])
def test_combines_carry_the_printed_factors(changes, service):
    result = transverse(**changes)
    document = build_frameweb_transverse(result)
    for combination in result.combinations:
        expected = {f"C{define_column(c, service)}": c.alternatives[0].factor.value for c in combination.components}
        assert coefficients(document["combine"][str(combination.number)]) == dict(
            sorted(expected.items(), key=lambda item: int(item[0][1:])))
        assert all(a.factor.digits in (1, 2) for c in combination.components for a in c.alternatives)


def test_combine_names(current):
    rows = {row["no"]: row for row in T09["combinations"]["combination_table"]["rows"]}
    for n in range(1, 14):  # 9-14 performance item and remark
        assert current["combine"][str(n)]["name"] == f"{rows[n]['performance_item']} {rows[n]['remark']}"
    assert [current["combine"][str(n)]["name"] for n in (14, 15, 16)] == ["長期支持", "短期支持 低水位",
                                                                          "短期支持 高水位"]


def test_pickups_are_those_of_9_15(current):
    printed = T09["extraction_cases"]["rows"]
    assert {n: coefficients(row) for n, row in current["pickup"].items()} == {
        n: coefficients(row) for n, row in EXAMPLE2_09["pickup"].items()}
    assert [(row["row"], row["name"], list(coefficients(row).values())) for row in current["pickup"].values()] == [
        (row["no"], row["name"], row["combinations"]) for row in printed]


def test_centrifugal_loads_on_a_curve():
    # Decision 33: R ≠ 0 adds basic cases 18-20 (up, down, double; H and M at the seat) and Define 16 (up or
    # down) and 17, with the factor of L in exactly the combinations that hold L. The serviceability impacts
    # follow as load cases 21-23 and Defines 18-19.
    result = transverse(**CURVE)
    document = build_frameweb_transverse(result)
    assert list(document["load"]) == [str(n) for n in range(1, 24)]
    assert [document["load"][n]["symbol"] for n in map(str, range(18, 24))] == [
        "CF1", "CF2", "CF3", "I1s", "I2s", "I3s"]
    assert [document["load"][n]["name"] for n in ("18", "19", "20")] == [
        "遠心荷重　単線　上り", "遠心荷重　単線　下り", "遠心荷重　複線"]
    for number in ("18", "19", "20"):
        action = result.basic_cases[int(number) - 1]
        (point,) = action.points
        assert document["load"][number]["fix_node"] == 2
        assert [(row["n"], row["tx"], row["ty"], row["rz"]) for row in document["load"][number]["load_node"]] == [
            (str(point.node), point.h.value, None, point.m.value)]
    assert (document["define"]["16"], document["define"]["17"]) == ({"row": 16, "C1": 18, "C2": 19},
                                                                     {"row": 17, "C1": 20})
    assert (document["define"]["18"], document["define"]["19"]) == ({"row": 18, "C1": 21, "C2": 22},
                                                                     {"row": 19, "C1": 23})
    for row in document["combine"].values():
        c = coefficients(row)
        assert c.get("C16") == c.get("C9") and c.get("C17") == c.get("C10")
    assert [n for n, row in document["combine"].items() if "C16" in row or "C17" in row] == [
        "1", "2", "5", "7", "8", "10", "11", "15", "16"]  # the combinations that hold L


def test_straight_track_has_no_centrifugal_cases(current):
    assert not any(case["symbol"].startswith("CF") for case in current["load"].values())


def add(vector, key, amount):
    vector[key] = vector.get(key, Decimal(0)) + amount


def native_vector(document, combine, choice):
    """Σ factor × load of one Combine, each Define taking the alternative of *choice* (by Define column)."""
    vector = {}
    for key, factor in coefficients(document["combine"][str(combine)]).items():
        alternatives = list(coefficients(document["define"][key[1:]]).values())
        reference = alternatives[choice.get(key, 0)]
        case = document["load"][str(abs(reference))]
        scale = D(factor) * (1 if reference > 0 else -1)
        for row in case.get("load_node", []):
            for axis in ("tx", "ty", "rz"):
                if row[axis] is not None:
                    add(vector, (case["fix_node"], "node", row["n"], axis), scale * D(row[axis]))
        for row in case.get("load_member", []):
            where = (case["fix_node"], "member", row["m1"], row["direction"], D(row["L1"]), D(row["L2"]))
            add(vector, (*where, "P1"), scale * D(row["P1"]))
            add(vector, (*where, "P2"), scale * D(row["P2"]))
    return vector


def resolved_vector(result, variant):
    springs = {"long_term": 1, "short_term": 2}
    lengths = {m.number: D(m.height.value) for m in result.frame.members}
    vector, count = {}, {}

    def put(key, amount):
        add(vector, key, amount)
        count[key] = count.get(key, 0) + 1

    for action in variant:
        spring = springs[action.source.spring.value]
        for p in action.points:
            for axis, amount in (("tx", D(p.h.value)), ("ty", D(p.n.value)), ("rz", D(p.m.value))):
                put((spring, "node", str(p.node), axis), amount)
        for line in action.line_loads:
            for member in line.members:
                for end in ("P1", "P2"):
                    put((spring, "member", str(member), "gy", D(0), D(0), end), D(line.n.value))
        for load in action.member_loads:
            where = (spring, "member", str(load.member), "gx", D(load.start.value),
                     lengths[load.member] - D(load.end.value))
            put((*where, "P1"), D(load.h_start.value))
            put((*where, "P2"), D(load.h_end.value))
    return vector, count


def choices(combination, service):
    """Every choice of FrameWeb: one alternative per Define, each on its own; with the calc's variant if any."""
    columns = [f"C{define_column(c, service)}" for c in combination.components]
    calc = set(combination.variants())
    for picked in product(*(range(len(c.alternatives)) for c in combination.components)):
        variant = tuple(c.alternatives[i] for c, i in zip(combination.components, picked, strict=True))
        yield dict(zip(columns, picked, strict=True)), variant, variant in calc


@pytest.mark.parametrize("changes,service", [
    ({}, SERVICE), (T_PEDESTAL, SERVICE), (WIDTHS | ground(5.2), SERVICE), (CURVE, SERVICE_ON_A_CURVE)],
    ids=["current", "pedestal", "haunch_cut", "curve"])
def test_every_variant_of_the_calc_is_a_choice_of_frameweb(changes, service):
    # Each variant of the calc (one track for all single-track actions, each horizontal action in either sign) is
    # one choice of an alternative per Define. The calc rounds each resolved action once (factor × printed
    # action -> 2 decimals); FrameWeb multiplies the printed action by the printed factor exactly, so they differ
    # by at most 0.005 per resolved action (decision 38), and the load points, members and spring sets agree.
    result = transverse(**changes)
    document = build_frameweb_transverse(result)
    variants = mixed = 0
    for combination in result.combinations:
        for choice, variant, of_the_calc in choices(combination, service):
            native = native_vector(document, combination.number, choice)
            resolved, count = resolved_vector(result, variant)
            assert {k for k, v in native.items() if v} == {k for k, v in resolved.items() if v}, combination.number
            for key, amount in resolved.items():
                assert abs(native.get(key, Decimal(0)) - amount) <= Decimal("0.005") * count[key], (combination, key)
            variants += of_the_calc
            mixed += not of_the_calc
    # 5 combinations with LF and W1 (4 each), 3 with one wind (2), 3 with a single track (7, 15, 16: up or down)
    # and 5 with one state: 37.
    assert variants == sum(len(c.variants()) for c in result.combinations) == 5 * 4 + 3 * 2 + 3 * 2 + 5
    # FrameWeb takes the worse alternative of each Define on its own, so in 7, 15 and 16 it also tries an up train
    # with a down impact: 2 × 2 choices for the calc's 2, and 2 × 2 × 2 with the centrifugal load on a curve.
    assert mixed == 3 * (6 if changes is CURVE else 2)


def test_zero_coefficients_are_left_out_and_an_empty_combination_is_an_error():
    # ρs = 0.004 prints 0.00: the serviceability train and impact add nothing, so combination 7 (L1 + I1 only) is
    # empty and FrameWeb would drop it, breaking Pickup 4.
    result = transverse(**{"上部構造/列車/荷重修正係数/使用性": 0.004})
    assert [a.factor.value for c in result.combinations[6].components for a in c.alternatives] == [0, 0, 0, 0]
    with pytest.raises(InputError, match="combine.7"):
        build_frameweb_transverse(result)


def test_the_printed_numbers_must_be_in_order(result):
    shuffled = replace(result, combinations=(result.combinations[1], result.combinations[0], *result.combinations[2:]))
    with pytest.raises(ValueError, match="combinations"):
        build_frameweb_transverse(shuffled)
    swapped = replace(result, define_cases=(result.define_cases[1], result.define_cases[0], *result.define_cases[2:]))
    with pytest.raises(ValueError, match="Define cases"):
        build_frameweb_transverse(swapped)
    with pytest.raises(ValueError, match="combination 1"):  # a component of a Define case that is not there
        build_frameweb_transverse(replace(result, define_cases=result.define_cases[1:]))


def changed_component(result, number, define, change):
    combination = result.combinations[number - 1]
    components = tuple(change(c) if c.define is define else c for c in combination.components)
    combinations = list(result.combinations)
    combinations[number - 1] = replace(combination, components=components)
    return replace(result, combinations=tuple(combinations))


@pytest.mark.parametrize("change", [
    lambda c: replace(c, alternatives=c.alternatives[::-1]),
    lambda c: replace(c, alternatives=c.alternatives[:1]),
    lambda c: replace(c, alternatives=(c.alternatives[0],
                                       replace(c.alternatives[1], factor=c.alternatives[0].nominal))),
    lambda c: replace(c, alternatives=(c.alternatives[0], replace(c.alternatives[1], basis=Basis.BASIC))),
], ids=["order", "missing", "factor", "basis"])
def test_the_alternatives_of_a_component_are_those_of_its_define(result, change):
    # Combination 7: I1 in the serviceability basis, up then down, with one factor for both.
    with pytest.raises(ValueError, match="combination 7"):
        build_frameweb_transverse(changed_component(result, 7, Define.IMPACT_SINGLE, change))


def test_the_signs_of_an_alternative_share_its_action(result):
    def change(c):
        other = replace(c.alternatives[1], source=replace(c.alternatives[1].source, points=()))
        return replace(c, alternatives=(c.alternatives[0], other))
    with pytest.raises(ValueError, match="combination 1"):
        build_frameweb_transverse(changed_component(result, 1, Define.LATERAL, change))


def test_every_use_of_an_action_must_be_the_same_action(result):
    # A basic Define stands for its basic cases; a serviceability Define for the same actions in every use.
    def basic(c):
        return replace(c, alternatives=tuple(replace(a, source=replace(a.source, points=a.source.points[:1]))
                                             for a in c.alternatives))
    with pytest.raises(ValueError, match="combination 1"):
        build_frameweb_transverse(changed_component(result, 1, Define.D1, basic))

    def service(c):
        return replace(c, alternatives=tuple(replace(a, source=replace(a.source, points=())) for a in c.alternatives))
    with pytest.raises(ValueError, match="combination 15"):
        build_frameweb_transverse(changed_component(result, 15, Define.IMPACT_SINGLE, service))
