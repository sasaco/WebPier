"""The 地盤変位 of a pile foundation on G3〜G5 in the reports (decision 97): 表層地盤の挙動 at the end of 0710 (10.5) and 0720
(11.5), and 応答変位法による設計応答値の算定 at the head of 0711 and 0721, before Aggre-SE's report.

As Example橋脚4 prints them (IV-3〜6: the layers, the surface displacement ag and the program's Tg, ag and f(z) at the top of
each layer; IV-55〜58: α, the correction factors ν and the table of the Cases), without the sentences that explain them
(decision 55). Tg, ag and f(z) are SoilStructure's as WebPier reads them (calc.ground_displacement): the formulas of ag are
printed with their symbols only, as the sample does, so that a hand recalculation from the printed Tg is not offered as the
value (SoilStructure works in single precision).
"""

from __future__ import annotations

from typing import Any

from gridlayoutpdf import Row

from ...calc.ground_displacement import GroundDisplacement
from ...calc.response_displacement import ResponseDisplacementResult
from ...core.printed import Precision
from ..equations import script, terms
from ..numbers import unit
from .frame_report import Manuscript, Span, TableSpec, sub, value

COEFFICIENT = Precision(2, "")
NUMBERS = "①②③④"
LEVELS = {"L1": "L1地震動", "L2": "L2地震動"}


def _cell(*parts: Any) -> Row:
    return Row(*parts, gap=0)


def surface_ground(m: Manuscript, ground: GroundDisplacement, number: str) -> None:
    """*number* 表層地盤の挙動 (10.5, 11.5)."""
    m.heading("ground.heading", f"{number} 表層地盤の挙動", 1)
    m.heading("ground.layers.heading", "(1) 地盤条件", 2)
    rows: list[tuple[Any, ...]] = [
        (Span("層番号", rowspan=2), Span("層", rowspan=2), "層厚", "単位体積重量", "せん断弾性波速度"),
        ("(m)", _cell("γ (", unit("kN/m3"), ")"), _cell(sub("V", "s"), " (m/s)"))]
    for index, layer in enumerate(ground.layers, 1):
        rows.append((str(index), layer.name, value(layer.thickness), value(layer.unit_weight), value(layer.velocity)))
    m.table("ground.layers", TableSpec((3, 7, 4, 6, 7), tuple(rows), (1,) * len(rows), header_rows=2,
                                       numeric=frozenset({0, 2, 3, 4})))
    m.equation("ground.region", "地域別係数", sub("ν", "a"), value(COEFFICIENT(float(ground.region_coefficient))))
    m.heading("ground.surface.heading", "(2) 地表面最大水平変位量", 2)
    tg = sub("T", "g")
    m.line("ground.l1", _cell(sub("a", "g"), " = ", sub("ν", "a"), " × 0.064 × ",
                              script("T", subscript="g", superscript="2.1"), "（L1地震動）"))
    m.line("ground.l2", _cell(sub("a", "g"), " = ", script("ν", subscript="a", superscript="0.90"), " × 0.413 × ", tg,
                              "（L2地震動 スペクトルⅡ）"))
    surface = ground.profile[0]
    rows = [("固有周期", Span("地表面最大水平変位量", colspan=2)),
            (_cell(tg, " (s)"), _cell(sub("a", "g"), " L1地震動 (mm)"), _cell(sub("a", "g"), " L2地震動 (mm)")),
            (value(ground.period), value(surface.l1), value(surface.l2))]
    m.table("ground.surface", TableSpec((7, 9, 9), tuple(rows), (1, 1, 1), header_rows=2,
                                        numeric=frozenset({0, 1, 2})))
    m.heading("ground.profile.heading", "(3) 地盤の設計水平変位量の鉛直方向分布", 2)
    rows = [("深さ", Span("地盤変位 f(z)", colspan=2)), ("z (m)", "L1地震動 (mm)", "L2地震動 (mm)")]
    rows += [(value(point.depth), value(point.l1), value(point.l2)) for point in ground.profile]
    m.table("ground.profile", TableSpec((7, 9, 9), tuple(rows), (1,) * len(rows), header_rows=2,
                                        numeric=frozenset({0, 1, 2})))


def response_displacement(m: Manuscript, result: ResponseDisplacementResult, first_case: int) -> None:
    """応答変位法による設計応答値の算定: the inertia Case, the factors and the Cases, numbered in Aggre-SE's project from
    *first_case*."""
    inertia = result.inertia
    m.heading("response.heading", "応答変位法による設計応答値の算定", 1)
    m.heading("response.inertia.heading", "(1) 応答変位法に用いる慣性力", 2)
    rows: list[tuple[Any, ...]] = [
        (Span("Case", rowspan=2), "等価固有周期", "全体系折曲点震度", Span("最大応答震度", colspan=2)),
        (_cell(sub("T", "eq"), " (s)"), sub("K", "heq"), "L1地震動", "L2地震動"),
        (str(inertia.case), value(inertia.teq), value(inertia.kheq), value(inertia.kh_l1), value(inertia.kh_l2))]
    m.table("response.inertia", TableSpec((3, 6, 7, 5, 5), tuple(rows), (1, 1, 1), header_rows=2,
                                          numeric=frozenset({0, 1, 2, 3, 4})))
    m.heading("response.factor.heading", "(2) 慣性力と地盤変位を組み合わせるための補正係数", 2)
    m.equation("response.alpha", "", "α", terms(sub("T", "eq"), "/", "(", sub("T", "g"), "/", sub("α", "g"), ")"))
    nu_u, nu_l = sub("ν", "U"), sub("ν", "L")
    for key, condition, upper, lower in (("response.upper", "α ≦ 0.75", "1.0", "0.0"),
                                         ("response.middle", "0.75 ＜ α ＜ 1.10", "−2.0α + 2.5", "−2.0α + 1.5"),
                                         ("response.lower", "1.10 ≦ α", "0.3", "−0.7")):
        m.line(key, _cell(f"{condition}：", nu_u, f" = {upper}，", nu_l, f" = {lower}"))
    rows = [("地震動", sub("α", "g"), _cell(sub("T", "g"), " (s)"), _cell(sub("T", "eq"), " (s)"), "α", nu_u, nu_l,
             _cell("採用 ", nu_u))]
    for found in result.corrections:
        rows.append((LEVELS[found.level], value(found.alpha_g), value(found.tg), value(found.teq), value(found.alpha),
                     value(found.upper), value(found.lower), value(found.adopted)))
    m.table("response.factors", TableSpec((4, 2, 4, 4, 3, 3, 3, 4), tuple(rows), (1,) * len(rows),
                                          numeric=frozenset(range(1, 8))))
    if any(found.yielded for found in result.corrections):
        m.line("response.yielded", _cell("最大応答震度が全体系折曲点震度を超える地震動は ", nu_u, " = 1.0 とする．"))
    m.heading("response.cases.heading", "(3) 荷重の組合せ", 2)
    rows = [("Case", "地震動", _cell("慣性力 ν×", sub("R", "a")), "地盤変位 ν×f(z)", "最大応答震度")]
    for index, case in enumerate(result.cases):
        rows.append((str(first_case + index), f"{LEVELS[case.level]} {NUMBERS[case.number - 1]}",
                     value(case.inertia), value(case.displacement), value(case.kh)))
    m.table("response.cases", TableSpec((3, 6, 6, 7, 5), tuple(rows), (1,) * len(rows),
                                        numeric=frozenset({0, 2, 3, 4})))
