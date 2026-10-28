"""0910 片持ち梁の断面照査 (13.3〜13.8, 13.9 with the appearance check): the explanations before Capacita's pages
(decisions 59, 73, ADR-0008).

WebPier lays out only the headings and the explanations (the check formulas, the symbols, the flowchart of the
flexural crack check, the fatigue conditions and the cracking moment with ε'csd). Each part is followed by
Capacita's pages of its section (``stages.insertion``), which the report receives by section id, cut from Capacita's
report by the page ranges Capacita returns: 13.3 安全性（破壊） (bending, shear, torsion), 13.4 安全性（疲労破壊）
(bending, shear), 13.5 耐久性 (flexural cracks with the cracking moment and ε'csd, shear cracks, torsion cracks),
13.6 使用性 (appearance; only with the appearance check: without it there is no 13.6 and the next sections move up,
as the sample), then 使用性（損傷） (the row 6: bending, shear, torsion) and 復旧性（地震時） (the row 7: bending, shear,
torsion) in sections of their own, as RC標準 R5 names them (decision 73; the sample's one 復旧性 section with 地震時以外
and 地震時 is H16's), and 最小鉄筋量及び最大鉄筋量 (the row 8 of the permanent case 28; the heading only). The chapter heading (§13) is not printed. A check Capacita skipped for zero section forces
(pipeline.capacita.SKIPPED) keeps its heading and explanation, followed by the reason it is omitted instead of
Capacita's pages.

The explanations keep the structure of Example2 13 pp.13-38 .. 13-65 (the texts the column check also has use its
wording), written for RC標準 R5 as Capacita checks it (decision 73: no clause numbers in the headings, the R5 flexural
crack method and flowchart of stages.check_text, Vyd = Vcd + Vsd). The values WebPier writes to the WDJ (γi, γb, kr, k4, ε'csd,
the trains of the fatigue check) and the 水掛かりの程度 of each face are printed from the same result; the values of
RC標準 that only Capacita holds are not.
Not reproduced from the reference (decision 59): the train figure, the reaction chart and the numeric ΣN line of
13-46 (an external program's work; Capacita's page shows ΣN), and βnt (Capacita's). The γb 1.3 of its torsion
explanation is now the R5 default the WDJ writes (decision 73).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gridlayoutpdf import Document

from ...calc.cantilever.check import CantileverSectionResult
from ...calc.cantilever.crack import AGES, CrackingMoment
from ...calc.column_check import SafetyFactors
from ...core.printed import Printed
from ...inputs import PierInput
from ...inputs.fields import BEAM_SURFACES
from ..equations import Definition
from . import insertion
from .check_text import (COLON, CONTINUED, CRACK_METHOD, CRACK_STRESS, OMITTED as COLUMN_OMITTED, SIGMA_SE, _blocks,
                         ecsd_text, flowchart, wrap)
from .frame_report import BODY_LEFT, Manuscript, Span, TableSpec, Unit, value
from .insertion import Insertion, documents, render_with_pages

CHAPTER = 13
PREFIX = "0910/"
# Why a check Capacita skipped for zero section forces is omitted (pipeline.capacita.SKIPPED), by its section.
OMITTED = {
    **COLUMN_OMITTED,
    "torsion_safety_destruction": "ねじりモーメントが生じないため，ねじりに対する照査を省略する．",
    "bending_durability": "曲げモーメントが生じないため，曲げひび割れの検討を省略する．",
    "bending_safety_fatigue": "変動作用による曲げモーメントが生じないため，曲げモーメントに対する疲労の照査を省略する．",
    "shear_safety_fatigue": "変動作用によるせん断力が生じないため，せん断に対する疲労の照査を省略する．",
    "torsion_durability": "永久作用と変動作用によるねじりモーメントが生じないため，ねじりひび割れの検討を省略する．",
    "torsion_restorability": "ねじりモーメントが生じないため，ねじりに対する照査を省略する．",
    "bending_restorability_eq": "曲げモーメントが生じないため，曲げ耐力の照査を省略する．",
    "shear_restorability_eq": "せん断力が生じないため，せん断に対する照査を省略する．",
    "torsion_restorability_eq": "ねじりモーメントが生じないため，ねじりに対する照査を省略する．",
}
_SURFACES = {"上面": "上面", "下面": "下面", "側面": "側面"}
MTU_MIN = wrap("設計斜め圧縮破壊耐力（Mtcud）と", "設計ねじり耐力（Mtyd）の小さいほう")


@dataclass(frozen=True)
class Numbering:
    """The section numbers of the stage: 使用性 only with the appearance check (the sample has none)."""

    safety: int = 3
    fatigue: int = 4
    durability: int = 5
    serviceability: int | None = None
    damage: int = 6
    restorability: int = 7
    rebar_amount: int = 8

    @staticmethod
    def of(result: CantileverSectionResult) -> Numbering:
        return Numbering.with_appearance(result.appearance)

    @staticmethod
    def with_appearance(appearance: bool) -> Numbering:
        """The numbers by the appearance check of the input (片持ち梁の照査.外観の照査); 0400 refers to them."""
        if appearance:
            return Numbering(serviceability=6, damage=7, restorability=8, rebar_amount=9)
        return Numbering()


def _definitions(m: Manuscript, key: str, *items: Definition) -> None:
    m.definitions(key, *items, colon=COLON)


def _factors(result: CantileverSectionResult, limit_state: int) -> SafetyFactors:
    return next(factors for factors in result.safety if factors.id == limit_state)


def scientific(number: Printed) -> str:
    """A value kept at three significant figures, written as the sample does (4.43E+12)."""
    return f"{number.value:.2E}"


# --- 13.3 安全性（破壊） --------------------------------------------------------------------------------------------


def _safety_moment(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    factors = _factors(result, 5)
    m.heading("safety.heading", f"{CHAPTER}.{n.safety} 安全性（破壊）の照査", 1)
    m.heading("safety.moment.heading", "(1) 曲げ耐力の算定", 2)
    m.paragraph("safety.moment.text", "曲げモーメントと軸方向力を受ける部材の照査は，設計曲げモーメントMdを設計応答値，"
                                      "設計曲げ耐力Mudを設計限界値として，次式により行う．")
    m.line("safety.moment.check", "γi・Md / Mud ≦ 1.0")
    _definitions(m, "safety.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                 Definition("Md", "設計曲げモーメント"), Definition("Mud", "設計曲げ耐力（Mud = Mu / γb）"),
                 Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))


def _shear_lines(m: Manuscript, key: str, gamma_i: str) -> None:
    """The shear check (a/d ≧ 2.0 and ＜ 2.0), shared by 安全性（破壊）, 使用性（損傷） and 復旧性（地震時）: Capacita checks
    the three alike (RcDan RailR5_Shear_ServiceabilityDamage_Ver and RestorabilityEQ extend SafetyDestruction)."""
    m.paragraph(f"{key}.text", "せん断力を受ける部材の照査は，設計せん断力Vdを設計応答値とし，部材ごとにa/dの値に"
                               "より，設計せん断耐力Vyd，腹部コンクリートの設計斜め圧縮破壊耐力Vwcdまたは設計せん断"
                               "圧縮破壊耐力Vddを設計限界値として，次式により行う．")
    m.heading(f"{key}.slender.heading", "1) a/d ≧ 2.0 の場合", 3)
    m.paragraph(f"{key}.yield.heading", "(a) 設計せん断耐力による照査", keep=True)
    m.line(f"{key}.yield.check", "γi・Vd / Vyd ≦ 1.0")
    _definitions(m, f"{key}.yield.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"),
                 Definition("Vyd", "棒部材の設計せん断耐力（Vyd = Vcd + Vsd）"),
                 Definition("Vcd", "せん断補強鋼材を用いない棒部材の設計せん断耐力"),
                 Definition("Vsd", "せん断補強鋼材により受け持たれる棒部材の設計せん断耐力"))
    m.paragraph(f"{key}.web.heading", "(b) 腹部コンクリートの斜め圧縮破壊耐力による照査", keep=True)
    m.line(f"{key}.web.check", "γi・Vd / Vwcd ≦ 1.0")
    _definitions(m, f"{key}.web.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vwcd", "設計斜め圧縮破壊耐力"))
    m.heading(f"{key}.deep.heading", "2) a/d ＜ 2.0 の場合", 3)
    m.line(f"{key}.deep.check", "γi・Vd / Vdd ≦ 1.0")
    _definitions(m, f"{key}.deep.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vdd", "設計せん断圧縮破壊耐力"))


def _safety_shear(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("safety.shear.heading", "(2) せん断に対する照査", 2)
    _shear_lines(m, "safety.shear", value(_factors(result, 5).ri))


def _torsion_lines(m: Manuscript, key: str, factors: SafetyFactors) -> None:
    """The torsion check (Example2 13-42, 13-43), shared by 安全性（破壊）, 使用性（損傷） and 復旧性（地震時）."""
    gamma_i, gamma_b = value(factors.ri), value(factors.t_rbt)
    m.heading(f"{key}.plain.heading", "a) ねじり補強鉄筋のない場合の設計ねじり耐力", 3)
    m.paragraph(f"{key}.pure.heading", "ア) 設計純ねじり耐力", keep=True)
    m.line(f"{key}.pure.formula", "Mtcd = βnt・Kt・ftd / γb")
    _definitions(m, f"{key}.pure.symbols", Definition("βnt", "軸方向力の影響を表す係数"),
                 Definition("Kt", "Kt = b²・d / {3.1 + 1.8 / (d / b)}"), Definition("ftd", "ftd = 1.25・(f'cd)^(1/2)"),
                 Definition("γb", f"部材係数(= {gamma_b})"))
    m.paragraph(f"{key}.moment.heading", "イ) 設計曲げモーメントが同時に作用する場合の設計ねじり耐力", keep=True)
    m.line(f"{key}.moment.formula", "Mtud1 = Mtcd・{0.2 + 0.8・(1 − γi・Md / Mud)^(1/2)}")
    _definitions(m, f"{key}.moment.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Md", "設計曲げモーメント"), Definition("Mud", "設計曲げ耐力"))
    m.paragraph(f"{key}.shear.heading", "ウ) 設計せん断力が同時に作用する場合の設計ねじり耐力", keep=True)
    m.line(f"{key}.shear.formula", "Mtud2 = Mtcd・(1 − 0.8・γi・Vd / Vud)")
    _definitions(m, f"{key}.shear.symbols", Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vud", "設計せん断耐力"))
    m.heading(f"{key}.reinforced.heading", "b) ねじり補強鉄筋がある場合の設計ねじり耐力", 3)
    m.paragraph(f"{key}.web.heading", "ア) 設計斜め圧縮破壊耐力", keep=True)
    m.line(f"{key}.web.formula", "Mtcud = Kt・fwcd / γb")
    _definitions(m, f"{key}.web.symbols", Definition("fwcd", "fwcd = 1.25・(f'cd)^(1/2)"),
                 Definition("γb", f"部材係数(= {gamma_b})"))
    m.paragraph(f"{key}.yield.heading", "イ) 設計ねじり耐力", keep=True)
    m.line(f"{key}.yield.formula", "Mtyd = 2・Am・(qw・ql)^(1/2) / γb")
    _definitions(m, f"{key}.yield.symbols", Definition("Am", "Am = bo・do"), Definition("qw", "qw = Atw・fwyd / s"),
                 Definition("ql", "ql = ΣAtl・flyd / u"), Definition("γb", f"部材係数(= {gamma_b})"))
    m.paragraph(f"{key}.combined.heading", "ウ) 設計曲げモーメントが同時に作用する場合の設計ねじり耐力", keep=True)
    m.line(f"{key}.combined.case1", "① Mud ≧ M'ud かつ γi・Md ≦ Mud − M'ud の場合　Mtud1 = Mtu.min")
    m.line(f"{key}.combined.case2", "② Mud ≧ M'ud かつ Mud − M'ud ≦ γi・Md ≦ Mud の場合", keep=True)
    m.line(f"{key}.combined.case2.formula",
           "Mtud2 = (Mtu.min − 0.2・Mtcd)・{(Mud − γi・Md) / M'ud}^(1/2) + 0.2・Mtcd", left=BODY_LEFT + 1)
    m.line(f"{key}.combined.case3", "③ Mud ＜ M'ud かつ γi・Md ≦ Mud の場合", keep=True)
    m.line(f"{key}.combined.case3.formula",
           "Mtud3 = (Mtu.min − 0.2・Mtcd)・(1 − γi・Md / Mud)^(1/2) + 0.2・Mtcd", left=BODY_LEFT + 1)
    _definitions(m, f"{key}.combined.symbols",
                 Definition("Mtu.min", MTU_MIN),
                 Definition("Mtcud", "設計斜め圧縮破壊耐力"), Definition("Mtyd", "設計ねじり耐力"),
                 Definition("Mtcd", "設計純ねじり耐力"), Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Md", "設計曲げモーメント"), Definition("Mud", "設計曲げ耐力"))
    m.paragraph(f"{key}.combined.shear.heading", "エ) 設計せん断力が同時に作用する場合の設計ねじり耐力", keep=True)
    m.line(f"{key}.combined.shear.formula", "Mtud = Mtu.min・(1 − γi・Vd / Vud) + 0.2・Mtcd・γi・Vd / Vud")
    _definitions(m, f"{key}.combined.shear.symbols",
                 Definition("Mtu.min", MTU_MIN),
                 Definition("Mtcd", "設計純ねじり耐力"), Definition("γi", f"構造物係数(= {gamma_i})"),
                 Definition("Vd", "設計せん断力"), Definition("Vud", "設計せん断耐力"))


def _safety_torsion(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("safety.torsion.heading", "(3) ねじりモーメントに対する検討", 2)
    _torsion_lines(m, "safety.torsion", _factors(result, 5))


# --- 13.4 安全性（疲労破壊） ----------------------------------------------------------------------------------------


def _trains(m: Manuscript, key: str, title: str, result: CantileverSectionResult) -> None:
    f = result.fatigue
    m.heading(f"{key}.heading", title, 3)
    m.line(f"{key}.passenger", f"A 列車荷重：旅客列車　→　{f.passenger_trains} 本/日")
    m.line(f"{key}.freight", f"B 列車荷重：貨物列車　→　{f.freight_trains} 本/日")


def _fsr200(m: Manuscript, key: str, title: str, result: CantileverSectionResult) -> None:
    gamma_s = value(_factors(result, 2).m_rs)
    m.heading(f"{key}.heading", title, 3)
    m.paragraph(f"{key}.text", "照査断面に配置した鉄筋の200万回強度（N/mm²）を次式により求める．")
    m.line(f"{key}.formula", "fsr200 = γ1・10^αr / (2×10⁶)^k・(1 − σmin / fsuk) / γs")
    _definitions(m, f"{key}.symbols", Definition("αr", "αr = 2.70 − 0.003φ　または　3.09 − 0.003φ"),
                 Definition("k", "k = 0.06　または　0.12"),
                 Definition("σmin", "鉄筋の引張最小応力度（N/mm²）で圧縮を受ける場合は 0 とする"),
                 Definition("fsuk", "鉄筋の引張強度の特性値（N/mm²）"),
                 Definition("γ1", "継手，曲げ加工による低減係数（圧接 0.7，曲げ加工 0.65）"),
                 Definition("γs", f"鉄筋の材料係数(= {gamma_s})"), Definition("φ", "照査の対象とする鉄筋の直径（mm）"))


def _sn_table(m: Manuscript, key: str, title: str) -> None:
    m.heading(f"{key}.heading", title, 3)
    m.paragraph(f"{key}.text", "σsrd と fsr200 の大小関係により，Ｓ－Ｎ線図の係数を下表に従い選択する．")
    rows = ((Span("Ｓ－Ｎ線パラメータ", rowspan=2), Span("異形鉄筋", colspan=2)),
            ("γi・σsrd / (fsr200 / γb) ≦ 1.0", "γi・σsrd / (fsr200 / γb) ＞ 1.0"),
            ("k", "0.06", "0.12"), ("αr", "2.70 − 0.003φ", "3.09 − 0.003φ"))
    m.table(f"{key}.table", TableSpec((6, 11, 11), rows, (1,) * 4, header_rows=2, left=2))


def _repetitions(m: Manuscript, key: str, title: str, result: CantileverSectionResult) -> None:
    f = result.fatigue
    m.heading(f"{key}.heading", title, 3)
    m.paragraph(f"{key}.text", "標準列車荷重換算の総等価繰返し回数 ΣN を次式により算定する．")
    m.line(f"{key}.formula", "ΣN = 365・T・{jA・NA・(SA / SC)^(1/k) + jB・NB・(SB / SC)^(1/k)}")
    _definitions(m, f"{key}.symbols", Definition("T", f"設計耐用年数(= {f.service_life} 年)"),
                 Definition("jA", f"A 列車の 1 線・1 日当りの本数(= {f.passenger_trains} 本/日)"),
                 Definition("jB", f"B 列車の 1 線・1 日当りの本数(= {f.freight_trains} 本/日)"),
                 Definition("NA", "A 列車 1 編成当りの等価繰返し回数（下表）"),
                 Definition("NB", "B 列車 1 編成当りの等価繰返し回数（下表）"),
                 Definition("SA / SC", f"A 列車荷重と標準列車荷重の最大変動断面力比(= {value(f.sa_ratio)})"),
                 Definition("SB / SC", f"B 列車荷重と標準列車荷重の最大変動断面力比(= {value(f.sb_ratio)})"))
    rows = (("1 編成当りの等価繰返し回数", "k = 0.06", "k = 0.12"),
            ("A 列車（NA）", value(f.na06), value(f.na12)), ("B 列車（NB）", value(f.nb06), value(f.nb12)))
    m.table(f"{key}.table", TableSpec((11, 7, 7), rows, (1,) * 3, numeric=frozenset({1, 2})))


def _frd(m: Manuscript, key: str, title: str, result: CantileverSectionResult) -> None:
    gamma_s = value(_factors(result, 2).m_rs)
    m.heading(f"{key}.heading", title, 3)
    m.paragraph(f"{key}.text", "総等価繰返し回数 ΣN を用いて，次式により設計引張疲労強度 frd を求める．")
    m.line(f"{key}.formula", "frd = γ1・γ2・10^αr / N^k・(1 − σmin / fsuk) / γs")
    _definitions(m, f"{key}.symbols", Definition("frd", "鉄筋の設計引張疲労強度（N/mm²）"),
                 Definition("N", "標準列車荷重換算の総等価繰返し回数 ΣN"), Definition("αr, k", "Ｓ－Ｎ線図の係数"),
                 Definition("σmin", "鉄筋の引張最小応力度（N/mm²）で，圧縮を受ける場合は 0 とする"),
                 Definition("fsuk", "鉄筋の引張強度の特性値（N/mm²）"),
                 Definition("γ1", "継手，曲げ加工による低減係数（圧接 0.7，曲げ加工 0.65）"),
                 Definition("γ2", "複線を支持する部材における荷重分担比 a による補正係数"),
                 Definition("a", "（1線載荷による最大断面力）/（複線載荷による最大断面力）"),
                 Definition("γs", f"鉄筋の材料係数(= {gamma_s})"))
    m.line(f"{key}.gamma2", "γ2 = {1 / (a^(1/k) + (1 − a)^(1/k))}^k")


def _fatigue_moment(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    factors = _factors(result, 2)
    m.heading("fatigue.heading", f"{CHAPTER}.{n.fatigue} 安全性（疲労破壊）の照査", 1)
    m.heading("fatigue.moment.heading", "(1) 曲げモーメントに対する照査", 2)
    m.paragraph("fatigue.moment.text", "曲げモーメントを受ける部材の疲労に関する照査は，設計変動応力度σsrdを設計応答値，"
                                       "設計疲労強度frdを部材係数で除した値を設計限界値とし，次式により行う．")
    m.line("fatigue.moment.check", "γi・IRd / ILd ≦ 1.0")
    _definitions(m, "fatigue.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                 Definition("IRd", "設計応答値(= σsrd)"), Definition("ILd", "設計限界値(= frd / γb)"),
                 Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))
    _trains(m, "fatigue.moment.trains", "1) 列車本数", result)
    m.heading("fatigue.moment.stress.heading", "2) 設計変動応力度 σsrd と最小応力度 σmin の算定", 3)
    m.paragraph("fatigue.moment.stress.text", "標準列車荷重による鉄筋の設計変動応力度σsrdおよび最小応力度σminを算定する．"
                                              "鉄筋の最小応力度σminは，鉄筋に生じる最小引張応力度または永久作用による"
                                              "設計応力度で，圧縮が生じる場合には 0 とする．")
    _fsr200(m, "fatigue.moment.fsr200", "3) 200万回引張疲労強度 fsr200 の算定", result)
    _sn_table(m, "fatigue.moment.sn", "4) Ｓ－Ｎ線図の係数の選択")
    _repetitions(m, "fatigue.moment.repetitions", "5) 総等価繰返し回数の算定", result)
    _frd(m, "fatigue.moment.frd", "6) 設計引張疲労強度 frd の算定", result)


def _fatigue_shear(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    factors = _factors(result, 2)
    m.heading("fatigue.shear.heading", "(2) せん断に対する照査", 2)
    m.heading("fatigue.shear.check.heading", "1) 部材の照査", 3)
    m.paragraph("fatigue.shear.check.text", "せん断力を受け，せん断補強鉄筋を用いる部材の疲労に関する照査は，設計変動"
                                            "応力度σwrdを設計応答値，設計疲労強度frdを部材係数で除した値を設計限界値とし，"
                                            "次式により行う．")
    m.line("fatigue.shear.check", "γi・IRd / ILd ≦ 1.0")
    _definitions(m, "fatigue.shear.check.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                 Definition("IRd", "設計応答値(= σwrd)"), Definition("ILd", "設計限界値(= frd / γb)"),
                 Definition("γb", f"部材係数(= {value(factors.v_rbs)})"))
    _trains(m, "fatigue.shear.trains", "2) 列車本数", result)
    m.heading("fatigue.shear.stress.heading", "3) 設計変動応力度 σwrd と最小応力度 σwpd の算定", 3)
    m.paragraph("fatigue.shear.stress.text", "標準列車荷重による鉄筋（スターラップ）の設計変動応力度σwrdおよび最小応力度"
                                             "σwpdを算定する．鉄筋（スターラップ）の最小応力度は，鉄筋（スターラップ）に"
                                             "生じる永久作用による設計応力度σwpdである．なお，σwrdおよびσwpdは，次式により"
                                             "算定する．")
    m.line("fatigue.shear.stress.wrd", "σwrd = (Vpd + Vrd − kr・Vcd)・s / {Aw・z(cosθ + sinθ)}・Vrd / (Vpd + Vrd + Vcd)")
    # Wider than the body: the second factor continues on the next line under the right side.
    m.line("fatigue.shear.stress.wpd", "σwpd = (Vpd + Vrd − kr・Vcd)・s / {Aw・z(cosθ + sinθ)}", keep=True)
    m.line("fatigue.shear.stress.wpd.ratio", "・(Vpd + Vcd) / (Vpd + Vrd + Vcd)", left=CONTINUED)
    _definitions(m, "fatigue.shear.stress.symbols", Definition("Vpd", "永久作用による設計せん断力（N）"),
                 Definition("Vrd", "変動作用による設計せん断力（N）"),
                 Definition("Vcd", wrap("せん断補強鋼材を用いない棒部材の設計せん断耐力", "（γb = 1.3）", mode="forced")),
                 Definition("kr", f"変動作用の頻度の影響を考慮するための係数(= {value(result.kr)})"),
                 Definition("s", "せん断補強鉄筋の配置間隔（mm）"),
                 Definition("Aw", "区間 s におけるせん断補強鉄筋の総断面積（mm²）"),
                 Definition("θ", "せん断補強鉄筋が部材軸となす角度"),
                 Definition("z", wrap("圧縮応力の合力の作用位置から引張鋼材の図心までの距離", "（d/1.15）")),
                 Definition("d", "有効高さ（mm）"))
    m.heading("fatigue.shear.fsr200.heading", "4) 200万回引張疲労強度 fsr200 の算定", 3)
    m.paragraph("fatigue.shear.fsr200.text", "曲げモーメントに対する照査と同様に算定する．")
    m.heading("fatigue.shear.sn.heading", "5) Ｓ－Ｎ線図の係数の選択", 3)
    m.paragraph("fatigue.shear.sn.text", "曲げモーメントに対する照査と同様に算定する．")
    m.heading("fatigue.shear.repetitions.heading", "6) 総等価繰返し回数の算定", 3)
    m.paragraph("fatigue.shear.repetitions.text", "曲げモーメントに対する照査と同様に算定する．")
    m.heading("fatigue.shear.frd.heading", "7) 設計引張疲労強度 frd の算定", 3)
    m.paragraph("fatigue.shear.frd.text", "総等価繰返し回数 ΣN を用いて，設計引張疲労強度 frd を求める．また，算定方法は，"
                                          "曲げモーメントに対する照査と同様である．")


# --- 13.5 耐久性 --------------------------------------------------------------------------------------------------


def _crack_method(m: Manuscript, key: str) -> None:
    m.heading(f"{key}.method.heading", "1) 曲げひび割れに対する部材の検討方法", 3)
    m.paragraph(f"{key}.method.text", CRACK_METHOD)
    m.figure(f"{key}.flowchart", flowchart(m.prefix + f"{key}.flowchart.figure"))
    m.heading(f"{key}.stress.heading", "2) 永久作用による引張鉄筋の応力度による検討", 3)
    m.paragraph(f"{key}.stress.text", CRACK_STRESS)
    m.line(f"{key}.stress.check", "σs / σsl1 ≦ 1.0")
    _definitions(m, f"{key}.stress.symbols", Definition("σs", "永久作用による引張鉄筋の設計応力度"),
                 Definition("σsl1", "永久作用による引張鉄筋応力度の制限値"))


def _crack_width(m: Manuscript, key: str, result: CantileverSectionResult, limit: str) -> None:
    m.heading(f"{key}.width.heading", "3) 曲げひび割れ幅の検討", 3)
    m.paragraph(f"{key}.width.text", f"曲げひび割れの検討は，コンクリート表面の設計曲げひび割れ幅Wdが{limit}Wlimに"
                                     "対して，次式を満たす方法により行う．")
    m.line(f"{key}.width.check", "Wd / Wlim ≦ 1.0")
    m.line(f"{key}.width.formula", "Wd = 1.1・k1・k2・k3・k4{4c + 0.7(Cs − φ)}(σse / Es + ε'csd)")
    _definitions(m, f"{key}.width.symbols", Definition("Wd", "コンクリート表面の設計曲げひび割れ幅"),
                 Definition("k1", "鋼材の表面形状がひび割れ幅に及ぼす影響を表す係数"),
                 Definition("k2", "コンクリートの品質がひび割れ幅に及ぼす影響を表す係数"),
                 Definition("k3", "引張鋼材の段数の影響を表す係数"),
                 Definition("k4", f"曲げひび割れの変動を考慮する係数(= {value(result.k4)})"),
                 Definition("c", "かぶり"), Definition("Cs", "鋼材の中心間隔"), Definition("φ", "鋼材径"),
                 Definition("ε'csd", ecsd_text(value(result.ecsd))),
                 Definition("σse", SIGMA_SE),
                 Definition("Es", "鋼材のヤング係数"), Definition("Wlim", limit))


def _cracking_moment(m: Manuscript, key: str, cm: CrackingMoment) -> None:
    """(a) 設計曲げひび割れ耐力 Mcrd (Example2 13-54), in the values of the result."""
    m.paragraph(f"{key}.heading", "(a) 設計曲げひび割れ耐力 Mcrd", keep=True)
    m.line(f"{key}.formula", "Mcrd = σcrd・I / y + N'd・I / (A・y)")
    _definitions(m, f"{key}.symbols", Definition("I", "断面二次モーメント"), Definition("y", "中立軸の高さ"),
                 Definition("σcrd", "設計曲げひび割れ強度（σcrd = fbck = kob・k1b・ftk）"),
                 Definition("N'd", "設計軸方向圧縮力"), Definition("A", "断面積"))
    m.line(f"{key}.inertia", f"I = b・h³ / 12 = {value(cm.width)} × {value(cm.depth)}³ / 12 = "
                             f"{scientific(cm.inertia)} mm⁴")
    m.line(f"{key}.axis", f"y = h / 2 = {value(cm.neutral_axis)} mm")
    m.line(f"{key}.area", f"A = b・h = {value(cm.width)} × {value(cm.depth)} = {scientific(cm.area)} mm²")
    m.line(f"{key}.axial", f"N'd = {value(cm.axial)} kN")
    m.line(f"{key}.ftk", f"ftk = 0.23 f'ck^(2/3) = 0.23 × {value(cm.strength)}^(2/3) = {value(cm.tensile_strength)} N/mm²")
    # Wider than the body: the values continue on the next line, their "=" under the formula's.
    m.line(f"{key}.gf", "GF = 1/100・dmax^(1/3)・f'ck^(1/3)", keep=True)
    m.line(f"{key}.gf.values", f"= 1/100 × {value(cm.aggregate_max)}^(1/3) × {value(cm.strength)}^(1/3) = "
                               f"{value(cm.fracture_energy)} N/mm", left=BODY_LEFT + 1)
    m.line(f"{key}.ec", f"Ec = {value(cm.modulus)} kN/mm²")
    m.line(f"{key}.lch", f"lch = 1000 GF Ec / ftk² = 1000 × {value(cm.fracture_energy)} × {value(cm.modulus)} / "
                         f"{value(cm.tensile_strength)}² = {value(cm.characteristic_length)} mm")
    m.line(f"{key}.kob", f"kob = 1 + 1 / {{0.85 + 4.5 (h / lch)}} = 1 + 1 / {{0.85 + 4.5 × {value(cm.depth)} / "
                         f"{value(cm.characteristic_length)}}} = {value(cm.kob)}")
    m.line(f"{key}.k1b", f"k1b = {value(cm.k1b)}")
    m.line(f"{key}.crack_stress", f"∴ σcrd = {value(cm.kob)} × {value(cm.k1b)} × {value(cm.tensile_strength)} = "
                                   f"{value(cm.crack_stress)} N/mm²")
    m.line(f"{key}.result", f"∴ Mcrd = {value(cm.crack_stress)} × {scientific(cm.inertia)} / {value(cm.neutral_axis)}"
                            f" + {value(cm.axial)} × 10³ × {scientific(cm.inertia)} / ({scientific(cm.area)} × "
                            f"{value(cm.neutral_axis)})")
    m.line(f"{key}.result.value", f"= {value(cm.moment)} kN・m", left=BODY_LEFT + 2)


def _ecsd(m: Manuscript, key: str, result: CantileverSectionResult) -> None:
    """(b) the self-weight moment and (c) ε'csd (Example2 13-55)."""
    cracking = result.cracking
    moment = value(cracking.cracking_moment.moment)
    m.paragraph(f"{key}.self_weight.heading", "(b) 部材自重による曲げモーメント", keep=True)
    m.line(f"{key}.self_weight.value", f"Md = {value(cracking.self_weight)} kN・m")
    m.paragraph(f"{key}.ecsd.heading", "(c) ε'csd の設定", keep=True)
    m.paragraph(f"{key}.ecsd.text", "曲げひび割れ幅の検討に用いるε'csdについて次表に示される中から適切なものを設定する．")
    ages = (("ひび割れ発生材齢", "ε'csd (×10⁻⁶)", "備考"),
            *((age, str(ecsd), f"{action}により曲げひび割れが発生する場合") for action, ecsd, age in AGES))
    # The remark takes 18 columns on one line, so the table spans the body from column 0.
    m.table(f"{key}.ecsd.ages", TableSpec((6, 6, 18), ages, (1,) * 4, numeric=frozenset({1}), left=0))
    m.paragraph(f"{key}.ecsd.compare", "曲げひび割れモーメントを計算し，設計作用と比較することにより，ε'csdを設定する．")
    compared = (cracking.self_weight, cracking.permanent, cracking.permanent_variable)
    rows = (("作用", "Md (kN・m)", "", "Mcrd (kN・m)"),
            *((action, value(md), "＜" if abs(md.value) < cracking.cracking_moment.moment.value else "≧", moment)
              for (action, _, _), md in zip(AGES, compared)))
    m.table(f"{key}.ecsd.table", TableSpec((11, 6, 2, 6), rows, (1,) * 4, numeric=frozenset({1, 3})))
    m.paragraph(f"{key}.ecsd.result", f"よって，ε'csd = {value(cracking.ecsd)} ×10⁻⁶ をひび割れの照査に用いる"
                                      f"（ひび割れ発生材齢 {cracking.age}）．")


def _durability_flexure(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("durability.heading", f"{CHAPTER}.{n.durability} 耐久性の照査", 1)
    faces = "，".join(f"{face}「{result.environments[face]}」" for face in BEAM_SURFACES)
    m.paragraph("durability.environment", f"水掛かりの程度は，{faces}とする．")
    m.heading("durability.flexure.heading", "(1) 曲げひび割れの検討", 2)
    _crack_method(m, "durability.flexure")
    _crack_width(m, "durability.flexure", result, "ひび割れ幅の制限値")
    _cracking_moment(m, "durability.flexure.mcrd", result.cracking.cracking_moment)
    _ecsd(m, "durability.flexure", result)


def _durability_shear(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
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


def _durability_torsion(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("durability.torsion.heading", "(3) ねじりひび割れの検討", 2)


def _serviceability(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("serviceability.heading", f"{CHAPTER}.{n.serviceability} 使用性の照査", 1)
    m.heading("serviceability.flexure.heading", "(1) 曲げひび割れの検討", 2)
    _crack_method(m, "serviceability.flexure")
    _crack_width(m, "serviceability.flexure", result, "外観に対するひび割れ幅の制限値")


# --- 使用性（損傷），復旧性（地震時） ----------------------------------------------------------------------------------


def _yield_moment(m: Manuscript, key: str, factors: SafetyFactors) -> None:
    m.heading(f"{key}.moment.heading", "(1) 曲げ耐力の算定", 2)
    m.paragraph(f"{key}.moment.text", "曲げモーメントと軸方向力を受ける部材の照査は，設計曲げモーメントMdを設計応答値，"
                                      "設計曲げ降伏耐力Mydを設計限界値として，次式により行う．")
    m.line(f"{key}.moment.check", "γi・Md / Myd ≦ 1.0")
    _definitions(m, f"{key}.moment.symbols", Definition("γi", f"構造物係数(= {value(factors.ri)})"),
                 Definition("Md", "設計曲げモーメント"), Definition("Myd", "設計曲げ降伏耐力（Myd = My / γb）"),
                 Definition("γb", f"部材係数(= {value(factors.m_rbs)})"))


def _damage(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("damage.heading", f"{CHAPTER}.{n.damage} 使用性（損傷）の照査", 1)
    _yield_moment(m, "damage", _factors(result, 6))


def _damage_shear(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("damage.shear.heading", "(2) せん断に対する照査", 2)
    _shear_lines(m, "damage.shear", value(_factors(result, 6).ri))


def _damage_torsion(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("damage.torsion.heading", "(3) ねじりモーメントに対する検討", 2)
    _torsion_lines(m, "damage.torsion", _factors(result, 6))


def _restorability_eq(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("restorability.heading", f"{CHAPTER}.{n.restorability} 復旧性（地震時）の照査", 1)
    _yield_moment(m, "restorability", _factors(result, 7))


def _restorability_eq_shear(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("restorability.shear.heading", "(2) せん断に対する照査", 2)
    _shear_lines(m, "restorability.shear", value(_factors(result, 7).ri))


def _restorability_eq_torsion(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("restorability.torsion.heading", "(3) ねじりモーメントに対する検討", 2)
    _torsion_lines(m, "restorability.torsion", _factors(result, 7))


def _rebar_amount(m: Manuscript, result: CantileverSectionResult, n: Numbering) -> None:
    m.heading("rebar_amount.heading", f"{CHAPTER}.{n.rebar_amount} 最小鉄筋量及び最大鉄筋量", 1)


_PARTS = {"bending_safety_destruction": _safety_moment, "shear_safety_destruction": _safety_shear,
          "torsion_safety_destruction": _safety_torsion, "bending_safety_fatigue": _fatigue_moment,
          "shear_safety_fatigue": _fatigue_shear, "bending_durability": _durability_flexure,
          "shear_durability": _durability_shear, "torsion_durability": _durability_torsion,
          "bending_serviceability": _serviceability, "bending_restorability": _damage,
          "shear_restorability": _damage_shear, "torsion_restorability": _damage_torsion,
          "bending_restorability_eq": _restorability_eq, "shear_restorability_eq": _restorability_eq_shear,
          "torsion_restorability_eq": _restorability_eq_torsion, "bending_rebar_amount": _rebar_amount}


def parts(result: CantileverSectionResult, skipped: Sequence[str] = ()) -> tuple[tuple[tuple[Unit, ...], str], ...]:
    """WebPier's manuscript before each of Capacita's sections, with that section's id, in report order. A section in
    *skipped* (Capacita skipped the check for zero forces) ends with the reason it is omitted, its own group."""
    numbering = Numbering.of(result)
    found = []
    for section in result.sections:
        m = Manuscript(PREFIX)
        _PARTS[section](m, result, numbering)
        if section in skipped:
            m.paragraph(f"{section}.omitted", OMITTED[section])
        found.append((tuple(m.units), section))
    return tuple(found)


def build_cantilever_check(result: CantileverSectionResult, skipped: Sequence[str] = ()) -> tuple[Document, ...]:
    """WebPier's documents of 0910, one before each of Capacita's sections, without Capacita's pages. A part that
    ends with a heading (ねじりひび割れの検討) ends with it set as a line in the heading style (``stages.insertion``)."""
    found = parts(result, skipped)
    units = tuple(unit for part, _ in found for unit in part)
    insertions = tuple(Insertion(section, part[-1].key, optional=True) for part, section in found)
    return insertion.documents(units, insertions, blocks=_blocks)


def render_cantilever_check(result: CantileverSectionResult, pier: PierInput, path: str | Path,
                            pages: Mapping[str, bytes]) -> Path:
    """The report: each of WebPier's parts, then Capacita's pages of its section (``pages``: the pages of each
    section by its id, cut by ``assembly.page_range``; a section Capacita skipped for zero forces has none, and its
    part ends with the reason it is omitted); atomically replaces *path*.

    WebPier's pages are the same bytes for the same input; Capacita's are its own (decision 59).
    """
    units, insertions = _manuscript(result, pages)
    return render_with_pages(units, insertions, pages, path, blocks=_blocks)


def _manuscript(result: CantileverSectionResult,
                pages: Mapping[str, bytes]) -> tuple[tuple[Unit, ...], tuple[Insertion, ...]]:
    """The units of the report and where Capacita's *pages* go; a section without pages ends with the reason it is
    omitted. The report and its grid Excel workbook are laid out from the same."""
    skipped = tuple(section for section in result.sections if section not in pages)
    found = parts(result, skipped)
    units = tuple(unit for part, _ in found for unit in part)
    insertions = tuple(Insertion(section, part[-1].key, optional=True) for part, section in found)
    return units, insertions


def grid_documents(result: CantileverSectionResult, pier: PierInput,
                   pages: Mapping[str, bytes]) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of Capacita (its grid Excel workbook)."""
    return documents(*_manuscript(result, pages), blocks=_blocks)
