"""0612 線路方向の基礎の照査 (8.10) and 0622 直角方向の基礎の照査 (9.10) (decision 54).

WebPier lays out every page: the check formulas and their symbols, then the table of each check, as Example2 08
pp.8-27 to 8-32 (09 pp.9-24 to 9-29 are the same pages). The section continues the column check of the same direction
(n.5 to n.9, decision 48) as n.10, n = 8 for 0612 and 9 for 0622; the chapter heading is not printed, and the
sample's duplicated "8.7" (and 09's copy of it) is not reproduced. Every number is a Printed value of the calc result
(ADR-0003); nothing is calculated here.

Written differently from the sample (decision 54, ADR-0001): the bearing check names the largest pressure pd1 it uses,
the pressures are in kN/m2, the long term limit of qd is its own row beside the unlimited qd (the sample prints the
limit as qvd), Be has a row, the vertical table has a judgement row like the horizontal one, and the rows of the
cohesive soils (c, Nc, αb, frc) and of the second axis (ey, L′) are not printed (only the sandy equation applies, in
the plane of the frame).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document

from ...calc.foundation_check import (FACTORS, GROUND_KINDS, ROTATION_DIVISOR, Basis, Column, FoundationCheckResult,
                                      Judged, Requirement)
from ...calc.embedment import CoverWeight
from ...core.printed import Printed
from ..equations import Definition, terms
from ..document import blank, report
from .frame_report import Manuscript, Span, TableSpec, Unit, blocks, operand, semantic_records, value

COLON = 211.0  # as the column check (reporting-style.md: the 0500 "ここに、" column)
TABLE_LEFT = 80.16
# The label, the symbol and the four columns (Example2 8-30: 長期支持, 短期支持, 安全性 鉛直力最大 / 曲げ最大).
WIDTHS = (96.0, 163.2, 59.04, 59.04, 59.04, 59.04)
BLANK = ""


@dataclass(frozen=True)
class Chapter:
    """Where a stage's foundation check stands: its section number and the prefix of its block ids."""

    number: int  # n of n.10, continuing the column check of the same direction
    prefix: str


LONGITUDINAL = Chapter(8, "0612/")
TRANSVERSE = Chapter(9, "0622/")


def _definitions(m: Manuscript, key: str, *items: Definition) -> None:
    m.definitions(key, *items, colon=COLON)


def _factor(requirement: Requirement, name: str) -> str:
    return value(getattr(FACTORS[requirement], name))


def _requirements(m: Manuscript, n: int) -> None:
    m.heading("heading", f"{n}.10 基礎の照査", 1)
    m.heading("vertical.heading", "(1) 鉛直支持に対する検討", 2)
    m.paragraph("vertical.text", "鉛直支持に対する検討においては，次式を満足することを確かめる．")
    for requirement, lead, check, items in (
            (Requirement.LONG_TERM, "・長期支持性能および短期支持性能の照査に対して", "γi・γa・pd1 / qd ≦ 1.0",
             (Definition("pd1", "設計最大鉛直地盤反力度(kN/m2)"), Definition("qd", "設計鉛直支持力度(kN/m2)"))),
            (Requirement.SAFETY, "・安全性の照査に対して", "γi・γa・Vd / Rvd ≦ 1.0",
             (Definition("Vd", "設計有効鉛直力(kN)"), Definition("Rvd", "設計鉛直支持力(kN)")))):
        key = f"vertical.{requirement.value}"
        m.paragraph(f"{key}.lead", lead, keep=True)
        m.line(f"{key}.check", check)
        _definitions(m, f"{key}.symbols", *items,
                     Definition("γa", f"構造解析係数(= {_factor(requirement, 'gamma_a')})"),
                     Definition("γi", f"構造物係数(= {_factor(requirement, 'gamma_i')})"))
    m.paragraph("rotation.lead", "・回転に対して", keep=True)
    m.line("rotation.bearing", "長期支持・短期支持　γi・γa・ex / 制限値 ≦ 1.0")
    m.line("rotation.safety", "安全性　γi・γa・Md / Mmd ≦ 1.0")
    _definitions(m, "rotation.symbols",
                 Definition("制限値", f"合力の偏心量の制限値（長期支持 B/{ROTATION_DIVISOR[Requirement.LONG_TERM]}，"
                                   f"短期支持 B/{ROTATION_DIVISOR[Requirement.SHORT_TERM]}）(m)"),
                 Definition("Md", "フーチング底面中心に作用する設計モーメント(kN・m)"),
                 Definition("Mmd", "設計最大モーメント(kN・m)"))
    m.line("rotation.mmd", "Mmd = Vd・B / 2・(1 − Vd / (qd・B・L))")


def _pressure(m: Manuscript, basis: Basis) -> None:
    m.heading("pressure.heading", "1) 設計鉛直地盤反力度", 3)
    m.paragraph("pressure.trapezoid.lead", "ex ≦ B/6 の場合（台形分布）", keep=True)
    m.line("pressure.trapezoid", "pd1, pd2 = Vd / (B・L)・(1 ± 6・ex / B)")
    m.paragraph("pressure.triangle.lead", "ex ＞ B/6 の場合（三角形分布）", keep=True)
    m.line("pressure.triangle", "pd1 = 2・Vd / (3・L・(B / 2 − ex))，pd2 = 0")
    _definitions(m, "pressure.symbols",
                 Definition("pd1", "基礎底面における設計最大鉛直地盤反力度(kN/m2)"),
                 Definition("pd2", "基礎底面における設計最小鉛直地盤反力度(kN/m2)"),
                 Definition("Vd", "基礎底面中心に働く設計有効鉛直荷重(kN)"),
                 Definition("L", f"荷重直角方向のフーチング幅(= {value(basis.l)} m)"),
                 Definition("B", f"荷重作用方向のフーチング幅(= {value(basis.b)} m)"),
                 Definition("ex", "合力の作用点の偏心量（ex = Md / Vd）(m)"))


def _cover(m: Manuscript, key: str, label: str, basis: Basis, cover: CoverWeight) -> None:
    e = basis.embedment
    m.equation(key, label, "γe2", terms("(", operand(cover.wet_segment), "×", value(e.unit_weight_wet), "+",
                                         operand(cover.submerged_segment), "×", value(e.unit_weight_submerged), ")",
                                         "/", value(basis.depth)), cover.unit_weight)


def _capacity(m: Manuscript, basis: Basis) -> None:
    m.heading("capacity.heading", "2) 設計鉛直支持力度", 3)
    m.paragraph("capacity.long.lead", "・長期支持性能の照査に対して", keep=True)
    m.paragraph("capacity.long.text", "長期支持性能の照査では，下表に示す地盤反力度を設計鉛直支持力度の上限値とする．")
    rows = [("地盤の種類", "地盤反力度の上限値(kN/m2)")]
    rows += [(kind.name, f"{value(kind.base)} ＋ γe2・Df" if kind.with_cover else value(kind.base))
             for kind in GROUND_KINDS]
    m.table("capacity.long.table", TableSpec((164.4, 164.4), tuple(rows), (14.28,) * len(rows), left=131.52))
    ground, limit = basis.ground, basis.long_term_limit
    m.paragraph("capacity.long.ground", f"支持層は{basis.soil_type}なので{ground.name}とし，上限値は次のとおりとする"
                                        "（γe2 は平水位の値）．")
    m.equation("capacity.long.limit", "上限値", "qd", terms(value(ground.base), "+", value(basis.normal.unit_weight),
                                                           "×", value(basis.depth)) if ground.with_cover
               else value(ground.base), limit, relation="≦")
    m.paragraph("capacity.all.lead", "・設計鉛直支持力度", keep=True)
    m.paragraph("capacity.all.text", "設計鉛直支持力度 qd は次式により算定する（支持層は砂質土）．")
    m.line("capacity.qd", "qd = qvd + γe2・Df")
    m.line("capacity.qvd", "qvd = frγ・Iγ・βb・Be・γe1・Nγ + frq・Iq・γe2・Df・(Nq − 1)")
    m.line("capacity.inclination", "Iq = (1 − δ / 90)²，Iγ = (1 − δ / φ)²（ただし，0 ≦ 1 − δ / φ），δ = tan⁻¹(Hd / Vd)")
    m.line("capacity.shape", "βb = 0.5 − 0.2・B′ / L（B′ ＞ L ならば L / B′），Be = min(B′, L)，B′ = B − 2・ex")
    factors = "，".join(f"{name} {_factor(requirement, 'f_gamma')}" for requirement, name in (
        (Requirement.LONG_TERM, "長期支持"), (Requirement.SHORT_TERM, "短期支持"), (Requirement.SAFETY, "安全性")))
    _definitions(m, "capacity.symbols",
                 Definition("qd", "設計鉛直支持力度(kN/m2)"),
                 Definition("qvd", "増加荷重に対する直接基礎の設計極限鉛直支持力度(kN/m2)"),
                 Definition("frγ, frq", f"地盤抵抗係数（{factors}）"),
                 Definition("Df", f"フーチング底面の有効根入れ深さ(= {value(basis.depth)} m)"),
                 Definition("γe1", f"フーチング底面の土の有効単位体積重量(= {value(basis.gamma_e1)} kN/m3)"),
                 Definition("γe2", "Df 区間の土の平均有効単位体積重量(kN/m3)"))
    m.paragraph("capacity.gamma_e2.text", "γe2 は，長期支持には平水位，短期支持と安全性には高水位の値を用いる．",
                keep=True)
    _cover(m, "capacity.gamma_e2.normal", "平水位", basis, basis.normal)
    _cover(m, "capacity.gamma_e2.high", "高水位", basis, basis.high)
    _definitions(m, "capacity.factors",
                 Definition("Iγ, Iq", "傾斜荷重に対する補正係数"),
                 Definition("δ", "フーチング底面における合力の傾斜角(度)"),
                 Definition("Hd", "フーチングに作用する設計水平荷重(kN)"),
                 Definition("φ", f"フーチング底面の土の内部摩擦角(= {value(basis.friction_angle)} 度)"),
                 Definition("βb", "フーチング底面の形状係数"),
                 Definition("Be", "B′，L のうち小さいほう(m)"),
                 Definition("B′", "フーチングの有効幅(m)"),
                 Definition("Nγ, Nq", f"フーチング底面の土の支持力係数(= {value(basis.n_gamma)}，"
                                       f"{value(basis.n_q)})"))


def _resistance(m: Manuscript) -> None:
    m.heading("resistance.heading", "3) 設計鉛直支持力", 3)
    m.paragraph("resistance.text", "設計鉛直支持力 Rvd は次式により算定する．")
    m.line("resistance.rvd", "Rvd = A′・qvd + γe2・Df・A′")
    _definitions(m, "resistance.symbols", Definition("Rvd", "直接基礎の設計鉛直支持力(kN)"),
                 Definition("A′", "フーチングの有効面積（A′ = B′・L）(m2)"))


def _text(item: Printed | None) -> str:
    return BLANK if item is None else value(item)


def _ratio(item: Judged | None) -> str:
    if item is None:
        return BLANK
    return "－" if item.value is None else value(item.value)


def _judgement(*items: Judged | None) -> str:
    return "ＯＫ" if all(item.ok for item in items if item is not None) else "ＮＧ"


Row = tuple[Any, ...]


def _header() -> list[Row]:
    return [(Span(BLANK, colspan=2, rowspan=2), Span("長期支持", rowspan=2), Span("短期支持", rowspan=2),
             Span("安全性", colspan=2)), ("鉛直力最大", "曲げ最大")]


def _rows(result: FoundationCheckResult, groups: list[tuple[str, list[tuple[str, Callable[[Column], str]]]]]
          ) -> list[Row]:
    rows = _header()
    for label, lines in groups:
        for index, (symbol, cell) in enumerate(lines):
            name = (Span(label, rowspan=len(lines)),) if index == 0 else ()
            rows.append((*name, Span(symbol, align="left"),
                         *(Span(cell(column), align="right") for column in result.columns)))
    return rows


def _number(name: str) -> Callable[[Column], str]:
    return lambda column: _text(getattr(column, name))


def _vertical_table(result: FoundationCheckResult) -> TableSpec:
    basis = result.basis
    groups: list[tuple[str, list[tuple[str, Callable[[Column], str]]]]] = [
        ("組合せ", [("No", lambda column: str(column.combination))]),
        ("基礎底面中心に\n作用する断面力", [("Vd (kN)", _number("vd")), ("Hd (kN)", _number("hd")),
                                            ("Md (kN・m)", _number("md"))]),
        ("合力の位置", [("ex = Md / Vd (m)", _number("ex"))]),
        ("フーチング形状", [("B (m)", lambda column: value(basis.b)), ("L (m)", lambda column: value(basis.l))]),
        ("有効幅", [("B′ = B − 2・ex (m)", _number("b_effective"))]),
        ("有効面積", [("A′ = B′・L (m2)", _number("area_effective"))]),
        ("有効根入れ", [("Df (m)", lambda column: value(basis.depth))]),
        ("内部摩擦角", [("φ (度)", lambda column: value(basis.friction_angle))]),
        ("荷重傾斜角", [("δ = tan⁻¹(Hd / Vd) (度)", _number("delta"))]),
        ("地盤反力の分布", [("形状", lambda column: "三角形" if column.triangular else "台形"),
                           ("載荷幅 x (m)", _number("width_loaded"))]),
        ("設計地盤反力度", [("pd1 (kN/m2)", _number("pd1")), ("pd2 (kN/m2)", _number("pd2"))]),
        ("土の有効\n単位体積重量", [("γe1 (kN/m3)", lambda column: value(basis.gamma_e1)),
                                    ("γe2 (kN/m3)", _number("gamma_e2"))]),
        ("傾斜荷重\n補正係数", [("Iγ = (1 − δ / φ)²", _number("i_gamma")), ("Iq = (1 − δ / 90)²", _number("i_q"))]),
        ("形状係数", [("βb = 0.5 − 0.2・B′ / L", _number("beta_b"))]),
        ("載荷幅", [("Be (m)", _number("b_e"))]),
        ("支持力係数", [("Nγ", lambda column: value(basis.n_gamma)), ("Nq", lambda column: value(basis.n_q))]),
        ("地盤抵抗係数", [("frγ", lambda column: value(column.factors.f_gamma)),
                         ("frq", lambda column: value(column.factors.f_q))]),
        ("極限支持力度", [("frγ・Iγ・βb・Be・γe1・Nγ", _number("term_gamma")),
                         ("frq・Iq・γe2・Df・(Nq − 1)", _number("term_q")), ("qvd (kN/m2)", _number("qvd"))]),
        ("設計鉛直\n支持力度", [("qvd + γe2・Df (kN/m2)", _number("qd_unlimited")),
                              ("上限値 (kN/m2)", lambda column: (value(basis.long_term_limit)
                                                                if column.requirement is Requirement.LONG_TERM
                                                                else BLANK)),
                              ("qd (kN/m2)", _number("qd"))]),
        ("設計鉛直支持力", [("Rvd (kN)", _number("rvd"))]),
        ("構造物係数", [("γi", lambda column: value(column.factors.gamma_i))]),
        ("構造解析係数", [("γa", lambda column: value(column.factors.gamma_a))]),
        ("安全率", [("γi・γa・pd1 / qd", lambda column: _ratio(column.bearing)),
                   ("γi・γa・Vd / Rvd", lambda column: _ratio(column.vertical))]),
        ("回転安定", [("制限値 (m)", _number("rotation_limit")),
                     ("γi・γa・ex / 制限値", lambda column: _ratio(column.rotation_ex)),
                     ("Mmd (kN・m)", _number("mmd")),
                     ("γi・γa・Md / Mmd", lambda column: _ratio(column.rotation_moment))]),
    ]
    rows = _rows(result, groups)
    rows.append((Span("判　　定", colspan=2), *(Span(_judgement(column.bearing, column.vertical, column.rotation_ex,
                                                                column.rotation_moment)) for column in result.columns)))
    return TableSpec(WIDTHS, tuple(rows), (14.28,) * len(rows), header_rows=2, left=TABLE_LEFT)


def _horizontal(m: Manuscript, result: FoundationCheckResult) -> None:
    basis = result.basis
    m.heading("horizontal.heading", "(2) 水平支持に対する検討", 2)
    m.paragraph("horizontal.text", "水平支持に対する検討においては，次式を満足することを確かめる．")
    m.line("horizontal.check", "γi・Hd / Rhd ≦ 1.0")
    _definitions(m, "horizontal.symbols", Definition("Hd", "設計水平荷重(kN)"), Definition("Rhd", "設計水平支持力(kN)"),
                 Definition("γi", f"構造物係数(= {_factor(Requirement.SAFETY, 'gamma_i_horizontal')})"))
    m.paragraph("horizontal.capacity.text", "設計水平支持力は次式により算定する．支持層は砂質土で，フーチングは現場"
                                            "打ちとし，フーチング前面の設計水平支持力 Rhp は考慮しない．")
    m.line("horizontal.rhd", "Rhd = Rhb")
    m.line("horizontal.rhb", "Rhb = frs・Vd・tanδb")
    _definitions(m, "horizontal.capacity.symbols",
                 Definition("Rhb", "フーチング底面の設計水平支持力(kN)"),
                 Definition("frs", f"直接基礎の水平支持力に対する地盤抵抗係数(= {_factor(Requirement.SAFETY, 'f_s')})"),
                 Definition("Vd", "基礎底面中心に働く設計有効鉛直荷重(kN)"),
                 Definition("δb", "フーチング底面と支持層との摩擦角（δb = φ）(度)"),
                 Definition("φ", f"フーチング底面の土の内部摩擦角(= {value(basis.friction_angle)} 度)"))
    groups: list[tuple[str, list[tuple[str, Callable[[Column], str]]]]] = [
        ("組合せ", [("No", lambda column: str(column.combination))]),
        ("基礎中心の断面力", [("Vd (kN)", _number("vd")), ("Hd (kN)", _number("hd"))]),
        ("内部摩擦角", [("φ (度)", lambda column: value(basis.friction_angle))]),
        ("地盤抵抗係数", [("frs", lambda column: value(column.factors.f_s))]),
        ("設計水平支持力", [("Rhd = frs・Vd・tanδb (kN)", _number("rhb"))]),
        ("構造物係数", [("γi", lambda column: value(column.factors.gamma_i_horizontal))]),
        ("安全率", [("γi・Hd / Rhd", lambda column: _ratio(column.horizontal))]),
    ]
    rows = _rows(result, groups)
    rows.append((Span("判　　定", colspan=2), *(Span(_judgement(column.horizontal)) for column in result.columns)))
    m.paragraph("horizontal.table.title", "水平支持に対する検討表", left=TABLE_LEFT, keep=True)
    m.table("horizontal.table", TableSpec(WIDTHS, tuple(rows), (14.28,) * len(rows), header_rows=2,
                                          left=TABLE_LEFT))


def content(result: FoundationCheckResult, chapter: Chapter) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(chapter.prefix)
    _requirements(m, chapter.number)
    _pressure(m, result.basis)
    _capacity(m, result.basis)
    _resistance(m)
    m.heading("table.heading", "4) 鉛直支持に対する検討", 3)
    m.table("table", _vertical_table(result))
    _horizontal(m, result)
    return tuple(m.units)


def records(result: FoundationCheckResult, chapter: Chapter) -> list[dict[str, str]]:
    return semantic_records(content(result, chapter))


def _blocks(units: tuple[Unit, ...]) -> list:
    """The blocks of *units* with one blank line before a run of formula lines and before each "ここに、" list, as
    the column check (reporting-style.md; Example2 8-27): a kept lead-in stays with its formula."""
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
    return found + blocks(run)


def build_foundation_check(result: FoundationCheckResult, chapter: Chapter) -> Document:
    units = content(result, chapter)
    if len({unit.key for unit in units}) != len(units):
        raise ValueError("帳票の単位に重複したキーがあります")
    return report(*_blocks(units))


def render_foundation_check(result: FoundationCheckResult, path: str | Path, chapter: Chapter) -> Path:
    """Lay out completely, then atomically replace *path*; the same result gives the same bytes."""
    return build_foundation_check(result, chapter).render(path, invariant=True)
