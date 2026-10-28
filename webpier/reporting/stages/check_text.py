"""The text WebPier lays out before Capacita's pages of the RC section checks it explains itself: the footing (0810,
0820), the cantilever (0910) and the pile body of a cast-in-place pile (0612, 0622).

The column check of 0611 and 0621 explained its sections with the same text until Capacita printed its own commentary
(decision 121); the pieces they share stayed here: the column of the "：" of the "ここに、" lists, the formula line
under a wider one, the breakable texts, the method and the flowchart of the flexural crack check of RC標準 R5 as
Capacita checks it (decision 73), the reasons a check Capacita skipped for zero section forces is omitted, and the
blank lines around the formulas and the lists.
"""

from __future__ import annotations

from collections.abc import Sequence

from gridlayoutpdf import BreakHint, Connector, Figure, Label, Row, TextBox, TextDiamond

from ..document import blank
from ..styles import BODY, columns_for, rows_for
from .frame_report import BODY_LEFT, FigureSpec, Unit, blocks

COLON = 10  # the "：" column of the "ここに、" lists: room for "ここに、" and the widest symbol (ε'csd, Mtu.min)
CONTINUED = BODY_LEFT + 3  # the continuation of a formula line wider than the body: under its right side

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


def wrap(*pieces: str, mode: str = "allowed") -> Row:
    """A "ここに、" text too long for the body: it may break between *pieces*, the next line under the text. With
    *mode* "forced" it always breaks there (a text that fits the PDF line but not Excel's wider print of it)."""
    found: list = []
    for piece in pieces:
        found += [BreakHint(mode), piece] if found else [piece]
    return Row(*found, gap=0)


def ecsd_text(ecsd: str) -> Row:
    return wrap("収縮・クリープ等によるひび割れ幅の増加を考慮する数値", f"(= {ecsd} ×10⁻⁶)")


SIGMA_SE = wrap("鋼材位置のコンクリートの応力度が0の状態からの", "鉄筋応力度の増加量")


# --- the flowchart of the flexural crack check ---------------------------------------------------------------------

_WIDTH, _HEIGHT = 390.0, 314.0  # 25 × 21 grid cells: from the body column to column 29
FLOWCHART_LEFT = 4
# 1) 曲げひび割れに対する部材の検討方法 in R5 (RcDan CalcResult_BendingCrack Analyze_WdOmit.Verify, decision 73).
CRACK_METHOD = ("曲げひび割れに対する部材の検討は，全断面を有効としたコンクリートの縁引張応力度σbが断面高さに応じた縁引張"
                "応力度の制限値σbl以下で，かつ永久作用による引張鉄筋の応力度σsが永久作用による引張鉄筋応力度の制限値σsl1"
                "以下の場合は，曲げひび割れ幅の検討を省略し，それ以外の場合は，曲げひび割れ幅Wdによる検討を行う．")
CRACK_STRESS = ("永久作用による引張鉄筋の応力度σsが，永久作用による引張鉄筋応力度の制限値σsl1に対し，次式を満たすことを"
                "検討する．")


def flowchart(key: str) -> FigureSpec:
    """START → σb → σbl → σb ≦ σbl: Yes σs ≦ σsl1, whose Yes omits the crack width; either No the crack width (RC標準
    R5 as Capacita checks it; the structure of Example2 8-18 / 8-23)."""
    boxes = (TextBox(80, 2, 80, 24, ("START",), rounded=True, style=BODY),
             TextBox(10, 44, 220, 36, ("全断面を有効として計算したコンクリートの", "縁引張応力度 σb の算定"), style=BODY),
             TextBox(10, 98, 220, 36, ("断面高さに応じた縁引張応力度の", "限界値 σbl の設定"), style=BODY),
             TextDiamond(60, 152, 120, 40, ("σb ≦ σbl",), style=BODY),
             TextDiamond(60, 214, 120, 40, ("σs ≦ σsl1",), style=BODY),
             TextBox(10, 276, 220, 36, ("曲げひび割れ幅の検討を省略",), style=BODY),
             TextBox(240, 216, 150, 36, ("曲げひび割れ幅による検討", "Wd / Wlim ≦ 1.0"), style=BODY))
    lines = (Connector(((120, 26), (120, 44))), Connector(((120, 80), (120, 98))),
             Connector(((120, 134), (120, 152))), Connector(((120, 192), (120, 214))),
             Connector(((120, 254), (120, 276))),
             Connector(((180, 172), (315, 172), (315, 216))), Connector(((180, 234), (240, 234))),
             Label(126, 206, "Yes", style=BODY), Label(186, 168, "No", style=BODY),
             Label(126, 268, "Yes", style=BODY), Label(186, 230, "No", style=BODY))
    texts = tuple(line for box in boxes for line in box.lines) + ("Yes", "No", "Yes", "No")
    return FigureSpec(Figure(columns_for(_WIDTH), rows_for(_HEIGHT), *boxes, *lines, block_id=key), texts,
                      left=FLOWCHART_LEFT)


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
