"""13.1 (2) 水平荷重: the forces on the girders and at their bearings, and what the rubber bearings and the
stoppers take (Example2 13-15 to 13-22)."""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.cantilever import CantileverResult
from ....calc.cantilever.bearings import BearingCase, Device, GirderDevices
from ....calc.cantilever.geometry import GIRDER_SIDES
from ....calc.moving_load import Girder
from ....calc.reaction import ReactionResult
from ....calc.reaction.longitudinal import (ADHESION, BEARING_LINES, DEFINITIONS, FRICTION_SHARE, LONG_RAIL,
                                            LONG_RAIL_SERVICE, BearingType, LongitudinalCase)
from ....core.printed import Printed
from ....inputs import PierInput
from ...numbers import decimal_constant, printed
from ..reaction.manuscript import (DETAIL, INDENTED, ITEM, PAIR_SECOND, SUBSECTION, CellSpec, Manuscript, TableSpec,
                                   cells, sub)
from ..reaction.tables import GIRDER_ROW, header

SNOW = {"snow2": "S2", "snow10": "S10", "snow30": "S30"}
MARKS = {Girder.ORIGIN: "T1", Girder.END: "T2"}
BEARINGS = {BearingType.FIXED: "固定", BearingType.MOVABLE: "可動"}
EQ_LABEL = "1.0 EQ（桁荷重）"


def combination_text(case: LongitudinalCase, result: ReactionResult) -> str:
    """[1.1D1 + 1.2D2 + 1.35(L+I) + 1.0LR + 1.23B + S10 の組合せ], from 0600's factors (07 7-7)."""
    definition, forces = DEFINITIONS[case], result.longitudinal.case(case).origin
    parts = [f"{definition.d1}D1", f"{definition.d2}D2"]
    if forces.live_factor is not None:
        parts.append(f"{printed(forces.live_factor)}(L+I)")
    parts.append(f"{definition.lr_factor}LR")
    if forces.brake_factor is not None:
        parts.append(f"{printed(forces.brake_factor)}B")
    parts.append(SNOW[definition.snow.value])
    return "[" + " + ".join(parts) + " の組合せ]"


def _girder_forces(m: Manuscript, result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> None:
    longitudinal = reaction.longitudinal
    m.heading("girder.heading", "1) 桁に働く水平荷重", ITEM)
    m.heading("girder.rail.heading", "(a) ロングレール縦荷重", DETAIL)
    m.heading("girder.rail.safety.heading", "a) 使用性の照査におけるひび割れの検討の必要性 および 安全性（破壊），復旧性の照査",
              INDENTED)
    m.paragraph("girder.rail.safety.text", f"1 軌道当り {decimal_constant(LONG_RAIL)} kN/m を考える．")
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.rail.safety.{girder.name.lower()}", GIRDER_SIDES[girder], forces.long_rail,
                symbolic=sub("T", "L1" if girder is Girder.ORIGIN else "L2"), wide=True)
    m.heading("girder.rail.service.heading", "b) 使用性の照査", INDENTED)
    m.paragraph("girder.rail.service.text", f"1 軌道当り {decimal_constant(LONG_RAIL_SERVICE)} kN/m を考える．")
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.rail.service.{girder.name.lower()}", GIRDER_SIDES[girder], forces.long_rail_service,
                symbolic=sub("T", "L1" if girder is Girder.ORIGIN else "L2"), wide=True)
    m.heading("girder.brake.heading", "(b) 制動荷重", DETAIL)
    m.paragraph("girder.brake.text", "安全性（破壊）の照査に対して：1軌道当り次式による．")
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.brake.{girder.name.lower()}", GIRDER_SIDES[girder], forces.braking_adopted, symbolic="T",
                wide=True)
    response = result.longitudinal
    m.heading("girder.seismic.heading", "(c) 地震時死荷重", DETAIL)
    m.value("girder.seismic.kh", "最大応答震度", response.kh, symbolic="Kh", wide=True)
    m.paragraph("girder.seismic.kh.source", f"（線路方向 Case{response.adopted.case} {response.adopted.block}）")
    seismic = result.bearing_cases[-1]
    for girder, forces, devices in ((Girder.ORIGIN, longitudinal.origin, seismic.origin),
                                    (Girder.END, longitudinal.end, seismic.end)):
        assert devices.inertia is not None
        m.formula(f"girder.seismic.{girder.name.lower()}", GIRDER_SIDES[girder], "T",
                  (response.kh, "×", forces.seismic_girder), devices.inertia, wide=True)
    m.heading("girder.train.heading", "(d) 地震時列車荷重", DETAIL)
    m.value("girder.train.kh", "設計震度", Printed(float(ADHESION), 3, ""), symbolic="Kh", wide=True)
    for girder, forces in ((Girder.ORIGIN, longitudinal.origin), (Girder.END, longitudinal.end)):
        m.value(f"girder.train.{girder.name.lower()}", GIRDER_SIDES[girder], forces.seismic_train, symbolic="T",
                wide=True)


def _devices(m: Manuscript, key: str, devices: GirderDevices, mu: Printed, seismic: bool) -> None:
    """One girder end of a bearing case (13-16, 13-20): T, Rm, Hbd and Hsd as the sample derives them."""
    girder = devices.girder
    mark = sub("T", MARKS[girder][1])
    m.start(key)
    m.paragraph(f"{key}.label", f"※ {GIRDER_SIDES[girder]}（{BEARINGS[devices.bearing]}支承）", INDENTED, gap=True)
    m.value(f"{key}.applied", mark, devices.applied, medium=True)
    if not seismic:
        m.paragraph(f"{key}.vertical.label", f"{BEARINGS[devices.bearing]}支承に働く鉛直荷重", INDENTED)
        assert devices.vertical is not None
        m.value(f"{key}.vertical", "Rm", devices.vertical, medium=True)
    m.paragraph(f"{key}.rubber.label", "ゴム支承に働く水平荷重", INDENTED)
    if devices.friction is not None and not seismic:
        m.formula(f"{key}.rubber", sub("H", "bd"), "μ・Rm", (mu, "×", devices.vertical), devices.rubber.total,
                  medium=True)
    else:
        m.value(f"{key}.rubber", sub("H", "bd"), devices.rubber.total, medium=True)
    m.paragraph(f"{key}.stopper.label", "ストッパーに働く水平荷重", INDENTED)
    if seismic:
        if devices.bearing is BearingType.MOVABLE:
            m.formula(f"{key}.stopper", sub("H", "sd"), "T / n", (devices.applied, "/", BEARING_LINES),
                      devices.stopper.total, medium=True)
        else:
            m.value(f"{key}.stopper", sub("H", "sd"), devices.stopper.total, symbolic="T", medium=True)
    elif devices.candidate is not None:
        m.formula(f"{key}.candidate", "T − 1/2μ・Rm", None,
                  (devices.applied, "−", FRICTION_SHARE, "×", mu, "×", devices.vertical), devices.candidate,
                  medium=True)
        m.formula(f"{key}.share", "T / n", None, (devices.applied, "/", BEARING_LINES), devices.share, medium=True)
        m.value(f"{key}.stopper", Row("∴ ", sub("H", "sd"), gap=0), devices.stopper.total, medium=True)
    else:
        m.value(f"{key}.stopper", sub("H", "sd"), devices.stopper.total, medium=True)
    m.end()


def _bearing_forces(m: Manuscript, result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> None:
    m.heading("bearing.heading", "2) シューに働く水平荷重", ITEM)
    m.heading("bearing.safety.heading", "(a) 安全性（破壊）", DETAIL)
    for case in result.bearing_cases:
        key = f"bearing.{'seismic' if case.case is None else case.case.name.lower()}"
        if case.case is None:
            m.heading("bearing.seismic.heading", "(b) 地震時慣性力", DETAIL)
        else:
            m.pair(f"{key}.label", f"・{case.label}", combination_text(case.case, reaction), INDENTED, PAIR_SECOND,
                   gap=True)
        for devices, span in ((case.origin, pier.spans.origin), (case.end, pier.spans.end)):
            _devices(m, f"{key}.{devices.girder.name.lower()}", devices, span.mu, case.case is None)


def _summary_table(cases: tuple[BearingCase, ...], girder: Girder, pick, each_label: str) -> TableSpec:  # noqa: ANN001
    rows = [header("荷 重 種 別", "", "桁全体\n(kN)", f"{each_label}\n(kN)")]
    rows[0] = (CellSpec("荷 重 種 別", colspan=2, align="center"), *rows[0][2:])
    safety = [case for case in cases if case.case is not None]
    for index, case in enumerate(safety):
        device: Device = pick(case.origin if girder is Girder.ORIGIN else case.end)
        first = (CellSpec("安全性\n（破壊）", rowspan=len(safety), align="center"),) if index == 0 else ()
        rows.append((*first, CellSpec(case.label, align="left"), *cells(device.total, device.each)))
    seismic = next(case for case in cases if case.case is None)
    device = pick(seismic.origin if girder is Girder.ORIGIN else seismic.end)
    rows.append((CellSpec("地震時", align="center"), CellSpec(EQ_LABEL, align="left"), *cells(device.total, device.each)))
    return TableSpec((60.0, 160.08, 96.0, 96.0), tuple(rows), header_rows=1, row_height=GIRDER_ROW * 2,
                     header_height=GIRDER_ROW * 2, numeric_columns=(2, 3))


def _summaries(m: Manuscript, result: CantileverResult) -> None:
    for key, title, name, each_label in (("rubber", "(c) ゴム支承に働く水平荷重のまとめ", "rubber", "1シュー当り"),
                                          ("stopper", "(d) ストッパーに働く水平荷重のまとめ", "stopper", "1ストッパー当り")):
        m.heading(f"summary.{key}.heading", title, DETAIL)
        for letter, girder in zip("ab", (Girder.ORIGIN, Girder.END)):
            devices: GirderDevices = getattr(result.bearing_cases[0], "origin" if girder is Girder.ORIGIN else "end")
            count: Device = getattr(devices, name)
            m.heading(f"summary.{key}.{girder.name.lower()}.heading",
                      f"{letter}) {GIRDER_SIDES[girder][:2]}桁　　{count.count} 箇所", INDENTED)
            m.table(f"summary.{key}.{girder.name.lower()}.table",
                    _summary_table(result.bearing_cases, girder, lambda d, name=name: getattr(d, name), each_label),
                    SUBSECTION)


def section(m: Manuscript, result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> None:
    m.heading("horizontal.heading", "(2) 水平荷重", SUBSECTION)
    _girder_forces(m, result, reaction, pier)
    _bearing_forces(m, result, reaction, pier)
    _summaries(m, result)

