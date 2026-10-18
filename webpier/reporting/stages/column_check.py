"""0611 線路方向の照査 (8.5〜8.9) and 0621 直角方向の照査 (9.5〜9.9): 柱の断面照査 (decision 48, ADR-0008).

WebPier lays out only the headings and the explanations (the check formulas, the symbols and the flowchart of the
flexural crack check). Each part is followed by Capacita's pages of its section (``stages.insertion``), which the
report receives by section id, cut from Capacita's report by the page ranges Capacita returns: n.5 the section force
list, n.6 safety (bending, shear), n.7 durability (flexural, shear cracks), n.8 serviceability (appearance; only
with the appearance check: without it there is no n.8 and n.9 keeps its number), n.9 restorability (bending, shear),
with n the ``Chapter`` of the stage (8 for 0611, 9 for 0621; the two directions differ by nothing else). The chapter
heading (§8, §9) is not printed; the foundation check will be n.10. A check Capacita skipped for zero section forces
(pipeline.capacita.SKIPPED) keeps its heading and explanation, followed by the reason it is omitted instead of
Capacita's pages (decision 48, owner 2026-10-18; Example2 across the track: the serviceability and the shear
durability checks).

The explanations follow Example2 08 pp.8-14, 8-16, 8-18, 8-19, 8-21, 8-23 and 8-25 (09 pp.9-18, 9-20 and 9-22 are the
same text). The values WebPier writes to the WDJ (γi, γb, kr, k4, ε'csd) and the corrosion environment of the input
are printed from the same result; the values of RC標準 that only Capacita holds (σsl1, σsl2 and Wlim by environment,
σbl, the coefficients of k1 to k3 and of z, γb of Vcd here) are not: the inserted result pages show the values used.
Not reproduced from the reference: its truncated flowchart texts (the decision is written σb ≦ σbl), its 1.0 for γi
of 8.9 (1) and 9.9 (1) (the WDJ and the result page have 1.2; ADR-0001), its omission of the restorability shear
check (it is checked; decision 48), and the omission of 9.7 and 9.8 across the track (they are checked, or their
omission is stated).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gridlayoutpdf import Connector, Document, Figure, Label, TextBox, TextDiamond

from ...calc.column_check import ColumnCheckResult, SafetyFactors
from ...inputs import PierInput
from ..document import blank
from ..equations import Definition  # values in the text: (= …), as Example2 8-14
from ..styles import BODY, grid_units
from . import insertion
from .frame_report import FigureSpec, Manuscript, Unit, blocks, value
from .insertion import Insertion, render_with_pages

COLON = 211.0  # the "：" of the 0500 "ここに、" lists (reporting-style.md): room for σwpd and ε'csd


@dataclass(frozen=True)
class Chapter:
    """Where a stage's column check stands in the report: its section numbers and the prefix of its block ids."""

    number: int  # n of n.5 … n.9, continuing the stage's load chapter
    prefix: str


LONGITUDINAL = Chapter(8, "0611/")  # after 0610 (8.1 〜 8.4)
TRANSVERSE = Chapter(9, "0621/")  # after 0620 (9.1 〜 9.4)

# Why a check Capacita skipped for zero section forces is omitted (pipeline.capacita.SKIPPED: RcDan CheckValidation),
# by its section.
OMITTED = {
    "bending_safety_destruction": "曲げモーメントおよび圧縮の軸方向力が生じないため，曲げ耐力の照査を省略する．",
    "shear_safety_destruction": "せん断力が生じないため，せん断に対する照査を省略する．",
    "shear_durability": "永久作用と変動作用によるせん断力が生じないため，せん断ひび割れの検討を省略する．",
    "bending_serviceability": "永久作用による曲げモーメントおよび引張の軸方向力が生じないため，外観に対する曲げひび割れの"
                              "検討を省略する．",
    "bending_restorability": "曲げモーメントが生じないため，曲げ耐力の照査を省略する．",
    "shear_restorability": "せん断力が生じないため，せん断に対する照査を省略する．",
}


def _definitions(m: Manuscript, key: str, *items: Definition) -> None:
    m.definitions(key, *items, colon=COLON)


def _factors(result: ColumnCheckResult, limit_state: int) -> SafetyFactors:
    return next(factors for factors in result.safety if factors.id == limit_state)


# --- the flowchart of the flexural crack check (8.7 (1), 8.8 (1)) ---------------------------------------------------

_WIDTH, _HEIGHT = 432.0, 252.0


def flowchart(key: str) -> FigureSpec:
    """START → σb → σbl → σb ≦ σbl: Yes the steel stress, No the crack width (Example2 8-18 / 8-23, completed)."""
    boxes = (TextBox(110, 2, 80, 24, ("START",), rounded=True, style=BODY),
             TextBox(40, 44, 220, 36, ("全断面を有効として計算したコンクリートの", "縁引張応力度 σb の算定"), style=BODY),
             TextBox(40, 98, 220, 36, ("断面高さに応じた縁引張応力度の", "限界値 σbl の設定"), style=BODY),
             TextDiamond(90, 152, 120, 40, ("σb ≦ σbl",), style=BODY),
             TextBox(40, 214, 220, 36, ("永久作用による引張鉄筋の", "応力度による検討"), style=BODY),
             TextBox(270, 214, 150, 36, ("曲げひび割れ幅による検討", "γi・Wd / Wlim ≦ 1.0"), style=BODY))
    lines = (Connector(((150, 26), (150, 44))), Connector(((150, 80), (150, 98))),
             Connector(((150, 134), (150, 152))), Connector(((150, 192), (150, 214))),
             Connector(((210, 172), (345, 172), (345, 214))),
             Label(156, 206, "Yes", style=BODY), Label(216, 168, "No", style=BODY))
    texts = tuple(line for box in boxes for line in box.lines) + ("Yes", "No")
    return FigureSpec(Figure(grid_units(_WIDTH), grid_units(_HEIGHT), *boxes, *lines, block_id=key), texts,
                      left=117.0)


# --- the parts ----------------------------------------------------------------------------------------------------


def _forces(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    m.heading("forces.heading", f"{n}.5 断面力の総括", 1)


def _safety_moment(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    factors = _factors(result, 5)
    m.heading("safety.heading", f"{n}.6 安全性（破壊）の照査", 1, tag="【ＲＣ標準 7.2.2】")
    m.heading("safety.moment.heading", "(1) 曲げ耐力の算定", 2)
    m.paragraph("safety.moment.text", "曲げモーメントと軸方向力を受ける部材の照査は，設計曲げモーメントMdを設計応答値，"
                                      "設計曲げ耐力Mudを設計限界値として，次式により行う．")
    m.line("safety.moment.check", "γi・Md / Mud ≦ 1.0")
    _definitions(m, "safety.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                  Definition("Md", "設計曲げモーメント"), Definition("Mud", "設計曲げ耐力（Mud = Mu / γb）"),
                  Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))


def _safety_shear(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    gamma_i = value(_factors(result, 5).ri)
    m.heading("safety.shear.heading", "(2) せん断に対する照査", 2, tag="【ＲＣ標準 7.2.3】")
    m.paragraph("safety.shear.text", "せん断力を受ける部材の照査は，設計せん断力Vdを設計応答値とし，部材ごとにa/dの値に"
                                     "より，設計せん断耐力Vyd，腹部コンクリートの設計斜め圧縮破壊耐力Vwcdまたは設計せん断"
                                     "圧縮破壊耐力Vddを設計限界値として，次式により行う．")
    m.heading("safety.shear.slender.heading", "1) a/d ≧ 2.0 の場合", 3)
    m.paragraph("safety.shear.yield.heading", "(a) 設計せん断耐力による照査", keep=True)
    m.line("safety.shear.yield.check", "γi・Vd / Vyd ≦ 1.0")
    _definitions(m, "safety.shear.yield.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                  Definition("Vd", "設計せん断力"),
                  Definition("Vyd", "棒部材の設計せん断耐力（Vyd = Vcd + Vwd + Vsd）"),
                  Definition("Vcd", "せん断補強鋼材を用いない棒部材の設計せん断耐力"),
                  Definition("Vwd", "せん断補強鋼材により受け持たれる棒部材の設計せん断耐力"),
                  Definition("Vsd", "鉄骨部分により受け持たれる棒部材の設計せん断耐力"))
    m.paragraph("safety.shear.web.heading", "(b) 腹部コンクリートの斜め圧縮破壊耐力による照査", keep=True)
    m.line("safety.shear.web.check", "γi・Vd / Vwcd ≦ 1.0")
    _definitions(m, "safety.shear.web.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                  Definition("Vd", "設計せん断力"), Definition("Vwcd", "設計斜め圧縮破壊耐力"))
    m.heading("safety.shear.deep.heading", "2) a/d ＜ 2.0 の場合", 3)
    m.line("safety.shear.deep.check", "γi・Vd / Vdd ≦ 1.0")
    _definitions(m, "safety.shear.deep.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                  Definition("Vd", "設計せん断力"), Definition("Vdd", "設計せん断圧縮破壊耐力"))


def _crack_method(m: Manuscript, key: str) -> None:
    m.heading(f"{key}.method.heading", "1) 曲げひび割れに対する部材の検討方法", 3)
    m.paragraph(f"{key}.method.text", "曲げひび割れに対する部材の検討は，全断面を有効としたコンクリートの縁引張応力度σbが"
                                      "断面高さに応じた縁引張応力度の制限値σbl以下の場合は，永久作用による引張鉄筋の"
                                      "応力度σsによる検討を行い，σbがσblを超える場合は，曲げひび割れ幅Wdによる検討を行う．")
    m.figure(f"{key}.flowchart", flowchart(m.prefix + f"{key}.flowchart.figure"))
    m.heading(f"{key}.stress.heading", "2) 永久作用による引張鉄筋の応力度による検討", 3)
    m.paragraph(f"{key}.stress.text", "永久作用による引張鉄筋の応力度σsが，永久作用による引張鉄筋応力度の制限値σsl1に"
                                      "対し，次式を満たすことを検討する．")
    m.line(f"{key}.stress.check", "σs / σsl1 ≦ 1.0")
    _definitions(m, f"{key}.stress.symbols", Definition("σs", "永久作用による引張鉄筋の設計応力度"),
                  Definition("σsl1", "永久作用による引張鉄筋応力度の制限値"))


def _crack_width(m: Manuscript, key: str, result: ColumnCheckResult, gamma_i: str, limit: str) -> None:
    m.heading(f"{key}.width.heading", "3) 曲げひび割れ幅の検討", 3)
    m.paragraph(f"{key}.width.text", f"曲げひび割れの検討は，コンクリート表面の設計曲げひび割れ幅Wdが{limit}Wlimに"
                                     "対して，次式を満たす方法により行う．")
    m.line(f"{key}.width.check", "γi・Wd / Wlim ≦ 1.0")
    m.line(f"{key}.width.formula", "Wd = 1.1・k1・k2・k3・k4{4c + 0.7(Cs − φ)}(σse / Es + ε'csd)")
    _definitions(m, f"{key}.width.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                  Definition("Wd", "コンクリート表面の設計曲げひび割れ幅"),
                  Definition("k1", "鋼材の表面形状がひび割れ幅に及ぼす影響を表す係数"),
                  Definition("k2", "コンクリートの品質がひび割れ幅に及ぼす影響を表す係数"),
                  Definition("k3", "引張鋼材の段数の影響を表す係数"),
                  Definition("k4", f"曲げひび割れの変動を考慮する係数(= {value(result.k4)})"),
                  Definition("c", "かぶり"), Definition("Cs", "鋼材の中心間隔"), Definition("φ", "鋼材径"),
                  Definition("ε'csd", f"収縮・クリープ等によるひび割れ幅の増加を考慮する数値(= {value(result.ecsd)} ×10⁻⁶)"),
                  Definition("σse", "鋼材位置のコンクリートの応力度が0の状態からの鉄筋応力度の増加量"),
                  Definition("Es", "鋼材のヤング係数"), Definition("Wlim", limit))


def _durability_flexure(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    m.heading("durability.heading", f"{n}.7 耐久性の照査", 1)
    m.paragraph("durability.environment", f"鋼材の腐食に対する環境条件は「{result.environment}」とする．")
    m.heading("durability.flexure.heading", "(1) 曲げひび割れの検討", 2)
    _crack_method(m, "durability.flexure")
    _crack_width(m, "durability.flexure", result, value(_factors(result, 0).ri), "ひび割れ幅の制限値")


def _durability_shear(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    m.heading("durability.shear.heading", "(2) せん断ひび割れの検討", 2)
    m.heading("durability.shear.omit.heading", "1) せん断ひび割れの検討を省略できる部材", 3)
    m.paragraph("durability.shear.omit.text", "永久作用と変動作用が組み合わされたときの設計せん断力Vdが，せん断補強鋼材を"
                                              "用いない棒部材の設計せん断耐力Vcdの70%よりも小さい場合には，せん断ひび割れ"
                                              "の検討を省略する．")
    m.line("durability.shear.omit.below", "Vd ＜ 0.7Vcd の場合　→　以下の検討を省略する．")
    m.line("durability.shear.omit.above", "Vd ≧ 0.7Vcd の場合　→　以下の検討を行う．")
    m.heading("durability.shear.check.heading", "2) せん断ひび割れの検討", 3)
    m.paragraph("durability.shear.check.text", "せん断ひび割れの検討においては，永久作用によるせん断補強鉄筋の応力度σwpd"
                                               "を鉄筋応力度の制限値σsl2以内とすることにより，せん断ひび割れ幅に関する検討"
                                               "を省略する．")
    m.line("durability.shear.check", "σwpd / σsl2 ≦ 1.0")
    m.line("durability.shear.formula", "σwpd = (Vpd + Vrd − kr・Vcd)・s / {Aw・z(cosθ + sinθ)}")
    m.line("durability.shear.formula.ratio", "　　　　× (Vpd + Vcd) / (Vpd + Vrd + Vcd)")
    _definitions(m, "durability.shear.symbols",
                  Definition("σwpd", "永久作用によるせん断補強鉄筋の設計応力度"),
                  Definition("Vpd", "永久作用による設計せん断力"), Definition("Vrd", "変動作用による設計せん断力"),
                  Definition("Vcd", "せん断補強鋼材を用いない棒部材の設計せん断耐力"),
                  Definition("kr", f"変動作用の頻度の影響を考慮するための係数(= {value(result.kr)})"),
                  Definition("s", "せん断補強鉄筋の配置間隔"), Definition("Aw", "区間sにおけるせん断補強鉄筋の総断面積"),
                  Definition("θ", "せん断補強鉄筋が部材軸となす角度"),
                  Definition("z", "圧縮応力の合力の作用位置から引張鋼材の図心までの距離"),
                  Definition("σsl2", "永久作用による鉄筋応力度の制限値"))


def _serviceability(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    m.heading("serviceability.heading", f"{n}.8 使用性の照査", 1)
    m.heading("serviceability.flexure.heading", "(1) 曲げひび割れの検討", 2)
    _crack_method(m, "serviceability.flexure")
    _crack_width(m, "serviceability.flexure", result, value(_factors(result, 0).ri), "外観に対するひび割れ幅の制限値")


def _restorability_moment(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    factors = _factors(result, 6)
    m.heading("restorability.heading", f"{n}.9 復旧性の照査", 1, tag="【ＲＣ標準 9.2】")
    m.heading("restorability.moment.heading", "(1) 曲げ耐力の算定", 2)
    m.paragraph("restorability.moment.text", "曲げモーメントと軸方向力を受ける部材の照査は，設計曲げモーメントMdを設計応答値，"
                                             "設計曲げ降伏耐力Mydを設計限界値として，次式により行う．")
    m.line("restorability.moment.check", "γi・Md / Myd ≦ 1.0")
    _definitions(m, "restorability.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                  Definition("Md", "設計曲げモーメント"), Definition("Myd", "設計曲げ降伏耐力（Myd = My / γb）"),
                  Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))


def _restorability_shear(m: Manuscript, result: ColumnCheckResult, n: int) -> None:
    factors = _factors(result, 6)
    m.heading("restorability.shear.heading", "(2) せん断に対する照査", 2, tag="【ＲＣ標準 9.2】")
    m.paragraph("restorability.shear.text", "せん断力を受ける部材の照査は，設計せん断力Vdを設計応答値，設計せん断耐力Vydを"
                                            "設計限界値として，次式により行う．")
    m.line("restorability.shear.check", "γi・Vd / Vyd ≦ 1.0")
    _definitions(m, "restorability.shear.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                  Definition("Vd", "設計せん断力"), Definition("Vyd", "設計せん断耐力"))


_PARTS = {"section_forces": _forces, "bending_safety_destruction": _safety_moment,
          "shear_safety_destruction": _safety_shear, "bending_durability": _durability_flexure,
          "shear_durability": _durability_shear, "bending_serviceability": _serviceability,
          "bending_restorability": _restorability_moment, "shear_restorability": _restorability_shear}


def parts(result: ColumnCheckResult, chapter: Chapter,
          skipped: Sequence[str] = ()) -> tuple[tuple[tuple[Unit, ...], str], ...]:
    """WebPier's manuscript before each of Capacita's sections, with that section's id, in report order. A section in
    *skipped* (Capacita skipped the check for zero forces) ends with the reason it is omitted, its own group."""
    found = []
    for section in result.sections:
        m = Manuscript(chapter.prefix)
        _PARTS[section](m, result, chapter.number)
        if section in skipped:
            m.paragraph(f"{section}.omitted", OMITTED[section])
        found.append((tuple(m.units), section))
    return tuple(found)


def _blocks(units: Sequence[Unit]) -> list:
    """The blocks of *units* with one blank line around each check formula and each "ここに、" list (a group of their
    own, reporting-style.md; Example2 8-14): the text, the formula lines and the symbols are separate groups. A kept
    lead-in ("(a) 設計せん断耐力による照査") stays with its formula."""
    found: list = []
    run: list[Unit] = []
    for unit in units:
        previous = run[-1].kind if run else None
        if run and not run[-1].keep and (unit.kind == "definitions" or unit.kind == "line" and previous != "line"
                                         or unit.key.endswith(".omitted")):
            found += blocks(run)
            blank(found)
            run = []
        run.append(unit)
    found += blocks(run)
    return found


def build_column_check(result: ColumnCheckResult, chapter: Chapter,
                       skipped: Sequence[str] = ()) -> tuple[Document, ...]:
    """WebPier's documents of 0611 or 0621, one before each of Capacita's sections, without Capacita's pages. A part
    that ends with a heading (n.5) ends with it set as a line in the heading style (``stages.insertion``)."""
    found = parts(result, chapter, skipped)
    units = tuple(unit for part, _ in found for unit in part)
    insertions = tuple(Insertion(section, part[-1].key, optional=True) for part, section in found)
    return insertion.documents(units, insertions, blocks=_blocks)


def render_column_check(result: ColumnCheckResult, pier: PierInput, path: str | Path, pages: Mapping[str, bytes],
                        chapter: Chapter) -> Path:
    """The report: each of WebPier's parts, then Capacita's pages of its section (``pages``: the pages of each
    section by its id, cut by ``assembly.page_range``; a section Capacita skipped for zero forces has none, and its
    part ends with the reason it is omitted); atomically replaces *path*.

    WebPier's pages are the same bytes for the same input; Capacita's are its own (decision 48).
    """
    skipped = tuple(section for section in result.sections if section not in pages and section in OMITTED)
    found = parts(result, chapter, skipped)
    units = tuple(unit for part, _ in found for unit in part)
    insertions = tuple(Insertion(section, part[-1].key, optional=section in OMITTED) for part, section in found)
    return render_with_pages(units, insertions, pages, path, blocks=_blocks)
