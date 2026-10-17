"""0600 pier self weight, overburden and buoyancy: Example2 08 p.8-3 and independent hand calculations.

The hand calculation below rounds every printed value (volumes and lengths to 3
decimals, weights to 2) and continues from the rounded value, as a person would.
"""

from decimal import Decimal

import pytest

from reaction_support import D, SELF_WEIGHT_08, pier, q, value
from webpier.calc.reaction.self_weight import Part, calculate_self_weight
from webpier.core.errors import InputError

P3 = SELF_WEIGHT_08["8-3"]
ZERO = Decimal(0)


def q3(x):
    return q(x, 3)


def sqrt(x):
    return Decimal(x).sqrt()


def hand(p):
    """Every printed quantity of the self-weight pages, by hand."""
    s = p.substructure
    b = {i: D(s.b[i].value) for i in s.b}
    w = {i: D(s.w[i].value) for i in s.w}
    h = {i: D(s.h[i].value) for i in s.h}
    df1, df2 = D(s.df1.value), D(s.df2.value)
    body, footing, soil = D(s.unit_weight_body.value), D(s.unit_weight_footing.value), D(s.unit_weight_overburden.value)
    r = {}

    def body_total(name, rows, gamma, heights=True):
        volume = sum((row[0] for row in rows), ZERO)
        moments = [sum((q3(row[0] * row[k]) for row in rows), ZERO) for k in (1, 2)]
        r[name + ".volume"] = volume
        r[name + ".weight"] = q(volume * gamma, 2)
        r[name + ".x_l"] = q3(moments[0] / volume) if volume else ZERO
        r[name + ".x_c"] = q3(moments[1] / volume) if volume else ZERO
        if heights:
            moment_y = sum((q3(row[0] * row[3]) for row in rows), ZERO)
            r[name + ".y"] = q3(moment_y / volume) if volume else ZERO

    # Pedestal: one prism on the beam top; centroids are geometric.
    area = q3(b[3] * w[3])
    volume = q3(area * h[1])
    r["pedestal.volume"] = volume
    r["pedestal.weight"] = q(volume * body, 2)
    r["pedestal.x_l"] = q3((2 * b[2] + b[3] - b[1] - b[4] + b[5]) / 2)
    r["pedestal.x_c"] = q3((2 * w[2] + w[3] - w[1] - w[4] + w[5]) / 2)
    r["pedestal.y"] = q3(h[1] / 2)

    # Beam: prism + haunch frustum; z from the smaller (lower) face A2.
    a1, a2 = q3(b[1] * w[1]), q3((b[1] - b[4] - b[5]) * (w[1] - w[4] - w[5]))
    xl, xc = q3((b[5] - b[4]) / 2), q3((w[5] - w[4]) / 2)
    ratio = a1 / a2
    z = q3(h[3] / 4 * (1 + 2 * sqrt(ratio) + 3 * ratio) / (1 + sqrt(ratio) + ratio))
    haunch_volume = q3(h[3] / 6 * ((b[1] - b[4] - b[5]) * w[1] + b[1] * (w[1] - w[4] - w[5]) + 2 * (a1 + a2)))
    haunch = (haunch_volume, q3(xl * z / h[3]) if h[3] else ZERO, q3(xc * z / h[3]) if h[3] else ZERO,
              q3(-(h[2] + h[3] - z)))
    r["beam.z"] = z
    r["beam.haunch_y"] = haunch[3]
    r["beam.haunch_x_l"] = haunch[1]
    body_total("beam", [(q3(a1 * h[2]), xl, xc, q3(-h[2] / 2)), haunch], body)

    # Column.
    column_area = q3(b[6] * w[6])
    column = (q3(column_area * h[4]), q3((b[7] - b[9]) / 2), q3((w[7] - w[9]) / 2), q3(h[4] / 2 + h[5] + h[6]))
    r["column.volume"], r["column.weight"] = column[0], q(column[0] * body, 2)
    r["column.x_l"], r["column.x_c"], r["column.y"] = column[1:]

    # Footing: haunch frustum on the lower prism; z from the larger (lower) face.
    bf, wf = b[7] + b[8] + b[9], w[7] + w[8] + w[9]
    f1, f2 = q3(b[8] * w[8]), q3(bf * wf)
    ratio = f1 / f2
    zf = q3(h[5] / 4 * (1 + 2 * sqrt(ratio) + 3 * ratio) / (1 + sqrt(ratio) + ratio))
    footing_haunch = (q3(h[5] / 6 * (bf * w[8] + b[8] * wf + 2 * (f1 + f2))),
                      q3(column[1] * zf / h[5]) if h[5] else ZERO, q3(column[2] * zf / h[5]) if h[5] else ZERO,
                      q3(h[6] + zf))
    body_total("footing", [footing_haunch, (q3(f2 * h[6]), ZERO, ZERO, q3(h[6] / 2))], footing)

    # Overburden soil: trapezoid, less the column, plus the haunch layer, less the footing haunch.
    hc = q3((df1 - df2) / bf * (b[9] + b[8] / 2) + df2)
    r["soil.depth_at_column"] = hc
    trapezoid_x = q3(bf * (df1 + 2 * df2) / (3 * (df1 + df2)) - bf / 2) if df1 + df2 else ZERO
    body_total("soil", [(q3(f2 * (df1 + df2) / 2), trapezoid_x, ZERO), (q3(-column_area * hc), column[1], column[2]),
                        (q3(f2 * h[5]), ZERO, ZERO), (-footing_haunch[0], footing_haunch[1], footing_haunch[2])],
               soil, heights=False)

    # Buoyancy at the three water levels (heights above the footing base).
    base, low, step = h[5] + h[6], min(df1, df2), abs(df1 - df2)
    for name, level in (("high", s.hw1), ("normal", s.hw2), ("low", s.hw3)):
        hw = D(level.value)
        rise = q3(min(hw - base - low, step))
        wedge = q3(min(bf * rise / step, bf)) if step and rise > 0 else ZERO
        rectangle = q3(bf - wedge)
        wet = max(rise, ZERO)
        r[name + ".rise"], r[name + ".wedge"], r[name + ".rectangle"] = rise, wedge, rectangle
        wedge_x = (rectangle + wedge / 3 if df1 > df2 else 2 * wedge / 3) - bf / 2
        rectangle_x = (rectangle / 2 if df1 > df2 else wedge + rectangle / 2) - bf / 2
        body_total(name, [(q3(f2 * max(ZERO, min(low + base, hw))), ZERO, ZERO),
                          (q3(column_area * max(hw - hc - base, ZERO)), column[1], column[2]),
                          (q3(wedge * wf * wet / 2), q3(wedge_x), ZERO),
                          (q3(rectangle * wf * wet), q3(rectangle_x), ZERO)], Decimal("-10.0"), heights=False)

    # Pier bottom: pedestal (by weight), beam and column about the column axis.
    top = h[4] + h[3] + h[2]
    rows = [(r["pedestal.weight"], r["pedestal.x_l"], r["pedestal.x_c"], q3(top + r["pedestal.y"])),
            (r["beam.weight"], r["beam.x_l"], r["beam.x_c"], q3(top + r["beam.y"])),
            (r["column.weight"], ZERO, ZERO, q3(h[4] / 2))]
    aggregate(r, "pier_bottom", rows)
    top += h[5] + h[6]
    rows = [(r["pedestal.weight"], q3(r["pedestal.x_l"] + r["column.x_l"]), q3(r["pedestal.x_c"] + r["column.x_c"]),
             q3(top + r["pedestal.y"])),
            (r["beam.weight"], q3(r["beam.x_l"] + r["column.x_l"]), q3(r["beam.x_c"] + r["column.x_c"]),
             q3(top + r["beam.y"])),
            (r["column.weight"], r["column.x_l"], r["column.x_c"], r["column.y"]),
            (r["footing.weight"], r["footing.x_l"], r["footing.x_c"], r["footing.y"]),
            (r["soil.weight"], r["soil.x_l"], r["soil.x_c"], None)]
    aggregate(r, "footing_centre", rows)
    return r


def aggregate(r, name, rows):
    weight = sum((row[0] for row in rows), ZERO)
    r[name + ".weight"] = weight
    for k, key in ((1, "x_l"), (2, "x_c"), (3, "y")):
        moment = sum((q3(row[0] * row[k]) for row in rows if row[k] is not None), ZERO)
        r[name + "." + key] = q3(moment / weight)


def actual(result):
    r = {}
    for name in ("pedestal", "beam", "column", "footing", "overburden"):
        part = getattr(result, name)
        key = "soil" if name == "overburden" else name
        r[key + ".volume"], r[key + ".weight"] = value(part.volume), value(part.weight)
        r[key + ".x_l"], r[key + ".x_c"] = value(part.x_l), value(part.x_c)
        if part.y is not None:
            r[key + ".y"] = value(part.y)
    r["beam.z"] = value(result.beam_haunch_centroid)
    r["beam.haunch_y"] = value(result.beam.rows[1].y)
    r["beam.haunch_x_l"] = value(result.beam.rows[1].x_l)
    r["soil.depth_at_column"] = value(result.soil_depth_at_column)
    for name in ("high", "normal", "low"):
        water = getattr(result, "buoyancy_" + name)
        r[name + ".rise"], r[name + ".wedge"], r[name + ".rectangle"] = (
            value(water.rise), value(water.wedge), value(water.rectangle))
        r[name + ".volume"], r[name + ".weight"] = value(water.body.volume), value(water.body.weight)
        r[name + ".x_l"], r[name + ".x_c"] = value(water.body.x_l), value(water.body.x_c)
    for name in ("pier_bottom", "footing_centre"):
        total = getattr(result, name)
        r[name + ".weight"] = value(total.weight)
        r[name + ".x_l"], r[name + ".x_c"], r[name + ".y"] = value(total.x_l), value(total.x_c), value(total.y)
    return r


ASYMMETRIC = {
    "下部構造/寸法/側面": {"B1": 3.0, "B2": 0.3, "B3": 1.2, "B4": 0.4, "B5": 0.2, "B6": 2.0, "B7": 1.5, "B8": 2.4,
                       "B9": 2.1},
    "下部構造/寸法/正面": {"W1": 8.0, "W2": 0.5, "W3": 6.0, "W4": 1.5, "W5": 2.0, "W6": 4.0, "W7": 2.0, "W8": 4.6,
                       "W9": 2.4},
    "下部構造/寸法/高さ": {"H1": 0.25, "H2": 1.8, "H3": 0.6, "H4": 5.0, "H5": 0.4, "H6": 1.5},
    "下部構造/土かぶり": {"起点側_df1": 1.2, "終点側_df2": 0.6},
    "下部構造/水位": {"高水位_hw1": 2.8, "平水位_hw2": 3.5, "低水位_hw3": -0.5},
}
MIRRORED = {**ASYMMETRIC, "下部構造/土かぶり": {"起点側_df1": 0.6, "終点側_df2": 1.2}}


@pytest.mark.parametrize("changes", [{}, ASYMMETRIC, MIRRORED], ids=["example2", "asymmetric", "mirrored"])
def test_every_printed_quantity_by_hand(changes):
    p = pier(**changes)
    expected, result = hand(p), actual(calculate_self_weight(p))
    assert result == expected


def test_example2_08_page_8_3():
    result = calculate_self_weight(pier())
    assert result.footing.weight.value == P3["footing"]["value"]
    assert result.overburden.weight.value == P3["overburden"]["total"]["value"]
    for name in ("high", "normal", "low"):
        assert getattr(result, "buoyancy_" + name).body.weight.value == P3["buoyancy"][name]["value"]
    # 08 p.8-2 prints the column section 4.50 x 2.70 = 12.150 m2.
    assert result.column_area.value == 12.15


def test_example2_values_by_hand():
    result = calculate_self_weight(pier())
    # Beam haunch: r = 24.300/12.150 = 2, z = 0.175(1+2√2+6)/(1+√2+2) = 0.38964 -> 0.390 from the lower face.
    assert result.beam_haunch_centroid.value == 0.39
    assert result.beam.rows[1].y.value == -2.31  # -(2.000 + 0.700 - 0.390)
    assert result.beam.volume.value == 61.358  # 48.600 + 12.758
    assert result.beam.weight.value == 1503.27
    assert result.column.weight.value == 1458.61  # 12.150 x 4.900 = 59.535 m3 x 24.5
    assert result.pier_bottom.weight.value == 2961.88  # Ds of the pier impact reduction
    assert (result.pedestal.x_l.value, result.pedestal.x_c.value) == (-1.35, -4.5)


def test_haunch_centroid_is_measured_from_the_smaller_lower_face():
    # ADR-0001: the old code (src/reaction_weights.py:205) used z from the top face, i.e. y = -(z + h2) = -2.390.
    result = calculate_self_weight(pier())
    assert result.beam.rows[1].y.value != -2.39
    asymmetric = calculate_self_weight(pier(**ASYMMETRIC))
    # A1 = 24.000, A2 = 2.400 x 4.500 = 10.800; z = 0.15(1+2√r+3r)/(1+√r+r) = 0.33890 -> 0.339.
    assert asymmetric.beam_haunch_centroid.value == 0.339
    assert asymmetric.beam.rows[1].y.value == -2.061  # -(1.800 + 0.600 - 0.339); the old code gave -2.139
    assert asymmetric.beam.rows[1].x_l.value == -0.057  # (0.200-0.400)/2 = -0.100, x 0.339/0.600 = -0.0565


def test_decision_20_pedestal_weight_and_transverse_moment_and_soil_centroid():
    result = calculate_self_weight(pier(**ASYMMETRIC))
    pedestal = result.pier_bottom.rows[0]
    assert result.pier_bottom.rows[0].part is Part.PEDESTAL
    # Weight, not volume: 1.200 x 6.000 = 7.200 m2 x 0.250 = 1.800 m3 x 24.5 = 44.10 kN.
    assert pedestal.weight.value == 44.1
    # The transverse moment includes the pedestal: xC = (2x0.5 + 6.0 - 8.0 - 1.5 + 2.0)/2 = -0.250.
    assert pedestal.x_c.value == -0.25
    assert pedestal.moment_c.value == -11.025
    # The haunch layer of the soil is centred on the footing: xL = 0, not the column's xC (-0.200).
    assert result.overburden.rows[2].x_l.value == 0.0
    assert result.overburden.rows[2].volume.value == 21.6  # 6.000 x 9.000 x 0.400


def test_negative_water_level_gives_no_buoyancy():
    low = calculate_self_weight(pier(**ASYMMETRIC)).buoyancy_low
    assert low.body.rows[0].volume.value == 0.0  # old code kept a signed -27.000 m3
    assert low.body.weight.value == 0.0


def test_water_in_the_sloped_soil_zone():
    high = calculate_self_weight(pier(**ASYMMETRIC)).buoyancy_high
    # Water 0.300 m above the low soil surface; the soil is 0.600 m higher at the origin side.
    assert (high.rise.value, high.wedge.value, high.rectangle.value) == (0.3, 3.0, 3.0)
    assert [row.x_l.value for row in high.body.rows[2:]] == [1.0, -1.5]


def test_symmetric_pier_has_no_eccentricity():
    result = calculate_self_weight(pier())
    for total in (result.pier_bottom, result.footing_centre):
        assert (total.x_l.value, total.x_c.value) == (0.0, 0.0)


def test_footing_centre_rows_and_soil_without_height():
    result = calculate_self_weight(pier())
    parts = [row.part for row in result.footing_centre.rows]
    assert parts == [Part.PEDESTAL, Part.BEAM, Part.COLUMN, Part.FOOTING, Part.OVERBURDEN]
    soil = result.footing_centre.rows[-1]
    assert (soil.y, soil.moment_y) == (None, None)
    assert result.overburden.y is None


def test_zero_haunches_and_zero_cover():
    result = calculate_self_weight(pier(**{"下部構造/寸法/高さ/H3": 0.0,
                                           "下部構造/土かぶり": {"起点側_df1": 0.0, "終点側_df2": 0.0}}))
    haunch = result.beam.rows[1]
    assert (haunch.volume.value, haunch.x_l.value, haunch.y.value) == (0.0, 0.0, -2.0)
    assert result.overburden.rows[0].x_l.value == 0.0
    assert result.overburden.volume.value == 0.0  # 0 - 12.150 x 0 + 0 - 0


def test_printed_digits_and_units():
    result = calculate_self_weight(pier())
    row = result.beam.rows[0]
    assert (row.volume.digits, row.volume.unit, row.moment_y.unit) == (3, "m3", "m4")
    assert (result.beam.weight.digits, result.beam.weight.unit) == (2, "kN")
    total_row = result.pier_bottom.rows[1]
    assert (total_row.moment_y.digits, total_row.moment_y.unit) == (3, "kN m")
    assert result.buoyancy_high.body.unit_weight.value == -10.0


def test_zero_total_with_unbalanced_moment_is_an_input_error():
    # A column as large as the footing removes all the soil volume but not its moment (xL = -0.150).
    with pytest.raises(InputError, match="上載土"):
        calculate_self_weight(pier(**{"下部構造/寸法/側面/B6": 7.0, "下部構造/寸法/正面/W6": 9.0,
                                      "下部構造/寸法/側面/B7": 2.0, "下部構造/寸法/側面/B9": 2.3}))


def test_a_section_that_rounds_to_zero_area_is_an_input_error():
    with pytest.raises(InputError, match="柱"):
        calculate_self_weight(pier(**{"下部構造/寸法/側面/B6": 0.001, "下部構造/寸法/正面/W6": 0.4}))
    with pytest.raises(InputError, match="はり下面"):
        calculate_self_weight(pier(**{"下部構造/寸法/側面/B4": 1.349, "下部構造/寸法/側面/B5": 1.35,
                                      "下部構造/寸法/正面/W4": 4.4, "下部構造/寸法/正面/W5": 4.5}))
