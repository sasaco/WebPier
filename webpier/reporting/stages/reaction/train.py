"""6.3 Train loads: the moving-load reactions, load factors, girder impact and the seismic train."""

from __future__ import annotations

from typing import Any

from gridlayoutpdf import Row

from ....calc.moving_load import AXLES, Girder, MovingLoadResult
from ....calc.reaction import ReactionResult
from ....calc.reaction.train import (
    DOUBLE_TRACK_SPAN, SEISMIC_SHARE, SERVICE_RATIO, GirderImpact, GroupTrain, Layout, LayoutTrain, PierImpact,
    PierImpactRatio,
)
from ....core.printed import Printed
from ....inputs import PierInput
from .manuscript import (
    BODY, DETAIL, ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, cells, expr, join, sub,
)
from .figures import loading_figure
from .tables import header

GROUPS = (("ultimate", "(a) 安全性（破壊）および復旧性の照査に用いる列車荷重"),
          ("service", "(b) 使用性の照査に用いる列車荷重"),
          ("fatigue", "(c) 安全性（疲労破壊）の照査に用いる列車荷重"))


INLINE_AXLES = 8  # RB = P × (a1 + … + a8) / l still fits one line (406 pt); more wrap inside the group


def _groups(loading: MovingLoadResult, girder: Girder) -> list[tuple[Printed, list[Printed]]]:
    """The levers by axle load: one group for a train of one axle load, else by load in train order of each load's first
    axle (A-17's 130 then 190, decision 101)."""
    axles = loading.on(girder)
    if loading.axle_load is not None:
        return [(loading.axle_load, [axle.lever for axle in axles])] if axles else []
    found: dict[float, tuple[Printed, list[Printed]]] = {}
    for axle in axles:
        load = loading.load(axle)
        found.setdefault(load.value, (load, []))[1].append(axle.lever)
    return list(found.values())


def _terms(parts: list[list[Any]]) -> list[Any]:
    joined: list[Any] = []
    for part in parts:
        joined += [*(("+",) if joined else ()), *part]
    return joined


def loading_lines(m: Manuscript, key: str, loading: MovingLoadResult, pier: PierInput) -> None:
    """The loading figure, then RB = (q a e + Σ P Σa) / l and RA = Σ P × (axles) + q a − RB in numbers, from the
    printed levers, lengths and axle counts (07 7-1; Example3 Ⅳ-1-2 for the line load)."""
    spans = pier.spans
    m.figure(key + ".figure", loading_figure(loading, pier), SUBSECTION)
    m.start(key + ".reactions")
    sides = ((Girder.ORIGIN, "B", "A", loading.rb, loading.ra, spans.origin.span, loading.origin_axles),
             (Girder.END, "C", "D", loading.rc, loading.rd, spans.end.span, loading.end_axles))
    for girder, pier_support, far_support, near, far, span, count in sides:
        axles, tail = loading.on(girder), loading.tail(girder)
        groups = _groups(loading, girder)
        lhs, other = sub("R", pier_support), sub("R", far_support)
        name = f"{key}.{pier_support.lower()}"
        if axles or tail is not None:
            moments = [] if tail is None else [[tail.load, "×", tail.length, "×", tail.lever]]
            moments += [[load, "×", "(", *join(levers), ")"] for load, levers in groups]
            numerator = moments[0] if len(moments) == 1 else ["(", *_terms(moments), ")"]
            # A long span carries more axles than one line holds (P7 終点側 61.390 m, 12 axles): the levers' group
            # wraps. A short one stays one run, as the reference prints it.
            m.formula(name, lhs, None, (*numerator, "/", span), near,
                      gap=girder is Girder.END, open_groups=len(axles) > INLINE_AXLES or len(moments) > 1)
            weights = [] if tail is None else [[tail.load, "×", tail.length]]
            # one axle load: the count is the calculator's (07 7-1); A-17's counts are by load
            weights += ([[groups[0][0], "×", count]] if len(groups) == 1
                        else [[load, "×", AXLES(len(levers))] for load, levers in groups])
            m.formula(f"{key}.{far_support.lower()}", other, None, (*_terms(weights), "−", near), far)
        else:
            m.value(name, lhs, near, gap=girder is Girder.END)
            m.value(f"{key}.{far_support.lower()}", other, far)
    m.end()


# 列車の配置 (decision 102): the headings of Example橋脚4 III-32〜III-33, and the keys of ② and ③ (①'s are the stem's)
PLACING_TITLES = {Layout.BOTH: "①：両側の桁に配置した場合", Layout.ORIGIN: "②：起点側の桁のみに配置した場合",
                  Layout.END: "③：終点側の桁のみに配置した場合"}
_TOKENS = {Layout.ORIGIN: "one_origin", Layout.END: "one_end"}


def placed_key(stem: str, layout: Layout) -> str:
    return stem if layout is Layout.BOTH else f"{stem}.{_TOKENS[layout]}"


def _placings(result: ReactionResult) -> list[LayoutTrain]:
    return [result.train.layout(layout) for layout in Layout]


def _impact_table(group: GroupTrain, result: ReactionResult, loading: MovingLoadResult) -> TableSpec:
    dead = result.dead
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
    return TableSpec((3, 6, 4, 4, 4, 4), tuple(rows), header_rows=1, numeric_columns=(2, 3, 4, 5))


def _coefficients(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    train = result.train
    m.heading("train.impact.heading", "(2) 衝撃係数", SUBSECTION)
    sides = (("origin", "起点側桁", pier.spans.origin), ("end", "終点側桁", pier.spans.end))
    m.heading("train.impact.ultimate.heading", "1) 安全性（破壊）および復旧性", ITEM)
    for key, name, span in sides:
        impact: GirderImpact = getattr(train.ultimate, key + "_impact")
        m.start(f"train.impact.ultimate.{key}")
        m.paragraph(f"train.impact.ultimate.{key}.label", name, gap=True)
        m.value(f"train.impact.ultimate.{key}.single", Row(sub("i", "F"), "(単線)", gap=0), impact.single, medium=True)
        m.formula(f"train.impact.ultimate.{key}.double", Row(sub("i", "F"), "(複線)", gap=0), None,
                  (impact.single, "×", "(", 1, "−", span.span, "/", DOUBLE_TRACK_SPAN, ")"), impact.double, medium=True)
        m.end()
    m.heading("train.impact.service.heading", "2) 使用性および安全性（疲労破壊）", ITEM)
    for key, name, _ in sides:
        ultimate: GirderImpact = getattr(train.ultimate, key + "_impact")
        service: GirderImpact = getattr(train.service, key + "_impact")
        m.start(f"train.impact.service.{key}")
        m.paragraph(f"train.impact.service.{key}.label", name, gap=True)
        for track, label in (("single", "(単線)"), ("double", "(複線)")):
            m.formula(f"train.impact.service.{key}.{track}", Row(sub("i", "F"), label, gap=0), None,
                      (getattr(ultimate, track), "×", SERVICE_RATIO), getattr(service, track), medium=True)
        fatigue: GirderImpact = getattr(train.fatigue, key + "_impact")
        m.paragraph(f"train.impact.fatigue.{key}.label", "（安全性（疲労破壊））", gap=True)
        for track, label in (("single", "(単線)"), ("double", "(複線)")):
            m.value(f"train.impact.fatigue.{key}.{track}", Row(sub("i", "F"), label, gap=0), getattr(fatigue, track),
                    medium=True)
        m.end()
    _pier_coefficients(m, result)


def _ratio(m: Manuscript, key: str, label: str, on_pier: PierImpact, ratio: PierImpactRatio) -> None:
    lhs = Row("r", label, gap=0)
    if ratio.limited:
        m.value(key, lhs, ratio.ratio)  # Ds/(L + Du + Ds) of 0.9 or more: no impact on the pier body
        return
    symbolic = expr(1, "−", sub("D", "S"), "/", "(", "L", "+", sub("D", "U"), "+", sub("D", "S"), ")")
    m.formula(key, lhs, symbolic,
              (1, "−", on_pier.weight, "/", "(", ratio.train, "+", on_pier.dead, "+", on_pier.weight, ")"),
              ratio.ratio, medium=True)


def _pier_coefficients(m: Manuscript, result: ReactionResult) -> None:
    """Impact on the pier body: i = i0 × (1 − Ds/(L + Du + Ds)) (RC標準 解4.4.4, Example3 Ⅱ-2-6; decision 77), with the
    L of each 列車の配置 (decision 102; Example橋脚4 III-35〜III-37)."""
    first = result.train.pier_impact
    m.heading("train.impact.pier.heading", "3) 橋脚く体に対する衝撃係数", ITEM)
    m.start("train.impact.pier.loads")
    m.value("train.impact.pier.du", sub("D", "U"), first.dead, medium=True)
    m.value("train.impact.pier.ds", sub("D", "S"), first.weight, medium=True)
    m.end()
    for placed in _placings(result):
        on_pier = placed.pier_impact
        stem = placed_key("train.impact.pier", placed.layout)
        m.start(f"{stem}.placed")
        m.paragraph(f"{stem}.placed.label", PLACING_TITLES[placed.layout], gap=True)
        for track, label in (("single", "(単線)"), ("double", "(複線)")):
            m.value(f"{stem}.{track}.l", Row("L", label, gap=0), getattr(on_pier, track).train, medium=True)
        for track, label in (("single", "(単線)"), ("double", "(複線)")):
            _ratio(m, f"{stem}.{track}.ratio", label, on_pier, getattr(on_pier, track))
        m.end()
        for usage, title in (("ultimate", "安全性（破壊）および復旧性"), ("service", "使用性"),
                             ("fatigue", "安全性（疲労破壊）")):
            group: GroupTrain = getattr(placed, usage)
            for key, name in (("origin", "起点側桁"), ("end", "終点側桁")):
                girder: GirderImpact = getattr(group, key + "_impact")
                on: GirderImpact = getattr(group, key + "_pier_impact")
                m.start(f"{stem}.{usage}.{key}")
                m.paragraph(f"{stem}.{usage}.{key}.label", f"{title}　{name}", gap=True)
                for track, label in (("single", "(単線)"), ("double", "(複線)")):
                    m.formula(f"{stem}.{usage}.{key}.{track}", Row("i", label, gap=0), None,
                              (getattr(girder, track), "×", getattr(on_pier, track).ratio), getattr(on, track),
                              medium=True)
                m.end()


def section(m: Manuscript, result: ReactionResult, pier: PierInput) -> None:
    train = result.train
    m.heading("train.heading", "6.3 列車荷重", SECTION)
    m.heading("train.loading.heading", "(1) 移動荷重による支点反力", SUBSECTION)
    for placed in _placings(result):
        key = placed_key("train.loading", placed.layout)
        m.heading(f"{key}.placing.heading", PLACING_TITLES[placed.layout], ITEM)
        loading_lines(m, key, placed.loading, pier)
    _coefficients(m, result, pier)
    m.heading("train.groups.heading", "(3) 列車荷重と衝撃荷重", SUBSECTION)
    for key, title in GROUPS:
        m.heading(f"train.{key}.heading", title, DETAIL)
        m.value(f"train.{key}.factor", Row("荷重修正係数 ", "ρf", gap=0), getattr(train, key).load_factor, left=BODY,
                equal=BODY + 6)  # the label takes six columns
        for placed in _placings(result):
            stem = placed_key(f"train.{key}", placed.layout)
            m.paragraph(f"{stem}.placing", PLACING_TITLES[placed.layout], gap=True)
            m.table(f"{stem}.table", _impact_table(getattr(placed, key), result, placed.loading), SUBSECTION)
    seismic = train.seismic
    m.heading("train.seismic.heading", "(4) 地震時列車荷重", SUBSECTION)
    for key, name, far, near, length, value, span in (
            ("origin", "起点側桁", "A", "B", seismic.origin_length, seismic.origin, pier.spans.origin),
            ("end", "終点側桁", "D", "C", seismic.end_length, seismic.end, pier.spans.end)):
        m.start(f"train.seismic.{key}")
        m.paragraph(f"train.seismic.{key}.label", name, gap=True)
        m.formula(f"train.seismic.{key}.length", "L", None, (span.l1, "+", span.span, "+", span.l2), length)
        m.formula(f"train.seismic.{key}.reaction", Row(sub("R", far), " = ", sub("R", near), gap=0),
                  None, (seismic.line_load, "×", length, "×", SEISMIC_SHARE),
                  value, medium=True)
        m.end()
