"""0600 hand-check from the printed PDF alone (decision 15).

Every formula chain recomputes from its printed numbers, and the tables do their
arithmetic from their printed cells: V·x = V × x, the sums, L = R × ρf, I = L × i,
M = H × y and H_B + H_C. Nothing here imports the report's internals except to
count the formulas the manuscript declares as numeric.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from pdf_handcheck import PrintedLine, decimal_of, formula_checks, printed_lines, rounded_like
from reaction_report_cases import CASES, case
from webpier.calc.reaction.self_weight import Part
from webpier.core.printed import Printed

PARTS = {"桁受け", "はり", "ハンチ部", "柱", "フーチング", "上載土", "台形部", "柱控除", "ハンチの層", "ハンチ控除",
         "斜面部", "矩形部"}


def render(tmp_path: Path, result, pier, name: str = "0600.pdf") -> Path:
    from webpier.reporting.stages.reaction import render_reaction

    return render_reaction(result, pier, tmp_path / name)


def declared(result, pier) -> int:
    from webpier.reporting.stages.reaction import content

    return sum(unit.checked for unit in content(result, pier))


@pytest.mark.parametrize("name", list(CASES))
def test_every_printed_formula_reproduces_its_result(tmp_path: Path, name: str):
    result, pier = case(name)
    checks = formula_checks(render(tmp_path, result, pier))
    assert len(checks) == declared(result, pier) > 250
    assert [check for check in checks if not check.ok] == []


def _suffix(line: PrintedLine) -> tuple[str, list[str]]:
    """The label (leading cells, joined) and the trailing cells that are numbers or dashes."""
    count = 0
    for cell in reversed(line.cells):
        if cell != "-" and decimal_of(cell) is None:
            break
        count += 1
    return "".join(line.cells[:len(line.cells) - count]), list(line.cells[len(line.cells) - count:])


def _product(a: str, b: str, printed: str) -> bool:
    return rounded_like(decimal_of(a) * decimal_of(b), printed) == decimal_of(printed)


class _Tables:
    """Reads the printed lines in order and recomputes each table row from its printed cells."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checked = 0
        self.parts: list[list[str]] = []  # rows of the volume or weight table being read
        self.rho: Decimal | None = None
        self.reaction: list[str] | None = None
        self.single: list[str] | None = None
        self.tracks: list[str] | None = None
        self.load: list[str] | None = None
        self.coefficient: list[str] | None = None

    def check(self, ok: bool, message: str) -> None:
        self.checked += 1
        if not ok:
            self.failures.append(message)

    def read(self, line: PrintedLine) -> None:
        label, values = _suffix(line)
        where = f"p{line.page} {label}"
        if "荷重修正係数" in label and values:
            self.rho = decimal_of(values[-1])
        if len(values) in (5, 7) and (label in PARTS or label == "合計"):
            self._part(label, values, where)
        elif len(values) == 4:
            self._impact(label.removeprefix("単線").removeprefix("複線"), values, where)
        elif len(values) == 3 and ("LR" in label or "EQ" in label):
            total = decimal_of(values[0]) + decimal_of(values[1])
            self.check(rounded_like(total, values[2]) == decimal_of(values[2]), f"{where} H_B + H_C: {values}")
        elif len(values) == 6 and not label.startswith("G"):
            for force, height, moment in (values[:3], values[3:]):
                self.check(_product(force, height, moment), f"{where} M = H × y: {force} × {height}")

    def _part(self, label: str, values: list[str], where: str) -> None:
        if label != "合計":
            for column in range(2, len(values), 2):
                if values[column] != "-":
                    self.check(_product(values[0], values[column - 1], values[column]),
                               f"{where}: {values[0]} × {values[column - 1]}")
            self.parts.append(values)
            return
        for column in range(0, len(values), 2):
            if values[column] != "-":
                total = sum((decimal_of(row[column]) for row in self.parts if row[column] != "-"), Decimal(0))
                self.check(rounded_like(total, values[column]) == decimal_of(values[column]),
                           f"{where} column {column}: {values[column]}")
        self.parts = []

    def _impact(self, label: str, values: list[str], where: str) -> None:
        if label == "列車反力R":
            self.reaction, self.single, self.tracks = values, None, None
        elif label == "列車荷重L" and self.reaction is not None and self.single is None:
            assert self.rho is not None
            for r, load in zip(self.reaction, values):
                self.check(_product(r, str(self.rho), load), f"{where} L = R × ρf: {r} × {self.rho}")
            self.single = self.load = values
        elif label == "軌道数n":
            self.tracks = values
        elif label == "列車荷重L" and self.single is not None and self.tracks is not None:
            for single, n, load in zip(self.single, self.tracks, values):
                self.check(_product(single, n, load), f"{where} L = L × n: {single} × {n}")
            self.load = values
        elif label == "衝撃係数i":
            self.coefficient = values
        elif label == "衝撃荷重I" and self.load is not None and self.coefficient is not None:
            for load, i, impact in zip(self.load, self.coefficient, values):
                self.check(_product(load, i, impact), f"{where} I = L × i: {load} × {i}")


def table_failures(lines: list[PrintedLine]) -> list[str]:
    tables = _Tables()
    for line in lines:
        tables.read(line)
    assert tables.checked > 0
    return tables.failures


def table_checks(lines: list[PrintedLine]) -> int:
    tables = _Tables()
    for line in lines:
        tables.read(line)
    return tables.checked


@pytest.mark.parametrize("name", list(CASES))
def test_every_table_row_recomputes_from_its_printed_cells(tmp_path: Path, name: str):
    lines = printed_lines(render(tmp_path, *case(name)))
    assert table_failures(lines) == []


def test_the_table_reader_checks_every_table_cell_with_arithmetic(tmp_path: Path):
    result, pier = case("current")
    lines = printed_lines(render(tmp_path, result, pier))
    sw = result.self_weight
    # The current input has no 桁受け (V = 0): neither its volume table nor its weight rows are printed (decision 41).
    assert sw.pedestal.volume.value == 0
    bodies = (sw.beam, sw.column, sw.footing, sw.overburden, sw.buoyancy_high.body,
              sw.buoyancy_normal.body, sw.buoyancy_low.body)
    # V·x (2 or 3 per row) and the sums (3 or 4) of each volume table, N·x and sums of the two weight tables.
    volumes = sum(len(body.rows) * (3 if body.moment_y is not None else 2) + (4 if body.moment_y is not None else 3)
                  for body in bodies)
    weights = sum(sum(2 + (row.moment_y is not None) for row in total.rows if row.part is not Part.PEDESTAL) + 4
                  for total in (sw.pier_bottom, sw.footing_centre))
    impacts = 3 * 4 * 4  # L = R × ρf, I, L = L × n, I for each of the three groups
    assert table_checks(lines) == volumes + weights + impacts + 10 + 2 * 8


def _wrong(result, field: str):
    """A result whose printed value no longer follows from the printed factors."""
    sw, train, lon, trans = result.self_weight, result.train, result.longitudinal, result.transverse
    if field == "beam_weight":
        return replace(result, self_weight=replace(sw, beam=replace(sw.beam, weight=Printed(1503.28, 2, "kN"))))
    if field == "haunch_z":
        return replace(result, self_weight=replace(sw, beam_haunch_centroid=Printed(0.390, 3, "m")))
    if field == "double_impact":
        impact = replace(train.ultimate.origin_impact, double=Printed(0.223, 3, ""))
        return replace(result, train=replace(train, ultimate=replace(train.ultimate, origin_impact=impact)))
    if field == "floor":
        case_ = lon.cases[2]
        origin = replace(case_.origin, friction_floor=Printed(29.85, 2, "kN"))
        cases = (*lon.cases[:2], replace(case_, origin=origin), *lon.cases[3:])
        return replace(result, longitudinal=replace(lon, cases=cases))
    if field == "hG":
        total = replace(sw.footing_centre, y=Printed(2.981, 3, "m"))  # ΣN·y / ΣN with the soil (decision 24)
        return replace(result, self_weight=replace(sw, footing_centre=total))
    assert field == "moment"
    wind = replace(trans.origin.wind_with_train, moment=Printed(1323.26, 2, "kN m"))
    side = replace(trans.origin, wind_with_train=wind)
    return replace(result, transverse=replace(trans, origin=side))


@pytest.mark.parametrize("field,expected", [
    ("beam_weight", {"61.358*24.5"}),
    # z is a factor of the haunch y as well (its x stays 0 × z / H3 = 0).
    ("haunch_z", {"0.700*(2.700*4.500/2+(2.700*4.500+4.500*0.000)/3+0.000*4.500/4)/(2.700*4.500+(2.700*4.500"
                  "+4.500*0.000)/2+0.000*4.500/3)", "-(2.000+0.700-0.390)"}),
    # The double-track impact is a factor of the movable bearing's Rm in the safety and restorability cases;
    # 0.223 × 0.75 still prints 0.167.
    ("double_impact", {"0.245*(1-18.850/200)",
                       "1.1*5740.00+1.2*520.00+1.35*272.47*2.000*(1+0.223)+740.00",
                       "1.1*5740.00+1.2*520.00+1.23*272.47*2.000*(1+0.223)+740.00",
                       "1.0*5740.00+1.0*520.00+1.23*272.47*2.000*(1+0.223)+740.00"}),
    # The friction floor μ·T/n is printed as a candidate of H; it does not govern here.
    ("floor", {"0.10*298.40"}),
    ("hG", {"26707.918/7129.33"}),
])
def test_a_value_that_does_not_follow_from_the_printed_factors_is_found(tmp_path: Path, field: str, expected: set[str]):
    result, pier = case("current")
    checks = formula_checks(render(tmp_path, _wrong(result, field), pier))
    assert {check.expression for check in checks if not check.ok} == expected


def test_a_table_cell_that_does_not_follow_is_found(tmp_path: Path):
    result, pier = case("current")
    lines = printed_lines(render(tmp_path, _wrong(result, "moment"), pier))
    failures = table_failures(lines)
    assert len(failures) == 1 and failures[0].endswith("M = H × y: 197.00 × 6.717")
