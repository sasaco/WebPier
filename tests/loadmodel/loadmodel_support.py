"""A small valid load model result: two bearings on each side, cases of every kind (decision 70)."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from webpier.loadmodel import (
    D1, D2, EQ2, WP_HIGH, WP_LOW, WP_NORMAL, BasicCase, BearingAction, BearingRef, BearingSlot, CantileverCombination,
    CantileverRow, CantileverTerm, Candidate, Combination, Context, ExtractionGroup, FrameDirection, Increment,
    LoadModelResult, MaxResponse, Paragraph, Section, Seismic, SeismicCombination, SeismicDirection, Side, SpringTerm,
    Table, Term, pier_wind,
)

B1, B2 = BearingRef(Side.ORIGIN, 1), BearingRef(Side.ORIGIN, 2)
C1, C2 = BearingRef(Side.END, 1), BearingRef(Side.END, 2)
CONTEXT = Context(Path("input.json"), tuple(BearingSlot(ref, Decimal(position)) for ref, position in (
    (B1, "-1.500"), (B2, "1.500"), (C1, "-1.500"), (C2, "1.500"))))


def D(text: str) -> Decimal:
    return Decimal(text)


def one(case: str, sign: int = 1) -> Term:
    return Term(D("1.0"), (Candidate(case, sign),))


def result(**changes) -> LoadModelResult:
    cases = (
        BasicCase("L", "車荷重", SpringTerm.SHORT, (
            BearingAction(B1, vertical=D("100.00")), BearingAction(C1, vertical=D("120.00")))),
        BasicCase("BR", "制動荷重", SpringTerm.SHORT, (
            BearingAction(B1, longitudinal=D("10.00"), longitudinal_height=D("1.200")),
            BearingAction(C2, transverse=D("5.00"), transverse_height=D("0.800")))),
        BasicCase("EQ1", "上部工の慣性力", SpringTerm.SHORT, (
            BearingAction(B1, longitudinal=D("50.00"), transverse=D("40.00"), transverse_height=D("1.000")),),
                  Seismic(Increment.INCREMENTAL, SeismicDirection.EARTHQUAKE)),
        BasicCase("LE", "地震時の車荷重", SpringTerm.SHORT, (BearingAction(C1, vertical=D("30.00")),),
                  Seismic(Increment.FIXED, SeismicDirection.DOWNWARD)),
    )
    values = dict(
        cases=cases,
        longitudinal=(
            Combination("安全性", (Term(D("1.1"), (Candidate(D1),)), Term(D("1.2"), (Candidate(D2),)),
                                   Term(D("1.35"), (Candidate("L"),)), Term(D("1.0"), (Candidate("BR"), Candidate("BR", -1)))),
                        frozenset({ExtractionGroup.FAILURE, ExtractionGroup.STABILITY})),
            Combination("永久", (one(D1), one(D2), one(WP_HIGH)), frozenset({ExtractionGroup.PERMANENT})),
        ),
        transverse=(
            Combination("風", (one(D1), one(D2), Term(D("1.2"), (Candidate(pier_wind(1)), Candidate(pier_wind(1), -1)))),
                        frozenset({ExtractionGroup.FAILURE})),
            Combination("低水位", (one(D1), one(WP_LOW)), frozenset({ExtractionGroup.SUPPORT_LONG_TERM})),
        ),
        seismic_longitudinal=(SeismicCombination("L-EQ", (D1, D2, WP_NORMAL, "LE", EQ2, "EQ1")),),
        seismic_transverse=(SeismicCombination("T-EQ", (D1, D2, "LE", EQ2, "EQ1")),),
        cantilever=(
            CantileverCombination("破壊", (CantileverTerm(D1, D("1.1")), CantileverTerm("L", D("1.35"))),
                                  frozenset({CantileverRow.SAFETY})),
            CantileverCombination("地震時", (CantileverTerm(D1, D("1.0")),
                                            CantileverTerm("EQ1", MaxResponse(FrameDirection.TRANSVERSE))),
                                  frozenset({CantileverRow.RESTORABILITY_EQ})),
        ),
        pier_wind_pressures=(D("3.0"),),
        sections={"0610": (Section("車荷重", (Paragraph("指定値"), Table(("支承", "N"), (("B1", "100.00"),)))),)},
        provenance={"input": "input.addin.json", "sha256": "0" * 64},
    )
    values.update(changes)
    return LoadModelResult(**values)


def with_case(base: LoadModelResult, index: int, **changes) -> LoadModelResult:
    cases = list(base.cases)
    cases[index] = replace(cases[index], **changes)
    return replace(base, cases=tuple(cases))
