"""Properties of the calculations that follow from their equations (decision 15, ADR-0003).

Only identities and orders the equations give are checked: a printed total is the sum of its printed parts, a
moment is the printed N times the printed arm, the loads written to the frame add up to the printed table, a
reaction from a printed lever is the lever sum over the span, and kv = c·ρ·Ed·Bv^e grows in proportion to Ed.
"""

from dataclasses import fields as dataclass_fields, is_dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from hypothesis import given, strategies as st

from reaction_support import pier
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import BasicCase as LongitudinalCase, calculate_longitudinal
from webpier.calc.moving_load import AxleTrain, Girder, car_offsets, search_reactions
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import BasicCase as TransverseCase, calculate_transverse
from webpier.core.printed import Printed

SUPPORT = "地盤データ/層/1/"
ORIGIN, END = "上部工反力/起点側/B支点/", "上部工反力/終点側/C支点/"


def D(printed):
    return Decimal(repr(printed.value))


def rounded(value, digits):
    return float(value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def at_digits(digits, low, high):
    scale = 10 ** digits
    return st.integers(min_value=round(low * scale), max_value=round(high * scale)).map(
        lambda units: float(Decimal(units).scaleb(-digits)))


# 0500 ---------------------------------------------------------------------------------------------------------

@given(st.integers(min_value=1, max_value=10**6), st.integers(min_value=2, max_value=9),
       st.sampled_from(["砂質土", "砂礫", "粘性土", "砂質土と粘性土の互層"]))
def test_ground_springs_grow_in_proportion_to_ed(modulus, factor, soil):
    small = calculate_foundation(pier(**{SUPPORT + "変形係数_Ed": modulus, SUPPORT + "土質区分": soil}))
    large = calculate_foundation(pier(**{SUPPORT + "変形係数_Ed": modulus * factor, SUPPORT + "土質区分": soil}))
    for term in ("long_term", "short_term"):
        one, many = getattr(small, term), getattr(large, term)
        # kv is printed to 1 kN/m3, so k·kv and kv(k·Ed) differ by at most the two roundings.
        assert abs(D(many.kv) - factor * D(one.kv)) <= Decimal(factor + 1) / 2
        assert many.kv.value >= one.kv.value and many.Kv.value >= one.Kv.value and many.Ks.value >= one.Ks.value
    for springs in (small.long_term, small.short_term, large.long_term, large.short_term):
        # Every spring is computed from the printed kv (hand check of 04 p.4-1).
        assert springs.Kv.value == rounded(D(springs.kv) * D(small.area), 0)
        assert springs.ks.value == rounded(D(springs.kv) / 3, 0)
        assert springs.Ks.value == rounded(D(springs.ks) * D(small.area), 0)
        assert springs.Kr_longitudinal.value == rounded(D(springs.kv) * D(small.inertia_longitudinal), 0)
        assert springs.Kr_transverse.value == rounded(D(springs.kv) * D(small.inertia_transverse), 0)
    assert small.short_term.kv.value >= small.long_term.kv.value  # ρ = 1.0 against 0.5


# Moving load ---------------------------------------------------------------------------------------------------

@st.composite
def bridges(draw):
    spans = []
    for _ in range(2):
        spans.append({"l1": draw(at_digits(3, 0, 1.5)), "span": draw(at_digits(3, 3, 40)),
                      "l2": draw(at_digits(3, 0, 1.5))})
    a1 = draw(at_digits(3, 1, 4))
    a2 = draw(st.one_of(st.just(0.0), at_digits(3, 1, 3)))
    car = draw(at_digits(3, a1 + 2 * a2 + 1, 26))
    tail = draw(st.one_of(st.none(), at_digits(2, 1, 60)))  # a line load behind the axles (E-17, decision 101)
    return (spans, a1, a2, car, draw(at_digits(2, 10, 250)), draw(st.integers(min_value=1, max_value=4)), tail,
            draw(at_digits(3, 0, 5)))


@given(bridges())
def test_the_adopted_loading_is_in_equilibrium_on_both_girders(bridge):
    spans, a1, a2, car, load, cars, tail, gap = bridge
    base = pier()
    origin, end = (replace(span, **{key: Printed(value, 3, "m") for key, value in sizes.items()})
                   for span, sizes in zip((base.spans.origin, base.spans.end), spans))
    offsets = car_offsets(cars, Decimal(repr(car)), Decimal(repr(a1)), Decimal(repr(a2)))
    train = AxleTrain("cars", (Printed(load, 2, "kN"),) * len(offsets), offsets,
                      None if tail is None else Printed(tail, 2, "kN/m"), Decimal(repr(gap)))
    result = search_reactions(origin, end, (train,))
    on = {girder: [axle for axle in result.axles if axle.girder is girder] for girder in Girder}
    assert (result.origin_axles.value, result.end_axles.value) == (len(on[Girder.ORIGIN]), len(on[Girder.END]))
    parts = {girder: result.tail(girder) for girder in Girder}
    weight = {girder: Decimal(0) if part is None else D(part.load) * D(part.length) for girder, part in parts.items()}
    moment = {girder: Decimal(0) if part is None else D(part.load) * D(part.length) * D(part.lever)
              for girder, part in parts.items()}
    # RA + RB and RC + RD carry every axle and the line load on their girder (vertical equilibrium: RA is the printed
    # total less the printed RB; exact without a line load, whose q × a has more digits than a force).
    for far, near, girder in ((result.ra, result.rb, Girder.ORIGIN), (result.rd, result.rc, Girder.END)):
        total = Decimal(repr(load)) * len(on[girder]) + weight[girder]
        assert far.value == rounded(total - D(near), 2)
        if parts[girder] is None:
            assert D(far) + D(near) == total
    # RB and RC are the moments about the far bearings over the span, from the printed levers and lengths.
    for girder, reaction, span in ((Girder.ORIGIN, result.rb, origin), (Girder.END, result.rc, end)):
        levers = sum((D(axle.lever) for axle in on[girder]), Decimal(0))
        assert reaction.value == rounded((Decimal(repr(load)) * levers + moment[girder]) / D(span.span), 2)
    # Every adopted axle stands on its girder: the lever lies between the far overhang and the pier overhang.
    for axle in on[Girder.ORIGIN]:
        assert -D(origin.l1) <= D(axle.lever) <= D(origin.span) + D(origin.l2)
    for axle in on[Girder.END]:
        assert -D(end.l2) <= D(axle.lever) <= D(end.span) + D(end.l1)
    assert result.rb.value + result.rc.value > 0


# 0610 / 0620 ------------------------------------------------------------------------------------------------

@st.composite
def bearing_loads(draw):
    """Dead, additional and snow loads of the bearings, the seat offset f and the pedestal height h1."""
    changes = {}
    for slots, count in ((ORIGIN, 4), (END, 2)):
        for index in range(count):
            for key in ("固定死荷重_D1", "付加死荷重_D2", "雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率"):
                changes[f"{slots}{index}/{key}"] = draw(at_digits(2, -500, 3000))
    for side in ("起点側", "終点側"):
        changes[f"上部構造/{side}/支承位置_f"] = draw(at_digits(3, 0.1, 1.2))
        changes[f"上部構造/{side}/高さ/h1"] = draw(st.one_of(st.just(0.0), at_digits(3, 0.05, 0.5)))
    return changes


def tables(value):
    """Every printed table of a result: an object with rows and the totals N and M (or H and M)."""
    if is_dataclass(value) and not isinstance(value, Printed):
        names = {item.name for item in dataclass_fields(value)}
        if "rows" in names:
            yield value
        for name in names:
            yield from tables(getattr(value, name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from tables(item)


def check_tables(result):
    found = 0
    for table in tables(result):
        for total in ("n", "h", "m"):
            if hasattr(table, total) and all(hasattr(row, total) for row in table.rows):
                parts = sum((D(getattr(row, total)) for row in table.rows), Decimal(0))
                assert getattr(table, total).value == rounded(parts, getattr(table, total).digits), (table, total)
                found += 1
        for row in table.rows:
            if all(hasattr(row, name) for name in ("n", "arm", "m")):
                assert row.m.value == rounded(D(row.n) * D(row.arm), row.m.digits), row
    return found


def check_d1(result, case):
    """The D1 loads written to the frame are the printed D1 table less the column line over the overlap."""
    points = result.basic(case).points
    top = sum((D(point.n) for point in points[:-1]), Decimal(0))
    assert float(top) == result.fixed.n.value
    assert points[-1].n == result.fixed.footing.n


@given(bearing_loads())
def test_0610_totals_are_the_sums_of_the_printed_parts(changes):
    p = pier(**changes)
    reaction = calculate_reaction(p)
    result = calculate_longitudinal(p, calculate_foundation(p), reaction)
    assert check_tables(result) >= 10
    check_d1(result, LongitudinalCase.D1)
    assert D(result.additional.table.n) == (D(reaction.dead.origin.pier.d2) + D(reaction.dead.end.pier.d2))


@given(bearing_loads())
def test_0620_totals_are_the_sums_of_the_printed_parts(changes):
    p = pier(**changes)
    result = calculate_transverse(p, calculate_foundation(p), calculate_reaction(p))
    assert check_tables(result) >= 10
    check_d1(result, TransverseCase.D1)
