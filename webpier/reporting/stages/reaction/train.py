"""6.3 Train loads: the moving-load reactions, load factors, girder impact and the seismic train."""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.moving_load import Girder, MovingLoadResult
from ....calc.reaction import ReactionResult
from ....calc.reaction.train import DOUBLE_TRACK_SPAN, SEISMIC_SHARE, SERVICE_RATIO, GirderImpact, GroupTrain
from ....inputs import PierInput
from ...numbers import decimal_constant, printed
from .manuscript import (
    BODY, DETAIL, ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, cells, join, sub, symbols,
)
from .tables import GIRDER_ROW, header

GIRDERS = {Girder.ORIGIN: "起点側桁", Girder.END: "終点側桁"}
GROUPS = (("ultimate", "(a) 安全性（破壊）および復旧性の照査に用いる列車荷重"),
          ("service", "(b) 使用性の照査に用いる列車荷重"),
          ("fatigue", "(c) 安全性（疲労破壊）の照査に用いる列車荷重"))


def group_symbols(*parts: str) -> Row:
    return Row("(", symbols(*parts), ")")


def _axle_table(loading: MovingLoadResult) -> TableSpec:
    rows = [header("軸", "位置 x (m)", "載荷する桁", "距離 a (m)")]
    for index, axle in enumerate(loading.axles, 1):
        rows.append(cells(CellSpec(str(index), align="center"), axle.position,
                          CellSpec(GIRDERS[axle.girder], align="center"), axle.lever))
    return TableSpec((43.56, 87.12, 87.12, 87.12), tuple(rows), header_rows=1, row_height=GIRDER_ROW,
                     numeric_columns=(1, 3))


def loading_lines(m: Manuscript, key: str, loading: MovingLoadResult, pier: PierInput, load: str) -> None:
    """RB = P Σa / l and RA = P × (axles) − RB for each girder, from the printed levers."""
    spans = pier.spans
    m.table(key + ".axles", _axle_table(loading), SUBSECTION)
    m.start(key + ".reactions")
    sides = ((Girder.ORIGIN, "B", "A", loading.rb, loading.ra, spans.origin.span),
             (Girder.END, "C", "D", loading.rc, loading.rd, spans.end.span))
    for girder, pier_support, far_support, near, far, span in sides:
        levers = [axle.lever for axle in loading.axles if axle.girder is girder]
        lhs, other = sub("R", pier_support), sub("R", far_support)
        name = f"{key}.{pier_support.lower()}"
        if levers:
            m.formula(name, lhs, symbols(load, "×", "Σa", "/", "l"),
                      (loading.axle_load, "×", "(", *join(levers), ")", "/", span), near, gap=girder is Girder.END)
            m.formula(f"{key}.{far_support.lower()}", other, symbols(load, "×", f"{len(levers)}", "−", lhs),
                      (loading.axle_load, "×", len(levers), "−", near), far)
        else:
            m.value(name, lhs, near, gap=girder is Girder.END)
            m.value(f"{key}.{far_support.lower()}", other, far)
            m.paragraph(f"{name}.none", f"{GIRDERS[girder]}には軸が載らない。")
    m.end()


def _impact_table(group: GroupTrain, result: ReactionResult) -> TableSpec:
    loading, dead = result.train.loading, result.dead
    supports = ("a", "b", "c", "d")
    single, double = group.single, group.double

    def values(track, field):  # noqa: ANN001, ANN202 - small local accessor
        return [getattr(getattr(track, support), field) for support in supports]

    rows = [header("", "", sub("R", "A"), sub("R", "B"), sub("R", "C"), sub("R", "D")),
            cells(CellSpec("列車反力 R", colspan=2, align="center"), loading.ra, loading.rb, loading.rc, loading.rd),
            cells(CellSpec("単線", rowspan=3, align="center"), "列車荷重 L", *values(single, "load"), align="center"),
            cells("衝撃係数 i", *values(single, "coefficient"), align="center"),
            cells("衝撃荷重 I", *values(single, "impact"), align="center"),
            cells(CellSpec("複線", rowspan=4, align="center"), "軌道数 n", dead.origin.track_total,
                  dead.origin.track_total, dead.end.track_total, dead.end.track_total, align="center"),
            cells("列車荷重 L", *values(double, "load"), align="center"),
            cells("衝撃係数 i", *values(double, "coefficient"), align="center"),
            cells("衝撃荷重 I", *values(double, "impact"), align="center")]
    return TableSpec((50.88, 87.12, 72.6, 72.6, 72.6, 72.6), tuple(rows), header_rows=1, row_height=GIRDER_ROW,
                     numeric_columns=(2, 3, 4, 5))


def _coefficients(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    train = result.train
    m.heading("train.impact.heading", "(2) 衝撃係数", SUBSECTION)
    m.paragraph("train.impact.introduction",
                "衝撃係数は桁の衝撃係数とし、後続の照査でもこの値をそのまま用いる。複線載荷の係数は"
                "単線の係数に (1 − L/200) を乗じた1つの式で求める（L はスパン長、L < 200 m）。")
    sides = (("origin", "起点側桁", pier.spans.origin), ("end", "終点側桁", pier.spans.end))
    m.heading("train.impact.ultimate.heading", "1) 安全性（破壊）および復旧性", ITEM)
    for key, name, span in sides:
        impact: GirderImpact = getattr(train.ultimate, key + "_impact")
        m.start(f"train.impact.ultimate.{key}")
        m.paragraph(f"train.impact.ultimate.{key}.label", name)
        m.value(f"train.impact.ultimate.{key}.single", Row(sub("i", "F"), "(単線)", gap=0), impact.single, medium=True)
        m.formula(f"train.impact.ultimate.{key}.double", Row(sub("i", "F"), "(複線)", gap=0),
                  symbols(Row(sub("i", "F"), "(単線)", gap=0), "×",
                          group_symbols("1", "−", "L", "/", decimal_constant(DOUBLE_TRACK_SPAN))),
                  (impact.single, "×", "(", 1, "−", span.span, "/", DOUBLE_TRACK_SPAN, ")"), impact.double, medium=True)
        m.end()
    m.heading("train.impact.service.heading", "2) 使用性および安全性（疲労破壊）", ITEM)
    m.paragraph("train.impact.service.introduction",
                "安全性（破壊）の衝撃係数に 3/4 を乗じる。安全性（疲労破壊）も同じ係数を用いる。")
    for key, name, _ in sides:
        ultimate: GirderImpact = getattr(train.ultimate, key + "_impact")
        service: GirderImpact = getattr(train.service, key + "_impact")
        m.start(f"train.impact.service.{key}")
        m.paragraph(f"train.impact.service.{key}.label", name)
        for track, label in (("single", "(単線)"), ("double", "(複線)")):
            m.formula(f"train.impact.service.{key}.{track}", Row(sub("i", "F"), label, gap=0), None,
                      (getattr(ultimate, track), "×", SERVICE_RATIO), getattr(service, track), medium=True)
        fatigue: GirderImpact = getattr(train.fatigue, key + "_impact")
        m.paragraph(f"train.impact.fatigue.{key}.label", "（安全性（疲労破壊））")
        for track, label in (("single", "(単線)"), ("double", "(複線)")):
            m.value(f"train.impact.fatigue.{key}.{track}", Row(sub("i", "F"), label, gap=0), getattr(fatigue, track),
                    medium=True)
        m.end()


def section(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    t, train = pier.train, result.train
    m.heading("train.heading", "6.3 列車荷重", SECTION)
    m.heading("train.loading.heading", "(1) 移動荷重による支点反力", SUBSECTION)
    m.paragraph("train.loading.vehicle",
                f"車両 {t.vehicle}：軸重 P = {printed(train.loading.axle_load)} kN、1両の長さ Lv = "
                f"{printed(t.car_length)} m、軸距 a1 = {printed(t.a1)} m（連結部）、a2 = {printed(t.a2)} m、"
                f"{t.cars} 両編成。")
    m.paragraph("train.loading.introduction",
                "1軌道の列車を RB + RC が最大となる位置に載荷する（荷重修正係数を乗じない）。位置 x は起点側桁の"
                "他端からの距離、a は各桁の他端の支点（A または D）からの距離、l はスパン長である。")
    loading_lines(m, "train.loading", train.loading, pier, "P")
    _coefficients(m, result, pier)
    m.heading("train.groups.heading", "(3) 列車荷重と衝撃荷重", SUBSECTION)
    m.paragraph("train.groups.introduction",
                "単線の列車荷重は L = R × ρf、複線は単線の列車荷重に軌道数 n を乗じる。衝撃荷重は I = L × i とする。")
    for key, title in GROUPS:
        group: GroupTrain = getattr(train, key)
        m.heading(f"train.{key}.heading", title, DETAIL)
        m.value(f"train.{key}.factor", Row("荷重修正係数 ", "ρf", gap=0), group.load_factor, left=BODY, medium=True)
        m.table(f"train.{key}.table", _impact_table(group, result), SUBSECTION)
    seismic = train.seismic
    m.heading("train.seismic.heading", "(4) 地震時列車荷重", SUBSECTION)
    m.paragraph("train.seismic.introduction",
                f"地震時の列車荷重 e = {printed(seismic.line_load)} kN/m（1軌道）を桁長 L に載荷し、"
                "両端に 1/2 ずつ分配する。")
    for key, name, far, near, length, value, span in (
            ("origin", "起点側桁", "A", "B", seismic.origin_length, seismic.origin, pier.spans.origin),
            ("end", "終点側桁", "D", "C", seismic.end_length, seismic.end, pier.spans.end)):
        m.start(f"train.seismic.{key}")
        m.paragraph(f"train.seismic.{key}.label", name)
        m.formula(f"train.seismic.{key}.length", "L", symbols("L1", "+", "l", "+", "L2"),
                  (span.l1, "+", span.span, "+", span.l2), length)
        m.formula(f"train.seismic.{key}.reaction", Row(sub("R", far), " = ", sub("R", near), gap=0),
                  symbols("e", "×", "L", "×", decimal_constant(SEISMIC_SHARE)),
                  (seismic.line_load, "×", length, "×", SEISMIC_SHARE),
                  value, medium=True)
        m.end()
