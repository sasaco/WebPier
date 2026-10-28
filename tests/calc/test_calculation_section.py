"""The 計算上断面 of the column (CONTEXT.md, decision 118): the column is an RC section with it, its shape stays the
実断面 B6 × W6. Hand values from tests/fixtures/inputs/current.json (B6 = 2.700, W6 = 4.500 m)."""

from dataclasses import replace

from reaction_support import pier
from webpier.calc.column_rebar import column_layout
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import Direction, build_frame
from webpier.calc.materials import calculate_materials
from webpier.calc.reaction import calculate_reaction
from webpier.core.printed import LENGTH
from webpier.inputs.model import CalculationSection

SECTION = CalculationSection(LENGTH(2.6), LENGTH(4.4))


def sectioned():
    return replace(pier(), calculation_section=SECTION)


def frame(p, direction):
    return build_frame(p, calculate_reaction(p).self_weight, calculate_foundation(p), calculate_materials(p),
                       direction)


def test_without_one_the_rc_section_is_the_real_one():
    p = pier()
    assert p.calculation_section is None
    assert p.column_section == (p.substructure.b[6], p.substructure.w[6]) == (LENGTH(2.7), LENGTH(4.5))


def test_the_bars_are_laid_in_the_calculation_section():
    layout = column_layout(sectioned())
    assert (layout.width.value, layout.height.value) == (4400.0, 2600.0)  # X = across (W), Y = along (B), mm


def test_the_frame_s_column_is_the_calculation_section():
    p = sectioned()
    longitudinal = frame(p, Direction.LONGITUDINAL).column_section
    assert (longitudinal.width.value, longitudinal.depth.value) == (4.4, 2.6)  # B in the plane along the track
    assert longitudinal.area.value == 11.44  # 4.4 × 2.6
    transverse = frame(p, Direction.TRANSVERSE).column_section
    assert (transverse.width.value, transverse.depth.value) == (2.6, 4.4)


def test_the_shape_stays_the_real_section():
    real, calculated = pier(), sectioned()
    assert calculate_reaction(calculated) == calculate_reaction(real)  # weights and positions: B6 × W6
    for direction in Direction:
        frames = frame(real, direction), frame(calculated, direction)
        assert frames[0].nodes == frames[1].nodes and frames[0].column_section != frames[1].column_section
