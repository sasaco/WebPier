"""0400 照査の前提 (decision 73, ADR-0012): the detailing checks of the column, the beam and the footing.

The expected values are the independent transcriptions tests/fixtures/example2/detailing.json of Example2 06 (compared
with current.json, the Example2 pier) and of the sample 0400 (compared with an input made like the sample's column and
footing; its notes list the differences), and hand calculations written here with Decimal, not with the code.
"""

import json
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from webpier.calc.detailing import calculate_detailing
from webpier.calc.detailing.common import bar_area
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "detailing.json").read_text(encoding="utf-8"))
EX2, S0400 = SAMPLE["example2_06"], SAMPLE["sample_0400"]


def rounded(value, places):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def data():
    return deepcopy(CURRENT)


def calculate(document=None):
    return calculate_detailing(parse_input(document if document is not None else data()))


def bounds(spacing):
    return {item.name: item.value.value for item in spacing.bounds}


def sample_document():
    """current.json with the column and the footing of the sample 0400 (see the fixture's notes)."""
    document = data()
    size = document["下部構造"]["寸法"]
    size["正面"]["W6"], size["側面"]["B6"], size["高さ"]["H6"] = 3.94, 1.7, 1.8
    column = document["鉄筋"]["柱"]
    column["concrete_strength_mpa"] = 24
    column["main_bars"] = {
        "線路": {"diameter_mm": 38, "per_face_count": 16, "cover_mode": "指定", "center_mm": 141.6, "endpoints": "含む",
               "distribution": {"mode": "等分", "edge_center_mm": 106, "pitch_mm": None}, "inner_layers": []},
        "直角": {"diameter_mm": 38, "per_face_count": 13, "cover_mode": "指定", "center_mm": 106, "endpoints": "含む",
               "distribution": {"mode": "等分", "edge_center_mm": 141.6, "pitch_mm": None}, "inner_layers": []}}
    footing = document["鉄筋"]["フーチング"]
    footing["concrete_strength_mpa"] = 24
    faces = footing["faces"]
    faces["上"]["線路"].update(diameter_mm=32, pitch_mm=150, center_mm=87)
    faces["上"]["直角"].update(diameter_mm=16, pitch_mm=200, center_mm=111)
    faces["下"]["線路"].update(diameter_mm=29, pitch_mm=150, center_mm=100)
    faces["下"]["直角"].update(diameter_mm=16, pitch_mm=200, center_mm=122.5)
    footing["stirrups"]["線路"].update(diameter_mm=22, pitch_mm=150, distribution_mode="間隔", width_pitch_mm=431,
                                     density_per_m=None)
    return document


# --- Example2 06 (current.json) -------------------------------------------------------------------------------------


def test_the_column_of_example2():
    result = calculate().column
    expected = EX2["6.3_axial_ratio"]["column"]
    amount = result.amount
    assert [(group.diameter.value, group.count.value, group.unit_area.value, group.area.value)
            for group in amount.groups] == [(32, 58, 794.2, 46063.6), (19, 18, 286.5, 5157.0)]
    assert (amount.area.value, amount.width.value, amount.depth.value) == (expected["total"], expected["b"], expected["h"])
    # 51220.6 / (4500 × 2700) × 100 = 0.42157… → 0.422 (Example2 0.42 %)
    assert (amount.section.value, amount.ratio.value, rounded(amount.ratio.value, 2)) == (12150000, 0.422, 0.42)
    assert amount.minimum_ok and amount.maximum_ok and amount.grade == "SD390" and result.main_count == 1
    for direction, key, ratio in zip(result.directions, ("column_longitudinal", "column_transverse"), (0.573, 0.573)):
        spacing, confinement = EX2["6.12_stirrup_spacing"][key], EX2["6.13_confinement"][key]
        shear = EX2["6.9_shear_ratio"][key]
        assert direction.effective_depth.value == spacing["d"]
        assert (direction.shear.area.value, direction.shear.width.value, direction.shear.pitch.value) == (
            shear["area"], shear["b"], shear["s"])
        assert direction.shear.ratio.value == ratio and rounded(ratio, 2) == shear["ps_percent"]
        assert bounds(direction.general)["half_d"] == spacing["half_d"]
        assert bounds(direction.general)["compression_15"] == spacing["compression_15"]
        found = bounds(direction.confinement)
        for name in ("main_8", "main_12", "stirrup_24"):
            assert found[name] == confinement[name]
        assert bounds(direction.general)["stirrup_48"] == confinement["stirrup_48"]
        assert found["quarter_d"] == rounded(confinement["quarter_d"], 0)  # 1099.5 → 1100 (printed to 1 mm)
    assert result.directions[0].main_diameter.value == 32 and result.directions[1].main_diameter.value == 19


def test_the_beam_of_example2():
    beam = calculate().beam
    expected = EX2["6.3_axial_ratio"]["beam"]
    upper, lower = beam.amount.groups
    assert (upper.diameter.value, upper.count.value, upper.area.value) == tuple(expected["upper"].values())
    assert (lower.diameter.value, lower.count.value, lower.area.value) == tuple(expected["lower"].values())
    assert beam.amount.area.value == expected["total"] and beam.amount.ratio.value == 0.343  # 25012 / 7290000
    assert rounded(beam.amount.ratio.value, 2) == expected["pc_percent"]
    assert beam.amount.maximum is None and beam.amount.maximum_ok is None
    skin = EX2["6.3_4_beam"]
    horizontal = beam.horizontal
    assert (horizontal.diameter.value, horizontal.pitch.value, horizontal.count.value, horizontal.unit_area.value,
            horizontal.width.value, horizontal.length.value, horizontal.ratio.value, horizontal.minimum.value) == (
        22, 125, 17, 387.1, 2700, 2700, 0.090, 0.080)
    assert horizontal.ok and horizontal.spacing_limit.value == 300
    # the vertical bars per spacing: 387.1 / (2700 × 125) × 100 = 0.1147 → 0.115
    assert (beam.vertical.ratio.value, beam.vertical.area.value, beam.vertical.ok) == (0.115, 387.1, True)
    corbel = beam.corbel
    assert (corbel.tension.value, corbel.required.value, corbel.provided.value) == tuple(skin["corbel"].values())
    assert corbel.ok
    compression = beam.compression
    assert (compression.provided.value, compression.required.value) == tuple(skin["compression"].values())
    assert compression.ok
    # d: the upper bars 17 at 108 and 8 at 108 + 32 + 32 = 172: 2700 − (17 × 108 + 8 × 172) / 25 = 2571.52 → 2571.5
    assert beam.effective_depth.value == 2571.5
    # ps: 4 × 387.1 / (2700 × 125) × 100 = 0.4588 → 0.459
    assert (beam.shear.area.value, beam.shear.ratio.value, beam.shear.ok) == (1548.4, 0.459, True)
    assert bounds(beam.general)["compression_15"] == 285  # 19 × 15
    assert bounds(beam.confinement)["main_8"] == 152 and bounds(beam.confinement)["half_short_side"] == 1350


def test_the_footing_of_example2():
    footing = calculate().footing
    assert footing.depth.value == 2700 and footing.aggregate_max.value == 25
    for direction, key, d, ratio in zip(footing.directions, ("footing_longitudinal", "footing_transverse"),
                                        (2600, 2573), (0.300, 0.340)):
        expected = EX2["6.3_axial_ratio"][key]
        upper, lower = direction.amount.groups
        assert (upper.diameter.value, upper.count.value, upper.area.value) == tuple(expected["upper"].values())
        assert (lower.diameter.value, lower.count.value, lower.area.value) == tuple(expected["lower"].values())
        assert direction.amount.area.value == expected["total"]
        assert direction.amount.ratio.value == ratio and rounded(ratio, 2) == expected["pc_percent"]
        assert direction.effective_depth.value == d
        shear = EX2["6.9_shear_ratio"]["footing"]
        # 2.00 × 198.6 / (1000 × 250) × 100 = 0.1589 → 0.159 (Example2 0.16)
        assert (direction.shear.area.value, direction.shear.ratio.value) == (shear["area"], 0.159)
        assert direction.ok
    spacing = EX2["6.12_stirrup_spacing"]
    assert bounds(footing.directions[0].general)["half_d"] == spacing["footing_longitudinal_lower"]["half_d"]
    assert bounds(footing.directions[0].general)["compression_15"] == 375
    assert bounds(footing.directions[1].general)["half_d"] == rounded(spacing["footing_transverse_lower"]["half_d"], 0)


# --- the sample 0400 ------------------------------------------------------------------------------------------------


def test_the_column_of_the_sample():
    result = calculate(sample_document()).column
    expected = S0400["column"]
    amount = result.amount
    assert (amount.width.value, amount.depth.value, amount.section.value) == (
        expected["b"], expected["h"], expected["area"])
    main, side = amount.groups[:result.main_count], amount.groups[result.main_count:]
    assert [(group.diameter.value, group.count.value, group.area.value) for group in main] == [
        tuple(expected["main"].values())]
    assert [(group.diameter.value, group.count.value, group.area.value) for group in side] == [
        tuple(expected["side"].values())]
    assert (amount.area.value, amount.ratio.value, amount.maximum.value) == (
        expected["as"], expected["pc_percent"], expected["pc_max_percent"])
    assert result.fck.value == expected["fck"]
    longitudinal, transverse = result.directions
    rows = expected["longitudinal"]
    assert longitudinal.effective_depth.value == rows["d"]
    found = bounds(longitudinal.confinement)
    assert (found["quarter_d"], found["main_8"], found["stirrup_24"], found["fixed_300"]) == (
        rows["quarter_d"], rows["main_8"], rows["stirrup_24"], 300)
    assert longitudinal.confinement.limit.value == 300 and longitudinal.confinement.pitch.value == rows["pitch"]
    assert longitudinal.lateral.limit.value == rows["stirrup_48"]
    ties = longitudinal.lateral.ties
    assert (ties.sets.value - ties.intermediate_sets.value, ties.intermediate_sets.value) == (
        rows["outer_sets"], rows["intermediate_sets"])
    for direction, rows in ((longitudinal, expected["longitudinal"]), (transverse, expected["transverse"])):
        assert direction.shear.area.value == rows["aw_total"]
        assert direction.shear.ratio.value == rows["pw_percent"] == direction.ductility.pw.value
        assert direction.ductility.value.value == rows["ductility"] and direction.ductility.ok
        assert direction.capacity.pw.value == rows["pw_fraction"]
        assert direction.capacity.value.value == rows["capacity"] and direction.capacity.above
    assert (longitudinal.ductility.kwo.value, longitudinal.ductility.limit.value, longitudinal.capacity.fwyd.value) == (
        1.15, 0.04, 390)
    assert transverse.effective_depth.value == expected["transverse"]["d"]
    assert bounds(transverse.confinement)["quarter_d"] == expected["transverse"]["quarter_d"]
    assert transverse.shear.width.value == expected["transverse"]["b"]
    assert transverse.lateral.ties.intermediate_sets.value == expected["transverse"]["intermediate_sets"]
    limits = expected["clear_limits"]
    spacing = longitudinal.spacing
    assert (spacing.minimum.value, spacing.bar_limit.value, spacing.aggregate_limit.value) == tuple(limits.values())


def test_the_footing_of_the_sample():
    footing = calculate(sample_document()).footing
    expected = S0400["footing_longitudinal"]
    longitudinal, transverse = footing.directions
    upper, lower = longitudinal.amount.groups
    assert (upper.diameter.value, upper.count.value, upper.area.value) == tuple(expected["upper"].values())
    assert (lower.diameter.value, lower.count.value, lower.area.value) == tuple(expected["lower"].values())
    amount = longitudinal.amount
    assert (amount.area.value, amount.width.value, amount.depth.value, amount.section.value, amount.ratio.value) == (
        expected["as"], expected["b"], expected["h"], expected["area"], expected["pc_percent"])
    ductility = expected["ductility"]
    assert (longitudinal.shear.area.value, longitudinal.shear.pitch.value, longitudinal.shear.ratio.value) == (
        ductility["aw_total"], ductility["s"], ductility["pw_percent"])
    assert longitudinal.ductility.value.value == ductility["value"]
    # 0.00599 × 390 / (24.0 / 1.3) = 0.12654 → 0.127 from the printed pw (the sample 0.126, ADR-0003)
    assert longitudinal.capacity.value.value == 0.127 != expected["capacity_sample"]
    for face, (name, rows) in zip(longitudinal.faces, expected["faces"].items()):
        assert (face.bars.area.value, face.required.value, face.distribution.value, face.compression.value) == tuple(
            rows.values())
        assert face.distribution_ok and face.compression_ok
    for face, rows in zip(transverse.faces, expected["transverse_faces"].values()):
        assert (face.bars.diameter.value, face.bars.count.value, face.bars.area.value, face.required.value,
                face.distribution.value, face.compression.value) == tuple(rows.values())


# --- hand calculations -----------------------------------------------------------------------------------------------


def test_the_clear_spacing_of_the_current_input():
    result = calculate()
    longitudinal, transverse = result.column.directions
    # 線路: the least gap of 108, 300, 450, … is 150: 150 − 32 = 118; 40, 1.5 × 32 = 48, 25 × 4/3 = 33.3
    spacing = longitudinal.spacing
    assert (spacing.pitch.value, spacing.layer, spacing.pitch_clear.value, spacing.clear.value) == (150, None, 118, 118)
    assert (spacing.minimum.value, spacing.bar_factor.value, spacing.bar_limit.value, spacing.aggregate_limit.value) == (
        40, 1.5, 48, 33.3)
    assert spacing.ok
    # 直角: D19 at 250: 231; 1.5 × 19 = 28.5
    assert (transverse.spacing.pitch.value, transverse.spacing.clear.value, transverse.spacing.bar_limit.value) == (
        250, 231, 28.5)
    upper, lower = result.beam.spacings
    # the beam's upper face: (2700 − 2 × 184) / 16 = 145.75 at x = 1350 + (j − 8) × 145.75, printed to 0.1 mm the
    # gaps are 145.7 and 145.8; the layers 108 and 172: 64 − 32 = 32 < 33.3 (a beam: 20 mm, φ, 4/3 Dmax)
    assert (upper.pitch.value, upper.layer.value, upper.clear.value, upper.minimum.value, upper.bar_limit.value) == (
        145.7, 64, 32, 20, 32)
    assert not upper.ok
    # the lower face: (2700 − 368) / 17 = 137.18; the printed positions give 137.1 and 137.2
    assert (lower.pitch.value, lower.clear.value, lower.ok) == (137.1, 118.1, True)
    assert not result.beam.ok and result.engineering_status == "not_ok"
    for direction in result.footing.directions:
        for face in direction.spacings:
            assert (face.pitch.value, face.layer, face.minimum.value, face.bar_factor.value) == (125, None, 20, 1.0)
    # 125 − 29 = 96 ≧ 33.3
    assert result.footing.directions[1].spacings[1].clear.value == 96


def test_the_current_input_without_the_beam_layer_is_ok():
    document = data()
    document["鉄筋"]["梁"]["faces"]["上"]["inner_layers"][0]["clear_gap_mm"] = 40
    result = calculate(document)
    assert result.beam.spacings[0].clear.value == 40 and result.beam.ok
    assert result.engineering_status == "ok" and result.column.ok and result.footing.ok
    assert result.cantilever_appearance is False


def test_the_stirrup_spacing_and_the_ties_can_fail():
    document = data()
    rows = document["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    rows[0].update(pitch_mm=400, effective_legs=2)
    column = calculate(document).column.directions[0]
    assert (column.general.limit.value, column.general.ok) == (300, False)
    assert (column.confinement.limit.value, column.confinement.ok) == (256, False)
    # two legs: the outer hoop at the 直角 bars, 4398 − 102 = 4296 > 22 × 48 = 1056
    assert (column.lateral.ties.max_spacing.value, column.lateral.ok) == (4296, False)
    # Ps = 2 × 387.1 / (4500 × 400) × 100 = 0.0430 < 0.15
    assert (column.shear.ratio.value, column.shear.ok) == (0.043, False)
    assert not column.ok


def test_the_ductility_limit_and_the_capacity_ratio_by_the_steel():
    document = data()
    document["鉄筋"]["柱"]["materials"]["transverse"] = "SD295"
    rows = document["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    rows[0].update(diameter_mm=32, pitch_mm=100)
    column = calculate(document).column.directions[0]
    # pw = 10 × 794.2 / (4500 × 100) × 100 = 1.7649 → 1.765; 0.021 × 0.85 × 1.765 + 0.013 = 0.04450 → 0.045 > 0.04
    assert (column.shear.ratio.value, column.ductility.kwo.value, column.ductility.value.value) == (1.765, 0.85, 0.045)
    assert not column.ductility.ok
    # 0.01765 × 295 / (27.0 / 1.3) = 0.25070 → 0.251
    assert (column.capacity.fwyd.value, column.capacity.value.value, column.capacity.above) == (295, 0.251, True)
    document["鉄筋"]["柱"]["materials"]["transverse"] = "SD345"
    assert calculate(document).column.directions[0].ductility.kwo == Printed(1.0, 2, "")


@pytest.mark.parametrize("member", ["柱", "フーチング"])
def test_sd490_hoops_stop_at_the_unchecked_kwo(member):
    """SD490 has no kwo checked in a source (decision 100): the hoops of that grade are an input error."""
    document = data()
    document["鉄筋"][member]["materials"]["transverse"] = "SD490"
    with pytest.raises(InputError, match=f"鉄筋.{member}.materials.transverse: SD490 の kwo"):
        calculate(document)


def test_sd490_main_bars_of_the_column_are_checked():
    document = data()
    document["鉄筋"]["柱"]["materials"]["main"] = "SD490"
    assert calculate(document).column.amount.grade == "SD490"


def test_a_footing_layer_inside_and_the_capacity_below_its_limit():
    document = data()
    document["鉄筋"]["フーチング"]["faces"]["下"]["線路"]["inner_layers"] = [{"pitch_mm": 250, "clear_gap_mm": 50}]
    direction = calculate(document).footing.directions[0]
    # the 線路 layers of the lower face at 100 and 100 + 25 + 50 = 175: 75 − 25 = 50
    lower = direction.spacings[1]
    assert (lower.pitch.value, lower.layer.value, lower.layer_clear.value, lower.clear.value) == (125, 75, 50, 50)
    # 8 + 4 = 12 bars a metre: 12 × 506.7 = 6080.4; d = 2700 − (8 × 100 + 4 × 175) / 12 = 2575
    assert (direction.amount.groups[1].count.value, direction.amount.groups[1].area.value) == (12, 6080.4)
    assert direction.effective_depth.value == 2575
    # 0.00159 × 390 / (27.0 / 1.3) = 0.02986 → 0.030 ≦ 0.1
    assert (direction.capacity.value.value, direction.capacity.above) == (0.03, False)


def test_a_beam_without_side_bars_and_one_with_one():
    document = data()
    document["鉄筋"]["梁"]["side_bars"] = None
    beam = calculate(document).beam
    assert (beam.horizontal.diameter, beam.horizontal.area.value, beam.horizontal.ratio.value) == (None, 0, 0)
    assert not beam.horizontal.ok and beam.horizontal.spacing_ok and not beam.horizontal.ratio_ok
    assert (beam.corbel.provided.value, beam.corbel.ok) == (0, False)
    document = data()
    document["鉄筋"]["梁"]["side_bars"]["per_face_count"] = 1
    beam = calculate(document).beam
    assert beam.horizontal.pitch is None and beam.horizontal.spacing_ok and not beam.horizontal.ratio_ok
    assert beam.corbel.pitch is None


def test_one_bar_a_line_has_no_clear_spacing():
    document = data()
    bars = document["鉄筋"]["柱"]["main_bars"]["直角"]
    bars["per_face_count"] = 1
    document["鉄筋"]["柱"]["column_hoops"]["direction_rows"][1]["effective_legs"] = 2
    spacing = calculate(document).column.directions[1].spacing
    assert (spacing.pitch, spacing.layer, spacing.clear, spacing.ok) == (None, None, None, True)


def test_the_nominal_areas():
    assert bar_area(Printed(38, 0, "mm"), "x") == Printed(1140, 0, "mm2")
    assert bar_area(Printed(10, 0, "mm"), "x") == Printed(71.33, 2, "mm2")
    with pytest.raises(InputError, match=r"^x: D20 の公称断面積がありません（JIS G 3112 の D6・D10・"):
        bar_area(Printed(20, 0, "mm"), "x")


def edited(path, value):
    document = data()
    node = document
    *parents, key = path.split("/")
    for part in parents:
        node = node[part]
    node[key] = value
    return document


@pytest.mark.parametrize(("path", "value", "message"), [
    ("鉄筋/フーチング/faces/上/線路/diameter_mm", None, "鉄筋.フーチング.faces.上.線路.diameter_mm: 値が必要です"),
    ("鉄筋/フーチング/faces/上/直角/pitch_mm", None, "鉄筋.フーチング.faces.上.直角.pitch_mm: 値が必要です"),
    ("鉄筋/フーチング/stirrups/線路/pitch_mm", None, "鉄筋.フーチング.stirrups.線路.pitch_mm: 値が必要です"),
    ("鉄筋/フーチング/materials/main", None, "鉄筋.フーチング.materials.main: 値が必要です"),
    ("鉄筋/フーチング/materials/transverse", None, "鉄筋.フーチング.materials.transverse: 値が必要です"),
    ("鉄筋/フーチング/aggregate_max_mm", None, "鉄筋.フーチング.aggregate_max_mm: 値が必要です"),
    ("鉄筋/梁/aggregate_max_mm", None, "鉄筋.梁.aggregate_max_mm: 値が必要です"),
    ("鉄筋/梁/materials/main", None, "鉄筋.梁.materials.main: 値が必要です"),
    ("鉄筋/梁/stirrups/effective_legs", None, "鉄筋.梁.stirrups.effective_legs: 値が必要です"),
    ("鉄筋/梁/stirrups/diameter_mm", 20, "鉄筋.梁.stirrups.diameter_mm: D20 の公称断面積がありません"),
    ("鉄筋/柱/aggregate_max_mm", None, "鉄筋.柱.aggregate_max_mm: 値が必要です"),
    ("鉄筋/柱/materials/main", None, "鉄筋.柱.materials.main: 値が必要です"),
    ("鉄筋/柱/main_bars/直角/per_face_count", 0, "鉄筋.柱.main_bars.直角: 直角の主鉄筋が必要です"),
    ("片持ち梁の照査/外観の照査", None, "片持ち梁の照査.外観の照査: 値が必要です"),
])
def test_a_blank_the_checks_need_is_an_input_error(path, value, message):
    with pytest.raises(InputError) as caught:
        calculate(edited(path, value))
    assert str(caught.value).startswith(message)


def test_the_appearance_check_of_the_cantilever_is_read():
    assert calculate(edited("片持ち梁の照査/外観の照査", "行う")).cantilever_appearance is True
