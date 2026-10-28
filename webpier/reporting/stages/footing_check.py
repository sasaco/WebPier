"""0810 線路方向フーチング照査 (12.2〜12.5) and 0820 直角方向フーチング照査 (12.6〜12.9): フーチングの断面照査 (decision 60,
ADR-0008).

WebPier lays out only the headings and the explanations (the check formulas, their symbols and the flowchart of the
flexural crack check, stages.check_text); each part is followed by Capacita's pages of its section (``stages.insertion``),
cut from Capacita's report by the page ranges it returns: n.a 安全性の照査 1) bending, 2) shear; n.b 耐久性の照査
1) the flexural crack check, 2) the shear crack check, which is not asked of Capacita (面部材のため省略: the
sample's sentence, 12_フーチング.pdf 262, printed after the durability pages); n.c 復旧性（地震時）の照査 1) bending,
2) shear; n.d 最小鉄筋量及び最大鉄筋量 (the row 8 of the long-term Md, decision 73; the heading only), with a, b, c, d
the four section numbers of the ``Chapter`` (12.2〜12.5 for 0810, 12.6〜12.9 for 0820). A footing of one part
(decision 110) has only that part's sections, numbered in turn (``chapters``): with the frame analyses alone 安全性,
耐久性 and the rebar amount (12.2〜12.4, 12.5〜12.7), with the nonlinear ones alone 復旧性（地震時） (12.2, 12.3). The
chapter heading (§12) and 12.1 are 0800's and not printed here.

The explanations keep the structure of 12_フーチング.pdf 254, 256, 257, 259〜261, 263, 265 and 266 as check_text writes them
(decision 48), written for RC標準 R5 as Capacita checks it (decision 73: no clause numbers in the headings, the R5
flexural crack method and flowchart of check_text): the values WebPier writes to the WDJ (γi, γb, k4, ε'csd) and the
水掛かりの程度 of the input are printed from the same result; the values and formulas of RC標準 that only Capacita
evaluates (σsl1 and Wlim by 水掛かりの程度, fvcd, fwcd, βd, βp, βn, z) are not: the inserted result pages show the
values used. The seismic restorability prints the factors of 復旧性（損傷）地震時 (γi 1.0, γb 1.0; the sample 263). Not
reproduced from the sample: its truncated flowchart texts, and the safety factors it copies into the seismic shear
check (265: γi 1.2; ADR-0001).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gridlayoutpdf import Document

from ...calc.column_check import SafetyFactors
from ...calc.footing_check import FootingCheckResult
from ..equations import Definition
from . import insertion
from .check_text import COLON, CRACK_METHOD, CRACK_STRESS, SIGMA_SE, _blocks, ecsd_text, flowchart
from .frame_report import Manuscript, Unit, value
from .insertion import Insertion, documents, render_with_pages

SAFETY, SEISMIC_RESTORABILITY = 5, 7  # the limit state ids of calc.column_check.SAFETY_FACTORS
# 2) せん断ひび割れの検討 is not asked of Capacita (decision 60; the sample 262).
OMISSION = ("本構造物のフーチングは，ディープビーム的な耐荷機構を有する面部材である．このため，せん断補強鋼材の役割が通常の"
            "棒部材と異なり，さらにひび割れ性状も異なると考えられる．したがって，せん断力によって耐久性に問題を生じることは"
            "少ないと考え，検討を省略する．")


# The groups of sections of a footing check, in report order; each has one section number.
SAFETY_GROUP, DURABILITY_GROUP, RESTORABILITY_GROUP, REBAR_AMOUNT_GROUP = "safety", "durability", "restorability", "rebar_amount"
GROUPS = (SAFETY_GROUP, DURABILITY_GROUP, RESTORABILITY_GROUP, REBAR_AMOUNT_GROUP)
# The groups of the part of the nonlinear analyses (decision 110); the others are those of the frame analyses.
SEISMIC_GROUPS = (RESTORABILITY_GROUP,)


@dataclass(frozen=True)
class Chapter:
    """Where a stage's footing check stands: the chapter, the section number of its first group, the prefix of its
    block ids and the groups it has (decision 110: those of the parts the input chooses), numbered in turn."""

    number: int
    first: int
    prefix: str
    groups: tuple[str, ...] = GROUPS

    def section(self, group: str) -> str:
        return f"{self.number}.{self.first + self.groups.index(group)}"


def chapters(frames: bool, seismic: bool) -> tuple[Chapter, Chapter]:
    """The chapters of 0810 and 0820 for the parts made (decision 110): 0820 follows 0810's sections."""
    groups = tuple(group for group in GROUPS if (seismic if group in SEISMIC_GROUPS else frames))
    return Chapter(12, 2, "0810/", groups), Chapter(12, 2 + len(groups), "0820/", groups)


LONGITUDINAL, TRANSVERSE = chapters(True, True)


def _definitions(m: Manuscript, key: str, *items: Definition) -> None:
    m.definitions(key, *items, colon=COLON)


def _factors(check: FootingCheckResult, limit_state: int) -> SafetyFactors:
    return next(factors for factors in check.safety_factors if factors.id == limit_state)


# --- the parts ----------------------------------------------------------------------------------------------------


def _safety_moment(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    factors = _factors(check, SAFETY)
    m.heading("safety.heading", f"{chapter.section(SAFETY_GROUP)} 安全性の照査", 1)
    m.heading("safety.moment.heading", "1) 曲げモーメントと軸方向力に対する照査", 2)
    m.paragraph("safety.moment.lead", "(a) 部材の照査", keep=True)
    m.paragraph("safety.moment.text", "曲げモーメントと軸方向力を受ける部材の照査は，設計曲げモーメントMdを設計応答値，"
                                      "設計曲げ耐力Mudを設計限界値として，次式により行う．")
    m.line("safety.moment.check", "γi・Md / Mud ≦ 1.0")
    _definitions(m, "safety.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                 Definition("Md", "設計曲げモーメント"), Definition("Mud", "設計曲げ耐力（Mud = Mu / γb）"),
                 Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))
    m.paragraph("safety.moment.capacity.lead", "(b) 曲げ耐力の算定", keep=True)
    m.paragraph("safety.moment.capacity.text", "曲げモーメントと軸方向力を受ける部材の曲げ耐力は，断面の圧縮縁でコンクリートの"
                                               "圧縮ひずみが終局ひずみに達するときの曲げモーメントで，圧縮縁に与えるコンクリート"
                                               "の終局ひずみと平面保持の仮定により求める．")


def _shear(m: Manuscript, key: str, factors: SafetyFactors) -> None:
    """2) せん断力に対する照査 of the safety and of the seismic restorability (the sample 256, 257, 265, 266)."""
    gamma_i = value(factors.ri)
    m.heading(f"{key}.heading", "2) せん断力に対する照査", 2)
    m.paragraph(f"{key}.text", "せん断力を受ける部材の照査は，設計せん断力Vdを設計応答値とし，部材ごとにa/dの値により，"
                               "設計せん断耐力Vyd，腹部コンクリートの設計斜め圧縮破壊耐力Vwcdまたは設計せん断圧縮破壊耐力Vdd"
                               "を設計限界値として，次式により行う．")
    m.heading(f"{key}.slender.heading", "(a) a/d ≧ 2.0 の場合", 3)
    m.paragraph(f"{key}.yield.heading", "a) 設計せん断耐力による照査", keep=True)
    m.line(f"{key}.yield.check", "γi・Vd / Vyd ≦ 1.0")
    _definitions(m, f"{key}.yield.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vyd", "棒部材の設計せん断耐力（Vyd = Vcd + Vsd）"),
                 Definition("Vcd", "せん断補強鋼材を用いない棒部材の設計せん断耐力"),
                 Definition("Vsd", "せん断補強鋼材により受け持たれる棒部材の設計せん断耐力"))
    m.paragraph(f"{key}.web.heading", "b) 腹部コンクリートの斜め圧縮破壊耐力による照査", keep=True)
    m.line(f"{key}.web.check", "γi・Vd / Vwcd ≦ 1.0")
    _definitions(m, f"{key}.web.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vwcd", "設計斜め圧縮破壊耐力"))
    m.heading(f"{key}.deep.heading", "(b) a/d ＜ 2.0 の場合", 3)
    m.line(f"{key}.deep.check", "γi・Vd / Vdd ≦ 1.0")
    _definitions(m, f"{key}.deep.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vdd", "設計せん断圧縮破壊耐力"))


def _safety_shear(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    _shear(m, "safety.shear", _factors(check, SAFETY))


def _safety_deep_beam(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    """2) せん断力に対する照査 of the footing of a pile foundation (decision 96): the deep beam checks of the face (Vfdd, lower
    tension) and of the pile position (Vsd, upper tension), whose pages are Capacita's."""
    gamma_i = value(_factors(check, SAFETY).ri)
    m.heading("safety.deep.heading", "2) せん断力に対する照査", 2)
    m.heading("safety.deep.face.heading", "(a) く体前面（下側引張）", 3)
    m.line("safety.deep.face.check", "γi・Vd / Vfdd ≦ 1.0")
    _definitions(m, "safety.deep.face.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vfdd", "設計せん断圧縮破壊耐力"))
    m.heading("safety.deep.pile.heading", "(b) 杭位置（上側引張）", 3)
    m.line("safety.deep.pile.check", "γi・Vd / Vsd ≦ 1.0")
    _definitions(m, "safety.deep.pile.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vsd", "設計引抜きせん断耐力"))


def _durability(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    key = "durability.flexure"
    m.heading("durability.heading", f"{chapter.section(DURABILITY_GROUP)} 耐久性の照査", 1)
    m.paragraph("durability.environment", f"水掛かりの程度は「{check.environment}」とする．")
    m.heading(f"{key}.heading", "1) 曲げモーメントと軸方向力に対する照査", 2)
    m.heading(f"{key}.method.heading", "(a) 曲げひび割れに対する部材の検討方法", 3)
    m.paragraph(f"{key}.method.text", CRACK_METHOD)
    m.figure(f"{key}.flowchart", flowchart(m.prefix + f"{key}.flowchart.figure"))
    m.heading(f"{key}.stress.heading", "(b) 永久作用による引張鉄筋の応力度による検討", 3)
    m.paragraph(f"{key}.stress.text", CRACK_STRESS)
    m.line(f"{key}.stress.check", "σs / σsl1 ≦ 1.0")
    _definitions(m, f"{key}.stress.symbols", Definition("σs", "永久作用による引張鉄筋の設計応力度"),
                 Definition("σsl1", "永久作用による引張鉄筋応力度の制限値"))
    m.heading(f"{key}.width.heading", "(c) 曲げひび割れ幅の検討", 3)
    m.paragraph(f"{key}.width.text", "曲げひび割れの検討は，コンクリート表面の設計曲げひび割れ幅Wdがひび割れ幅の制限値Wlim"
                                     "に対して，次式を満たす方法により行う．")
    m.line(f"{key}.width.check", "Wd / Wlim ≦ 1.0")
    m.line(f"{key}.width.formula", "Wd = 1.1・k1・k2・k3・k4{4c + 0.7(Cs − φ)}(σse / Es + ε'csd)")
    _definitions(m, f"{key}.width.symbols", Definition("Wd", "コンクリート表面の設計曲げひび割れ幅"),
                 Definition("k1", "鋼材の表面形状がひび割れ幅に及ぼす影響を表す係数"),
                 Definition("k2", "コンクリートの品質がひび割れ幅に及ぼす影響を表す係数"),
                 Definition("k3", "引張鋼材の段数の影響を表す係数"),
                 Definition("k4", f"曲げひび割れの変動を考慮する係数(= {value(check.k4)})"),
                 Definition("c", "かぶり"), Definition("Cs", "鋼材の中心間隔"), Definition("φ", "鋼材径"),
                 Definition("ε'csd", ecsd_text(value(check.ecsd))),
                 Definition("σse", SIGMA_SE),
                 Definition("Es", "鋼材のヤング係数"), Definition("Wlim", "ひび割れ幅の制限値"))


def _durability_shear(m: Manuscript) -> None:
    """2) of 耐久性, after its pages: at the head of the part that follows them."""
    m.heading("durability.shear.heading", "2) せん断ひび割れの検討", 2)
    m.paragraph("durability.shear.omitted", OMISSION)


def _restorability_moment(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    factors = _factors(check, SEISMIC_RESTORABILITY)
    m.heading("restorability.heading", f"{chapter.section(RESTORABILITY_GROUP)} 復旧性（地震時）の照査", 1)
    m.heading("restorability.moment.heading", "1) 曲げモーメントと軸方向力に対する照査", 2)
    m.paragraph("restorability.moment.lead", "(a) 部材の照査", keep=True)
    m.paragraph("restorability.moment.text", "曲げモーメントと軸方向力を受ける部材の照査は，設計曲げモーメントMdを設計応答値，"
                                             "設計曲げ降伏耐力Mydを設計限界値として，次式により行う．以上の照査により，性能"
                                             "照査レベル１を満足することを確認する．")
    m.line("restorability.moment.check", "γi・Md / Myd ≦ 1.0")
    _definitions(m, "restorability.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                 Definition("Md", "設計曲げモーメント"), Definition("Myd", "設計曲げ降伏耐力（Myd = My / γb）"),
                 Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))
    m.paragraph("restorability.moment.capacity.lead", "(b) 曲げ耐力の算定", keep=True)
    m.paragraph("restorability.moment.capacity.text", "曲げモーメントと軸方向力を受ける部材の曲げ耐力は，引張鉄筋が降伏する"
                                                      "ときの曲げモーメントで，引張鉄筋重心位置に与える軸方向鉄筋の降伏ひずみ"
                                                      "と平面保持の仮定により求める．")


def _restorability_shear(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    _shear(m, "restorability.shear", _factors(check, SEISMIC_RESTORABILITY))


def _rebar_amount(m: Manuscript, check: FootingCheckResult, chapter: Chapter) -> None:
    m.heading("rebar_amount.heading", f"{chapter.section(REBAR_AMOUNT_GROUP)} 最小鉄筋量及び最大鉄筋量", 1)


_PARTS = {"bending_safety_destruction": _safety_moment, "shear_safety_destruction": _safety_shear,
          "shear_deep_beam_safety_destruction": _safety_deep_beam,
          "bending_durability": _durability, "bending_restorability_eq": _restorability_moment,
          "shear_restorability_eq": _restorability_shear, "bending_rebar_amount": _rebar_amount}


def parts(check: FootingCheckResult, chapter: Chapter) -> tuple[tuple[tuple[Unit, ...], str], ...]:
    """WebPier's manuscript before each of Capacita's sections, with that section's id, in report order."""
    found = []
    previous = None
    for section in check.sections:
        m = Manuscript(chapter.prefix)
        if previous == "bending_durability":
            _durability_shear(m)
        _PARTS[section](m, check, chapter)
        previous = section
        found.append((tuple(m.units), section))
    return tuple(found)


def _insertions(found: Sequence[tuple[tuple[Unit, ...], str]]) -> tuple[Insertion, ...]:
    """Every section's pages are required: a check without pages is a failure of the run, not a skipped check."""
    return tuple(Insertion(section, part[-1].key) for part, section in found)


def build_footing_check(check: FootingCheckResult, chapter: Chapter) -> tuple[Document, ...]:
    """WebPier's documents of 0810 or 0820, one before each of Capacita's sections, without Capacita's pages."""
    found = parts(check, chapter)
    units = tuple(unit for part, _ in found for unit in part)
    return insertion.documents(units, _insertions(found), blocks=_blocks)


def render_footing_check(check: FootingCheckResult, path: str | Path, pages: Mapping[str, bytes],
                         chapter: Chapter) -> Path:
    """The report: each of WebPier's parts, then Capacita's pages of its section (``pages``: the pages of each
    section by its id, cut by ``assembly.page_range``); atomically replaces *path*. WebPier's pages are the same
    bytes for the same input; Capacita's are its own."""
    found = parts(check, chapter)
    units = tuple(unit for part, _ in found for unit in part)
    return render_with_pages(units, _insertions(found), pages, path, blocks=_blocks)


def grid_documents(check: FootingCheckResult, chapter: Chapter) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of Capacita (its grid Excel workbook)."""
    found = parts(check, chapter)
    units = tuple(unit for part, _ in found for unit in part)
    return documents(units, _insertions(found), blocks=_blocks)
