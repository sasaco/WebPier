"""0600 hand-check from the printed PDF alone (decision 15).

Every formula chain recomputes from its printed numbers, and the tables do their
arithmetic from their printed cells: V from its numbers and W = V × γ (table 6.2.1),
L = R × ρf, I = L × i, M = H × y and H_B + H_C. Nothing here imports the report's internals except to
count the formulas the manuscript declares as numeric.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from pdf_handcheck import PrintedLine, _evaluate, decimal_of, formula_checks, printed_lines, rounded_like
from reaction_report_cases import CASES, case
from webpier.core.printed import Printed

PARTS = {"桁受け", "はり", "柱", "フーチング", "上載土"}
OPERATORS = {"+", "−", "×", "/"}
NUMBERS = re.compile(r"[−(]*\d")  # the first number of V (the header's words and units are not)
HEADING = re.compile(r"\(\d+\)")  # the next item, after the table and its sums


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
    assert len(checks) == declared(result, pier) > 150
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
        self.weights: list[tuple[list[str], list[str]]] | None = None  # rows of table 6.2.1: V's numbers, V γ W
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
        if line.cells[:2] == ("表", "6.2.1"):
            self.weights = []
            return
        if self.weights is not None:
            if line.cells[0] != "W" and not HEADING.fullmatch(line.cells[0]):
                self._weight_row(line)
                return
            self._weights(f"p{line.page} 表6.2.1")
        label, values = _suffix(line)
        where = f"p{line.page} {label}"
        if "荷重修正係数" in label and values:
            self.rho = decimal_of(values[-1])
        if len(values) == 4:
            self._impact(label.removeprefix("単線").removeprefix("複線"), values, where)
        elif len(values) == 3 and ("LR" in label or "EQ" in label):
            total = decimal_of(values[0]) + decimal_of(values[1])
            self.check(rounded_like(total, values[2]) == decimal_of(values[2]), f"{where} H_B + H_C: {values}")
        elif len(values) == 6 and not label.startswith("G"):
            for force, height, moment in (values[:3], values[3:]):
                self.check(_product(force, height, moment), f"{where} M = H × y: {force} × {height}")

    def _weight_row(self, line: PrintedLine) -> None:
        """A line of table 6.2.1: its numbers of V continue the row when they begin with an operator (a wrapped V),
        and its "= V γ W" belongs to the row being read, on whichever of its lines it stands."""
        assert self.weights is not None
        cells = [cell for cell in line.cells if cell not in PARTS and cell != "V"]
        numbers, values = (cells[:cells.index("=")], cells[cells.index("=") + 1:]) if "=" in cells else (cells, [])
        first = bool(numbers) and NUMBERS.match(numbers[0]) is not None
        if first:
            self.weights.append(([], []))
        if self.weights and (first or numbers and numbers[0] in OPERATORS or values):
            self.weights[-1][0].extend(numbers)
            self.weights[-1][1].extend(values)

    def _weights(self, where: str) -> None:
        """V recomputed from its printed numbers, and W = V × γ, of each row read."""
        assert self.weights is not None
        for numbers, values in self.weights:
            expression = " ".join(numbers)
            volume, gamma, weight = values
            exact = _evaluate(expression.replace("×", "*").replace("−", "-").replace(" ", ""))
            self.check(rounded_like(exact, volume) == decimal_of(volume), f"{where} V = {expression}: {volume}")
            self.check(_product(volume, gamma, weight), f"{where} W = V × γ: {volume} × {gamma}")
        self.weights = None

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
    # Table 6.2.1: V and W of each row whose V is not 0; the current input has no 桁受け and no footing haunch, and
    # the soil no haunch layer nor its deduction (decision 79).
    shown = sum(row.volume.value != 0 for body in (sw.pedestal, sw.beam, sw.column, sw.footing, sw.overburden)
                for row in body.rows)
    assert shown == 6
    impacts = 3 * 4 * 4 * 3  # L = R × ρf, I, L = L × n, I for each of the three groups, for ①, ② and ③
    # the summary along the track also has the five combinations with the train of ② and ③ (decision 102)
    assert table_checks(lines) == 2 * shown + impacts + 10 + 2 * 8 + 2 * 5


def _wrong(result, field: str):
    """A result whose printed value no longer follows from the printed factors."""
    sw, train, lon, trans = result.self_weight, result.train, result.longitudinal, result.transverse
    if field == "beam_weight":
        return replace(result, self_weight=replace(sw, beam=replace(sw.beam, weight=Printed(1503.28, 2, "kN"))))
    if field == "double_impact":
        impact = replace(train.ultimate.origin_impact, double=Printed(0.223, 3, ""))
        return replace(result, train=replace(train, ultimate=replace(train.ultimate, origin_impact=impact)))
    if field == "floor":
        case_ = lon.cases[2]
        origin = replace(case_.origin, friction_floor=Printed(29.85, 2, "kN"))
        cases = (*lon.cases[:2], replace(case_, origin=origin), *lon.cases[3:])
        return replace(result, longitudinal=replace(lon, cases=cases))
    if field == "beam_row_weight":
        weights = (sw.beam.weights[0], Printed(312.58, 2, "kN"))
        return replace(result, self_weight=replace(sw, beam=replace(sw.beam, weights=weights)))
    if field == "column_volume":
        rows = (replace(sw.column.rows[0], volume=Printed(59.536, 3, "m3")),)
        return replace(result, self_weight=replace(sw, column=replace(sw.column, rows=rows)))
    assert field == "moment"
    wind = replace(trans.origin.wind_with_train, moment=Printed(1323.26, 2, "kN m"))
    side = replace(trans.origin, wind_with_train=wind)
    return replace(result, transverse=replace(trans, origin=side))


@pytest.mark.parametrize("field,expected", [
    ("beam_weight", {"1190.70+312.57"}),
    # The double-track impact is a factor of the movable bearing's Rm in the safety and restorability cases;
    # 0.223 × 0.75 still prints 0.167.
    ("double_impact", {"0.245*(1-18.850/200)", "0.223*0.763",
                       "1.1*5740.00+1.2*520.00+1.35*272.47*2.000*(1+0.223)+740.00",
                       "1.1*5740.00+1.2*520.00+1.23*272.47*2.000*(1+0.223)+740.00",
                       "1.0*5740.00+1.0*520.00+1.23*272.47*2.000*(1+0.223)+740.00"}),
    # The friction floor μ·T/n is printed as a candidate of H; it does not govern here.
    ("floor", {"0.10*298.40"}),
])
def test_a_value_that_does_not_follow_from_the_printed_factors_is_found(tmp_path: Path, field: str, expected: set[str]):
    result, pier = case("current")
    checks = formula_checks(render(tmp_path, _wrong(result, field), pier))
    assert {check.expression for check in checks if not check.ok} == expected


@pytest.mark.parametrize("field,expected", [
    ("moment", ["M = H × y: 197.00 × 6.717"]),
    ("beam_row_weight", ["W = V × γ: 12.758 × 24.5"]),
    # V = 59.536 neither follows from its numbers nor gives the printed W.
    ("column_volume", ["V = 2.700 × 4.500 × 4.900: 59.536", "W = V × γ: 59.536 × 24.5"]),
])
def test_a_table_cell_that_does_not_follow_is_found(tmp_path: Path, field: str, expected: list[str]):
    result, pier = case("current")
    lines = printed_lines(render(tmp_path, _wrong(result, field), pier))
    failures = table_failures(lines)
    assert len(failures) == len(expected) and all(failure.endswith(end) for failure, end in zip(failures, expected))
