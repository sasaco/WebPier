"""0612 線路方向の基礎の照査 (8.11) and 0622 直角方向の基礎の照査 (9.11) of a pile foundation (decision 89, Example橋脚4
III-3.3).

The section continues the column check of the same direction (n.5 to n.10) as n.11. For a steel pipe pile it first prints the
check of the pile body (SteelDan's values: the resistances of the pipe, and for each pile row the largest bending moment, shear
force and axial compression of its pile with the three checks); for a cast-in-place pile the section of the pile and the
design forces of each pile row, each followed by Capacita's pages of its check (decision 91, with the mechanism of the
column check: ``stages.insertion``); then the checks of the
foundation's stability against the design limits SOIL-JR returned (the table of limits is its .sdr, as it printed them) and
the responses of the frame of 0610 / 0620: the pile head force Vd and the pull-out force Vud per pile, the horizontal
displacement and the rotation of the footing top. The pull-out check is a row of dashes when no pile head is in tension
(the sample omits it). Every number is a Printed value of the calc result (ADR-0003); nothing is calculated here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document

from ...calc.foundation_check import Requirement
from ...calc.pile_body import Case, PileBodyResult, RowBody
from ...calc.pile_cast import CaseForces, Kind, PileCastResult, RowForces
from ...calc.pile_check import Column, Judged, PileCheckResult
from ...calc.pile_joint import PileJointResult, RowJoint, Side
from ...core.printed import Printed
from ..document import blank, report
from ..equations import Definition
from .column_check import OMITTED
from .foundation_check import COLON, Chapter, LONGITUDINAL, TRANSVERSE
from .frame_report import Manuscript, Span, TableSpec, Unit, blocks, semantic_records, value
from .insertion import Insertion, documents, render_with_pages

TABLE_LEFT = 1
WIDTHS = (6, 11, 4, 4, 4)  # the label, the symbol, and 長期支持, 短期支持, 安全性
BLANK = ""
NAMES = {Requirement.LONG_TERM: "長期支持", Requirement.SHORT_TERM: "短期支持", Requirement.SAFETY: "安全性"}
DASH = "－"


def _text(item: Printed | None) -> str:
    return DASH if item is None else value(item)


def _ratio(item: Judged | None) -> str:
    return DASH if item is None else value(item.value)


def _judgement(column: Column) -> str:
    return "ＯＫ" if all(item.ok for item in column.judgements) else "ＮＧ"


def _number(item: int | None) -> str:
    return DASH if item is None else str(item)


Row = tuple[Any, ...]


def _table(result: PileCheckResult) -> TableSpec:
    columns = result.columns
    groups: list[tuple[str, list[tuple[str, Callable[[Column], str]]]]] = [
        ("組合せ", [("Vd の No", lambda column: _number(column.vd_combination)),
                   ("Vud の No", lambda column: _number(column.vud_combination)),
                   ("δd の No", lambda column: _number(column.delta_combination)),
                   ("θd の No", lambda column: _number(column.theta_combination))]),
        ("設計応答値", [("Vd (kN)", lambda column: value(column.vd)), ("Vud (kN)", lambda column: _text(column.vud)),
                       ("δd (mm)", lambda column: value(column.delta)), ("θd (rad)", lambda column: value(column.theta))]),
        ("基準支持力", [("Rk (kN)", lambda column: value(column.limits.rk)), ("pt", lambda column: value(column.limits.pt)),
                       ("fr", lambda column: value(column.limits.fr))]),
        ("設計限界値", [("Rvd (kN)", lambda column: value(column.limits.rvd)),
                       ("Rud (kN)", lambda column: value(column.limits.rud)),
                       ("δLd (mm)", lambda column: value(column.limits.delta)),
                       ("θLd (rad)", lambda column: value(column.limits.theta))]),
        ("構造物係数", [("γi", lambda column: value(column.gamma_i))]),
        ("安全率", [("γi・Vd / Rvd", lambda column: _ratio(column.vertical)),
                   ("γi・Vud / Rud", lambda column: _ratio(column.pull_out)),
                   ("γi・δd / δLd", lambda column: _ratio(column.horizontal)),
                   ("γi・θd / θLd", lambda column: _ratio(column.rotation))]),
    ]
    rows: list[Row] = [(Span(BLANK, colspan=2), *(Span(NAMES[column.requirement], align="center")
                                                  for column in columns))]
    for label, lines in groups:
        for index, (symbol, cell) in enumerate(lines):
            name = (Span(label, rowspan=len(lines)),) if index == 0 else ()
            rows.append((*name, Span(symbol, align="left"), *(Span(cell(column), align="right") for column in columns)))
    rows.append((Span("判　　定", colspan=2), *(Span(_judgement(column)) for column in columns)))
    return TableSpec(WIDTHS, tuple(rows), (1,) * len(rows), header_rows=1, left=TABLE_LEFT)


BODY_WIDTHS = (12, 7, 5)  # the pipe's table: the item, the symbol and the value
BODY_ROW_WIDTHS = (7, 10, 4, 4, 4)  # a pile row's table: the label, the symbol and the three cases
CASE_NAMES = {Case.MOMENT: "Mmax", Case.SHEAR: "Vmax", Case.AXIAL: "Nmax"}


def _resistance_table(body: PileBodyResult) -> TableSpec:
    steel, found = body.steel, body.resistance
    items = [("鋼管の材質", "", steel.grade), ("鋼管外径（腐食代考慮）", "D (mm)", value(steel.diameter)),
             ("鋼管の有効肉厚", "t (mm)", value(steel.thickness)), ("有効断面積", "A (m2)", value(found.area)),
             ("断面2次モーメント", "I (m4)", value(found.inertia)), ("中立軸までの距離", "yt, yc (mm)", value(found.distance)),
             ("引張降伏強度の特性値", "fsyk (N/mm2)", value(steel.fsyk)), ("圧縮降伏強度の特性値", "f'syk (N/mm2)", value(steel.fsyk)),
             ("せん断降伏強度の特性値", "fsvyk (N/mm2)", value(steel.fsvyk)), ("材料係数", "γs", value(body.gamma_s)),
             ("部材係数", "γb", value(body.gamma_b)), ("構造物係数", "γi", value(body.gamma_i)),
             ("設計降伏強度", "fsyd, f'syd (N/mm2)", value(found.fsyd)), ("設計せん断降伏強度", "fsvyd (N/mm2)", value(found.fsvyd)),
             ("設計軸方向引張耐力", "Nud (kN)", value(found.tension)), ("設計軸方向圧縮耐力", "N'u0d (kN)", value(found.compression)),
             ("引張側の設計曲げ耐力", "Mutd (kN・m)", value(found.bending_tension)),
             ("圧縮側の設計曲げ耐力", "Mucd (kN・m)", value(found.bending_compression)),
             ("設計せん断耐力", "Vyd (kN)", value(found.shear))]
    rows = [(Span(label, align="left"), Span(symbol, align="left"), Span(text, align="right")) for label, symbol, text in items]
    return TableSpec(BODY_WIDTHS, tuple(rows), (1,) * len(rows), header_rows=0, left=TABLE_LEFT)

CAST_WIDTHS = (12, 7, 5)  # the pile's table: the item, the symbol and the value
CAST_ROW_ITEMS = (5, 8)  # a pile row's table: the label and the symbol, then the cells left shared by the cases
CAST_KEYS = {"bending_safety_destruction": "cast.bending.heading", "shear_safety_destruction": "cast.shear.heading"}
CAST_HEADINGS = {"bending_safety_destruction": "a) 曲げモーメントと軸方向力に対する照査",
                 "shear_safety_destruction": "b) せん断力に対する照査"}


def _cast_table(cast: PileCastResult) -> TableSpec:
    """The section of the pile as Capacita is given it (mm, N/mm2)."""
    found = cast.section
    _, _, rfck, _, rec, rvcd = cast.pile_factor
    items = [("杭径", "D (mm)", value(found.diameter)), ("コンクリートの設計基準強度", "f'ck (N/mm2)", value(found.fck)),
             ("施工条件", "", found.condition), ("f'ck の低減係数", "", f"{rfck:.2f}"), ("Ec の低減係数", "", f"{rec:.2f}"),
             ("Vcd の低減係数", "", f"{rvcd:.2f}"),
             ("軸方向鉄筋", "", f"D{found.bar_diameter.value:g}-{found.bar_count}本"),
             ("軸方向鉄筋の材質", "", found.bar_steel.grade), ("軸方向鉄筋の断面積", "As (mm2)", value(found.bar_area)),
             ("純かぶり", "(mm)", value(found.cover)), ("主鉄筋の芯かぶり", "(mm)", value(found.centre)),
             ("帯鉄筋", "", f"D{found.hoop_diameter.value:g}"), ("帯鉄筋の材質", "", found.hoop_steel.grade),
             ("帯鉄筋の間隔", "s (mm)", value(found.hoop_pitch))]
    rows = [(Span(label, align="left"), Span(symbol, align="left"), Span(text, align="right"))
            for label, symbol, text in items]
    return TableSpec(CAST_WIDTHS, tuple(rows), (1,) * len(rows), header_rows=0, left=TABLE_LEFT)


def _cast_row_table(row: RowForces, kinds: Sequence[Kind]) -> TableSpec:
    """The design forces of one pile row: a column for each kind of case any row has (a dash where this row has none)."""
    found: Mapping[Kind, CaseForces] = {case.kind: case for case in row.cases}
    lines: list[tuple[str, str, Callable[[CaseForces], str]]] = [
        ("組合せ", "No", lambda case: str(case.combination)),
        ("着目点", "杭頭から (m)", lambda case: value(case.distance)),
        ("設計断面力", "Md (kN・m)", lambda case: value(case.md)),
        ("", "N'd (kN)", lambda case: value(case.nd)),
        ("", "Vd (kN)", lambda case: value(case.vd))]
    rows: list[Row] = [(Span(BLANK, colspan=2), *(Span(kind.value, align="center") for kind in kinds))]
    labels = {"組合せ": 1, "着目点": 1, "設計断面力": 3}
    for label, symbol, cell in lines:
        name = (Span(label, rowspan=labels[label]),) if label else ()
        rows.append((*name, Span(symbol, align="left"),
                     *(Span(cell(found[kind]) if kind in found else DASH, align="right") for kind in kinds)))
    widths = (*CAST_ROW_ITEMS, *((29 - sum(CAST_ROW_ITEMS)) // len(kinds),) * len(kinds))
    return TableSpec(widths, tuple(rows), (1,) * len(rows), header_rows=1, left=TABLE_LEFT)


def _cast(m: Manuscript, cast: PileCastResult) -> None:
    """(1) 杭体の照査（場所打ち杭）: the section and the design forces of each pile row, then the headings after which
    Capacita's pages of the bending and of the shear check go (a check it skipped for zero forces ends with the reason)."""
    m.heading("cast.heading", "(1) 杭体の照査（場所打ち杭）", 2)
    m.paragraph("cast.section.title", "場所打ち杭の諸元", left=TABLE_LEFT, keep=True)
    m.table("cast.section", _cast_table(cast))
    kinds = [kind for kind in Kind if any(case.kind is kind for row in cast.rows for case in row.cases)]
    for row in cast.rows:
        m.paragraph(f"cast.row{row.row}.title", f"杭列 {row.row} の設計断面力（杭1本当り，{row.piles}本）",
                    left=TABLE_LEFT, keep=True)
        m.table(f"cast.row{row.row}", _cast_row_table(row, kinds))
    for section, key in CAST_KEYS.items():
        m.heading(key, CAST_HEADINGS[section], 3)
        if section in cast.skipped:
            m.paragraph(f"{key}.omitted", OMITTED[section])


def _tension(item: Printed) -> str:
    """The ratio of the tension side: a dash when it is not above 0 (the axial force is compression, the check is the other's)."""
    return DASH if item.value <= 0 else value(item)


def _row_table(row: RowBody) -> TableSpec:
    lines: list[tuple[str, str, Callable[[Any], str]]] = [
        ("組合せ", "No", lambda case: str(case.combination)),
        ("着目点", "杭頭から (m)", lambda case: value(case.distance)),
        ("設計断面力", "Md (kN・m)", lambda case: value(case.md)),
        ("", "N'd (kN)", lambda case: value(case.nd)),
        ("", "Vd (kN)", lambda case: value(case.vd)),
        ("照査", "γi・(−N'd / Nud + Md / Mutd)", lambda case: _tension(case.ratio_tension)),
        ("", "γi・(N'd / N'u0d + Md / Mucd)", lambda case: value(case.ratio_compression)),
        ("", "γi・Vd / Vyd", lambda case: value(case.shear)),
        ("", "(γi / 1.1)²・[ ]", lambda case: value(case.combined))]
    rows: list[Row] = [(Span(BLANK, colspan=2), *(Span(CASE_NAMES[case.case], align="center") for case in row.cases))]
    labels = [("組合せ", 1), ("着目点", 1), ("設計断面力", 3), ("照査", 4)]
    for index, (label, symbol, cell) in enumerate(lines):
        name = (Span(label, rowspan=dict(labels)[label]),) if label else ()
        rows.append((*name, Span(symbol, align="left"), *(Span(cell(case), align="right") for case in row.cases)))
    rows.append((Span("判　　定", colspan=2), *(Span("ＯＫ" if all(item.value <= 1.0 for item in (case.bending, case.shear, case.combined))
                                                    else "ＮＧ") for case in row.cases)))
    return TableSpec(BODY_ROW_WIDTHS, tuple(rows), (1,) * len(rows), header_rows=1, left=TABLE_LEFT)


FORCE_WIDTHS = (7, 6, 6, 6, 4)  # the joint's design forces: the member, Md, N'd, the combination and the remark
JOINT_ITEMS = (10, 7)  # the joint's result: the item and the symbol, then a column for each pile row (4 cells, fewer for many rows: the page is 29 cells)


def _in_order(rows: tuple[RowJoint, ...]) -> list[RowJoint]:
    """The sample's order: the push side, the rows between, the pull side."""
    return sorted(rows, key=lambda row: {Side.PUSH: 0, None: 1, Side.PULL: 2}[row.check.side])


def _forces_table(rows: tuple[RowJoint, ...]) -> TableSpec:
    """表 3.2.10: the design forces of one pile in each pile row."""
    head = tuple(Span(text, align="center") for text in ("部　材", "Md (kN・m)", "N'd (kN)", "組合せCase", "備　考"))
    table: list[Row] = [head]
    for row in _in_order(rows):
        side = row.check
        table.append((Span(f"鋼管杭（杭列 {row.row}）", align="left"), Span(value(side.md), align="right"),
                      Span(value(side.nd), align="right"), Span(str(side.combination), align="right"),
                      Span(side.side.value if side.side else BLANK, align="left")))
    return TableSpec(FORCE_WIDTHS, tuple(table), (1,) * len(table), header_rows=1, left=TABLE_LEFT)


def _joint_table(joint: PileJointResult) -> TableSpec:
    """表 3.2.11: the section and the check of the joint, a column for each pile row (headed by the push side or the pull side)."""
    found = joint.section
    ordered = _in_order(joint.rows)
    sides = tuple(row.check for row in ordered)
    names = [Span(row.check.side.value if row.check.side else f"杭列 {row.row}", align="center") for row in ordered]
    both: list[tuple[str, str, Callable[[Any], str]]] = [
        ("鉄筋量", "As (mm2)", lambda side: value(found.bar_area)),
        ("", f"(D{found.bar_diameter.value:g}-{found.bar_count}本)", lambda side: BLANK),
        ("鉄筋重心位置", "dsc (mm)", lambda side: value(found.centroid)),
        ("コンクリートの圧縮強度の特性値", "f'ck (N/mm2)", lambda side: value(found.fck)),
        ("鉄筋の引張降伏強度の特性値", "fsyk (N/mm2)", lambda side: value(found.bar_strength)),
        ("鋼管杭の引張降伏強度の特性値", "f'syk (N/mm2)", lambda side: value(found.pipe_strength)),
        ("材料係数（コンクリート）", "γc", lambda side: value(joint.gamma_c)),
        ("材料係数（鋼材）", "γs", lambda side: value(joint.gamma_s)),
        ("部材係数", "γb", lambda side: value(joint.gamma_b)),
        ("構造物係数", "γi", lambda side: value(joint.gamma_i)),
        ("設計曲げモーメント", "Md (kN・m)", lambda side: value(side.md)),
        ("設計軸方向圧縮力", "N'd (kN)", lambda side: value(side.nd)),
        ("設計曲げ耐力", "Mud (kN・m)", lambda side: value(side.mud)),
        ("照査", "γi・Md / Mud", lambda side: value(side.ratio))]
    rows: list[Row] = [(Span(BLANK, colspan=2), *names),
                       (Span("鋼管外径（腐食代考慮）", align="left"), Span("D (mm)", align="left"),
                        *(Span(value(found.diameter), align="right") for _ in sides)),
                       (Span("鋼管の有効肉厚", align="left"), Span("t (mm)", align="left"),
                        *(Span(value(found.thickness), align="right") for _ in sides)),
                       (Span("（鋼管腐食代）", align="left"), Span("(mm)", align="left"),
                        *(Span(value(found.corrosion), align="right") for _ in sides))]
    rows += [(Span(label, align="left"), Span(symbol, align="left"), *(Span(cell(side), align="right") for side in sides))
             for label, symbol, cell in both]
    rows.append((Span("照査結果", colspan=2), *(Span("ＯＫ" if side.ok else "ＮＧ") for side in sides)))
    return TableSpec((*JOINT_ITEMS, *(min(4, (29 - sum(JOINT_ITEMS)) // len(sides)),) * len(sides)), tuple(rows), (1,) * len(rows), header_rows=1, left=TABLE_LEFT)


def _joint(m: Manuscript, joint: PileJointResult) -> None:
    """(b) 杭とフーチングの結合部 (III-3.2.2 (b)): the text and the formulas are the sample's, the shear check is omitted as it is."""
    m.heading("joint.heading", "(b) 杭とフーチングの結合部", 3, tag="【杭体設計の手引き 2.4】")
    m.paragraph("joint.text1", "杭とフーチングの結合部の破壊の照査は，断面力を照査指標として行う．")
    m.paragraph("joint.text2", "設計限界値として，曲げモーメントに対して設計曲げ耐力Mud，せん断力に対して設計せん断耐力Vydで照査を行う．")
    m.heading("joint.bending", "a) 曲げモーメントに対する照査", 3)
    m.paragraph("joint.forces.title", "(i) 設計断面力", left=TABLE_LEFT, keep=True)
    m.table("joint.forces", _forces_table(joint.rows))
    m.paragraph("joint.forces.note", "※断面力は，杭1本当りを示す．", left=TABLE_LEFT)
    m.paragraph("joint.result", "(ii) 照査結果", left=TABLE_LEFT, keep=True)
    m.paragraph("joint.text3", "設計曲げ耐力Mudの算定には，鋼管による拘束効果を考慮したコンクリートの設計圧縮強度f'cckと終局ひずみε'ccにより算定する．")
    m.line("joint.fcck", "f'cck = f'cd (2.254 √(1 + 7.94 σ'1 / f'ck) − 2・σ'1 / f'ck − 1.254)")
    m.line("joint.fcck.source", "【杭体設計の手引き 解2.4-2】", left=18)
    m.definitions("joint.symbols",
                  Definition("f'cck", "中詰めコンクリートの設計基準強度(N/mm2)"),
                  Definition("f'cd", "中詰めコンクリートの最大圧縮強度(N/mm2)"),
                  Definition("σ'1", "鋼管によるコンクリートの拘束応力度(N/mm2)"),
                  Definition("f'syd", "鋼管の設計降伏強度(N/mm2)"),
                  Definition("t", "鋼管の有効肉厚(mm)（腐食代を考慮する）"),
                  Definition("D", "鋼管外径(mm)（腐食代を考慮する）"), colon=COLON)
    m.line("joint.sigma", "σ'1 = 2・t・f'syd / (D − 2t)")
    m.line("joint.sigma.source", "【杭体設計の手引き 解2.4-3】", left=18)
    m.line("joint.ecc", "ε'cc = 0.002[1 + 5(f'cc / f'cd − 1)]")
    m.line("joint.ecc.source", "【杭体設計の手引き 解2.4-5】", left=18)
    m.paragraph("joint.table.title", "表　杭とフーチングの結合部の安全性の照査結果", left=TABLE_LEFT, keep=True)
    m.table("joint.table", _joint_table(joint))
    m.heading("joint.shear", "b) せん断力に対する照査", 3)
    m.paragraph("joint.shear.text1", "【杭体設計の手引き】に示される仕様を満足する一般的な設計条件（【基礎標準　解説　表 15.1.1-1】）の鋼管杭であれば，"
                "結合部での純せん断による破壊は生じないと考えられることから，仮想RC部材としてのせん断耐力の照査は行わなくて良い．")
    m.paragraph("joint.shear.text2", "本設計計算例の鋼管杭は，周面支持の杭基礎となるので，一般的な設計条件を満足しない特殊な設計条件となるが，"
                "せん断力への影響は少ないことから上記条件と同等と判断し，照査を省略する．")


def _body(m: Manuscript, body: PileBodyResult, *, subheading: bool = False) -> None:
    m.heading("body.heading", "(1) 杭体の照査（鋼管杭）", 2)
    if subheading:
        m.heading("body.sub", "(a) 杭体", 3)
    m.paragraph("body.text", "鋼管杭の杭体の照査においては，杭1本当りの断面力について，次式を満足することを確かめる．")
    m.line("body.bending.tension", "γi・(−N'd / Nud + Md / Mutd) ≦ 1.0")
    m.line("body.bending.compression", "γi・(N'd / N'u0d + Md / Mucd) ≦ 1.0")
    m.line("body.shear", "γi・Vd / Vyd ≦ 1.0")
    m.line("body.combined", "(γi / 1.1)²・[ (N'd / N'u0d + Md / Mucd)² + (Vd / Vyd)² ] ≦ 1.0")
    m.definitions("body.symbols",
                  Definition("N'd", "設計軸方向圧縮力(kN)"), Definition("Md", "設計曲げモーメント(kN・m)"),
                  Definition("Vd", "設計せん断力(kN)"), Definition("Nud", "設計軸方向引張耐力(kN)"),
                  Definition("N'u0d", "設計軸方向圧縮耐力(kN)"), Definition("Mutd", "引張側の設計曲げ耐力(kN・m)"),
                  Definition("Mucd", "圧縮側の設計曲げ耐力(kN・m)"), Definition("Vyd", "設計せん断耐力(kN)"), colon=COLON)
    m.paragraph("body.resistance.title", "鋼管杭の諸元と耐力", left=TABLE_LEFT, keep=True)
    m.table("body.resistance", _resistance_table(body))
    for row in body.rows:
        m.paragraph(f"body.row{row.row}.title", f"杭列 {row.row} の鋼管杭の照査結果（杭1本当り，{row.piles}本）", left=TABLE_LEFT, keep=True)
        m.table(f"body.row{row.row}", _row_table(row))


def content(result: PileCheckResult, chapter: Chapter) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(chapter.prefix)
    m.heading("heading", f"{chapter.number}.11 基礎の照査", 1)
    if result.cast is not None:
        _cast(m, result.cast)
    if result.body is not None:
        _body(m, result.body, subheading=result.joint is not None)
    if result.joint is not None:
        _joint(m, result.joint)
    first = result.body is None and result.cast is None
    m.heading("stability.heading", "(1) 杭基礎の安定に対する検討" if first else "(2) 杭基礎の安定に対する検討", 2)
    m.paragraph("stability.text", "杭基礎の安定に対する検討においては，次式を満足することを確かめる．")
    m.line("vertical", "γi・Vd / Rvd ≦ 1.0")
    m.line("pull_out", "γi・Vud / Rud ≦ 1.0")
    m.line("horizontal", "γi・δd / δLd ≦ 1.0")
    m.line("rotation", "γi・θd / θLd ≦ 1.0")
    m.definitions("symbols",
                  Definition("γi", "構造物係数"),
                  Definition("Vd", "押込み側杭頭部の設計鉛直力(kN)"),
                  Definition("Rvd", "設計鉛直支持力(kN)"),
                  Definition("Vud", "引抜き側杭頭部の設計引抜き力(kN)"),
                  Definition("Rud", "設計引抜き抵抗力(kN)"),
                  Definition("δd", "フーチング天端の最大応答水平変位(mm)"),
                  Definition("δLd", "水平変位の設計限界値(mm)"),
                  Definition("θd", "フーチング天端の最大応答回転角(rad)"),
                  Definition("θLd", "回転角の設計限界値(rad)"), colon=COLON)
    m.paragraph("table.title", "杭基礎の安定に対する検討表（杭1本当り）", left=TABLE_LEFT, keep=True)
    m.table("table", _table(result))
    return tuple(m.units)


def records(result: PileCheckResult, chapter: Chapter) -> list[dict[str, str]]:
    return semantic_records(content(result, chapter))


def _blocks(units: Sequence[Unit]) -> list:
    """The blocks of *units*, a blank line before each "ここに、" list and each run of formula lines."""
    found: list = []
    run: list[Unit] = []
    for unit in units:
        previous = run[-1].kind if run else None
        if run and not run[-1].keep and (unit.kind == "definitions" or unit.kind in ("line", "equation")
                                         and previous not in ("line", "equation")):
            found += blocks(run)
            blank(found)
            run = []
        run.append(unit)
    return [*found, *blocks(run)]


def insertions(result: PileCheckResult, chapter: Chapter) -> tuple[Insertion, ...]:
    """Where Capacita's pages of a cast-in-place pile go: after the heading of each of its two checks (after the reason
    it is omitted, when it skipped one for zero forces); none for a steel pipe pile."""
    if result.cast is None:
        return ()
    return tuple(Insertion(section, f"{chapter.prefix}{key}" + (".omitted" if section in result.cast.skipped else ""),
                           optional=section in result.cast.skipped) for section, key in CAST_KEYS.items())


def build_pile_check(result: PileCheckResult, chapter: Chapter) -> Document:
    return report(*_blocks(content(result, chapter)))


def render_pile_check(result: PileCheckResult, path: str | Path, chapter: Chapter) -> Path:
    """Lay out completely, then atomically replace *path*; the same result gives the same bytes (the report of a
    cast-in-place pile has Capacita's pages as it returned them, which are the program's)."""
    if result.cast is None:
        return build_pile_check(result, chapter).render(path, invariant=True)
    return render_with_pages(content(result, chapter), insertions(result, chapter), result.cast.pages, path, blocks=_blocks)


def grid_documents(result: PileCheckResult, chapter: Chapter) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report, without Capacita's pages."""
    if result.cast is None:
        return (build_pile_check(result, chapter),)
    return documents(content(result, chapter), insertions(result, chapter), blocks=_blocks)


__all__ = ["LONGITUDINAL", "TRANSVERSE", "Chapter", "build_pile_check", "content", "grid_documents", "insertions",
           "records", "render_pile_check"]
