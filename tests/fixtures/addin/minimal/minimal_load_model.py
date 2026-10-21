"""A load model for the tests (decision 70): a vehicle load on two bearings, like P7, with its values written here.

The bearings are 起点側1 (支承位置 −3.8 m) and 終点側2 (+2.95 m) of tests/fixtures/inputs/current.json, both on the
cantilevers of the beam. It has what the tests need: no combination of 変動作用 (the zero case), the sign −1, heights
of the horizontal forces along and across the track, seismic cases fixed, incremental and limited incremental, and the
最大応答震度 in a cantilever combination. It imports webpier.loadmodel only.
"""

from decimal import Decimal

from webpier.loadmodel import (
    D1, D2, EQ2, WP_LOW, WP_NORMAL, BasicCase, BearingAction, BearingRef, CantileverCombination, CantileverRow,
    CantileverTerm, Candidate, Combination, Context, ExtractionGroup, FrameDirection, Increment, LoadModelResult,
    MaxResponse, Paragraph, Section, Seismic, SeismicCombination, SeismicDirection, Side, SpringTerm, Table, Term,
    pier_wind,
)

B1, C2 = BearingRef(Side.ORIGIN, 1), BearingRef(Side.END, 2)
G = ExtractionGroup
R = CantileverRow


def _d(text: str) -> Decimal:
    return Decimal(text)


def _term(factor: str, *cases: str, both: bool = False) -> Term:
    """*factor* on one of *cases*; *both*: each in either direction."""
    return Term(_d(factor), tuple(Candidate(case, sign) for case in cases for sign in ((1, -1) if both else (1,))))


CASES = (
    BasicCase("L", "車荷重", SpringTerm.SHORT, (
        BearingAction(B1, vertical=_d("300.00")), BearingAction(C2, vertical=_d("250.00")))),
    BasicCase("BR", "制動荷重", SpringTerm.SHORT, (
        BearingAction(B1, longitudinal=_d("20.00"), longitudinal_height=_d("1.500")),
        BearingAction(C2, longitudinal=_d("15.00"), longitudinal_height=_d("1.500")))),
    BasicCase("WG", "桁の風荷重", SpringTerm.SHORT, (
        BearingAction(B1, transverse=_d("8.00"), transverse_height=_d("2.000")),
        BearingAction(C2, transverse=_d("6.00"), transverse_height=_d("2.500")))),
    BasicCase("LE", "地震時の車荷重", SpringTerm.SHORT, (
        BearingAction(B1, vertical=_d("90.00")), BearingAction(C2, vertical=_d("80.00"))),
              Seismic(Increment.FIXED, SeismicDirection.DOWNWARD)),
    BasicCase("EQ1", "上部工の慣性力", SpringTerm.SHORT, (
        BearingAction(B1, longitudinal=_d("400.00"), transverse=_d("400.00"), transverse_height=_d("1.000")),
        BearingAction(C2, longitudinal=_d("350.00"), transverse=_d("350.00"), transverse_height=_d("1.200"))),
              Seismic(Increment.INCREMENTAL, SeismicDirection.EARTHQUAKE)),
    BasicCase("EQL", "活荷重慣性力", SpringTerm.SHORT, (
        BearingAction(B1, longitudinal=_d("60.00"), transverse=_d("60.00"), transverse_height=_d("2.000")),
        BearingAction(C2, longitudinal=_d("50.00"), transverse=_d("50.00"), transverse_height=_d("2.000"))),
              Seismic(Increment.LIMITED, SeismicDirection.EARTHQUAKE)),
)

LONGITUDINAL = (  # no combination of 変動作用 (G.VARIABLE): its extraction is the zero case
    Combination("破壊 車最大", (_term("1.1", D1), _term("1.2", D2), _term("1.35", "L"), _term("1.0", "BR", both=True)),
                frozenset({G.FAILURE, G.STABILITY})),
    Combination("ひび割れ 縁応力度", (_term("1.0", D1), _term("1.0", D2), _term("1.0", "L")),
                frozenset({G.PERMANENT_VARIABLE})),
    Combination("ひび割れ 永久", (_term("1.0", D1), _term("1.0", D2)), frozenset({G.PERMANENT})),
    Combination("損傷 車最大", (_term("1.0", D1), _term("1.0", D2), _term("1.0", "L"), _term("1.0", "BR", both=True)),
                frozenset({G.DAMAGE})),
    Combination("長期支持", (_term("1.0", D1), _term("1.0", D2), _term("1.0", WP_NORMAL)),
                frozenset({G.SUPPORT_LONG_TERM})),
    Combination("短期支持", (_term("1.0", D1), _term("1.0", D2), _term("1.0", WP_LOW), _term("1.0", "L")),
                frozenset({G.SUPPORT_SHORT_TERM})),
)
TRANSVERSE = (
    Combination("破壊 風最大", (_term("1.1", D1), _term("1.2", D2), _term("1.2", "WG", both=True),
                             _term("1.2", pier_wind(1), both=True)), frozenset({G.FAILURE, G.STABILITY})),
    Combination("ひび割れ 縁応力度", (_term("1.0", D1), _term("1.0", D2), _term("1.0", "L")),
                frozenset({G.PERMANENT_VARIABLE})),
    Combination("ひび割れ 永久", (_term("1.0", D1), _term("1.0", D2)), frozenset({G.PERMANENT})),
    Combination("損傷 車最大", (_term("1.0", D1), _term("1.0", D2), _term("1.0", "L"),
                             _term("1.0", "WG", both=True)), frozenset({G.DAMAGE})),
    Combination("長期支持", (_term("1.0", D1), _term("1.0", D2), _term("1.0", WP_NORMAL)),
                frozenset({G.SUPPORT_LONG_TERM})),
    Combination("短期支持", (_term("1.0", D1), _term("1.0", D2), _term("1.0", WP_LOW), _term("1.0", "L"),
                         _term("1.0", pier_wind(1), both=True)), frozenset({G.SUPPORT_SHORT_TERM})),
)
SEISMIC = (SeismicCombination("地震時", (D1, D2, WP_NORMAL, "LE", "EQ1", "EQL", EQ2)),)
CANTILEVER = (  # no combination of 使用性（損傷） (R.SERVICEABILITY_DAMAGE): its forces are 0
    CantileverCombination("破壊 車最大", (CantileverTerm(D1, _d("1.1")), CantileverTerm(D2, _d("1.2")),
                                      CantileverTerm("L", _d("1.35")), CantileverTerm("BR", _d("1.0"))),
                          frozenset({R.SAFETY})),
    CantileverCombination("永久", (CantileverTerm(D1, _d("1.0")), CantileverTerm(D2, _d("1.0"))),
                          frozenset({R.DURABILITY_STRESS, R.DURABILITY_PERMANENT, R.FATIGUE_PERMANENT})),
    CantileverCombination("永久＋変動", (CantileverTerm(D1, _d("1.0")), CantileverTerm(D2, _d("1.0")),
                                     CantileverTerm("L", _d("1.0"))),
                          frozenset({R.DURABILITY_STRESS, R.FATIGUE_VARIABLE})),
    CantileverCombination("変動", (CantileverTerm("L", _d("1.0")),), frozenset({R.DURABILITY_VARIABLE})),
    CantileverCombination("地震時", (CantileverTerm(D1, _d("1.0")), CantileverTerm(D2, _d("1.0")),
                                    CantileverTerm("LE", _d("1.0")),
                                    CantileverTerm("EQ1", MaxResponse(FrameDirection.TRANSVERSE))),
                          frozenset({R.RESTORABILITY_EQ})),
)
SECTIONS = {
    "0610": (Section("車荷重の根拠", (
        Paragraph("車荷重の反力は設計資料の支承ごとの指定値とする。"),
        Table(("支承", "鉛直力 (kN)"), (("起点側1", "300.00"), ("終点側2", "250.00"))))),),
    "0710": (Section("地震時の作用の根拠", (Paragraph("上部工の慣性力と活荷重慣性力は支承ごとの指定値とする。"),)),),
}


class MinimalLoadModel:
    def calculate(self, context: Context) -> LoadModelResult:
        return LoadModelResult(
            cases=CASES, longitudinal=LONGITUDINAL, transverse=TRANSVERSE, seismic_longitudinal=SEISMIC,
            seismic_transverse=SEISMIC, cantilever=CANTILEVER, pier_wind_pressures=(_d("3.0"),), sections=SECTIONS,
            provenance={"source": "tests/fixtures/addin/minimal", "bearings": len(context.bearings)})


def load_model() -> MinimalLoadModel:
    return MinimalLoadModel()
