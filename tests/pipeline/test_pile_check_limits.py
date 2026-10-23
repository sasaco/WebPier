"""The design limits of the 基礎の照査 of a pile foundation as SOIL-JR's .sdr prints them (decision 89): read by their names, in
the "地震時以外" condition of the direction, with the rotation in 1/1000 rad."""

from dataclasses import replace
from pathlib import Path

import pytest

from webpier.calc.foundation_check import LONGITUDINAL, TRANSVERSE, Requirement
from webpier.export.soiljr import SdrError, SdrTable, parse_sdr
from webpier.pipeline.pile_check import limits

SOIL = Path(__file__).parents[1] / "fixtures" / "soiljr"


def sdr(name="pile_cast.sdr"):
    return parse_sdr((SOIL / name).read_bytes())


def test_the_limits_are_the_three_requirements_of_the_non_seismic_condition():
    found = limits(sdr(), LONGITUDINAL)
    long_term = found[Requirement.LONG_TERM]
    assert (long_term.rk.value, long_term.pt.value, long_term.fr.value, long_term.rvd.value) == (4363.7, 0.54, 0.388, 1694.7)
    assert (long_term.rud.value, long_term.delta.value, long_term.indicator, long_term.theta.value) == (
        216.4, 11.314, "0.4%L≦40mm", 0.002)
    assert found[Requirement.SHORT_TERM].rud.value == 1671.3
    safety = found[Requirement.SAFETY]  # 安定(地震時以外): the third row of every table
    assert (safety.rvd.value, safety.rud.value, safety.delta.value, safety.theta.value) == (3260.3, 2164.6, 33.941, 0.006)
    assert safety.theta.digits == 5 and long_term.rvd.unit == "kN"


def test_the_two_directions_have_their_own_tables():
    found = sdr("pile_steel.sdr")
    assert limits(found, TRANSVERSE) == limits(found, LONGITUDINAL)  # SOIL-JR gives the same values to both


def replaced(found, title, change):
    tables = tuple(change(table) if table.title == title and table.direction == "橋軸方向" and table.condition == "地震時以外"
                   else table for table in found.tables)
    return replace(found, tables=tables)


def test_a_row_that_is_not_there_is_named():
    broken = replaced(sdr(), "水平変位の照査", lambda table: replace(table, rows=table.rows[1:]))
    with pytest.raises(SdrError, match="【水平変位の照査】に「長期支持性能」の行がありません"):
        limits(broken, LONGITUDINAL)


def test_a_column_that_is_not_there_is_named():
    broken = replaced(sdr(), "回転角の照査", lambda table: replace(table, columns=("性能項目", "設計限界値")))
    with pytest.raises(SdrError, match="【回転角の照査】に設計限界値θLの列がありません"):
        limits(broken, LONGITUDINAL)


def test_a_cell_that_is_not_a_number_is_named():
    def text(table: SdrTable) -> SdrTable:
        return replace(table, rows=tuple((*row[:4], "－", *row[5:]) if row[0] == "短期支持性能" else row for row in table.rows))

    with pytest.raises(SdrError, match="【設計引き抜き抵抗力の算定】の「短期支持性能」の設計引き抜き抵抗力が数値ではありません"):
        limits(replaced(sdr(), "設計引き抜き抵抗力の算定", text), LONGITUDINAL)


def test_an_indicator_that_is_a_number_is_named():
    def number(table: SdrTable) -> SdrTable:
        return replace(table, rows=tuple((row[0], row[1], 5.0, row[3]) if row[0] == "長期支持性能" else row for row in table.rows))

    with pytest.raises(SdrError, match="設計限界値の指標が文字ではありません"):
        limits(replaced(sdr(), "水平変位の照査", number), LONGITUDINAL)
