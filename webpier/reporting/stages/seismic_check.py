"""0711 線路方向・0721 線路直角方向の耐震性能照査: Aggre-SE's report is the whole report (decision 56, ADR-0009).

WebPier draws nothing: no heading, no section number (Example2's 10.5 応答値の算定 and 10.6 応答値一覧表 were written
onto Aggre-SE's pages by hand), no page is chosen, reordered or turned. The report is the bytes of the ``report.pdf``
the Aggre-SE runner returned (pipeline.aggrese), which the report receives as ``SEISMIC_CHECK``. A pile foundation on G3〜G5
(decision 97) has WebPier's pages of the 応答変位法 before it (``render_pile_seismic_check``), Aggre-SE's report then as it is;
they have no grid Excel workbook (its role, 0711.xlsx, is the one of Aggre-SE's summary workbook). A 場所打ち杭 (decision 98,
``render_pile_seismic_check``) has WebPier's page of 杭頭反力の最大値から定める最小鉄筋量 after Aggre-SE's report, as the sample 0440
2.4 (1) prints it, and the 杭の段落とし計算書 of ⑧ (``PILE_ANCHOR_BAR``) after it as it is when the piles have a cut-off.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gridlayoutpdf import Row

from ...calc.detailing.pile import MINIMUM_CONCRETE, MINIMUM_FACTOR, MINIMUM_STEEL, PileSeismicResult
from ..assembly import write_as_is
from ..equations import Definition
from .detailing import PILE_MINIMUM_TAG, PILE_MINIMUM_TITLE
from .frame_report import Manuscript, sub, sup, value
from .ground_displacement import response_displacement
from .insertion import Insertion, render_with_pages

SEISMIC_CHECK = "seismic_check"  # Aggre-SE's report (0711, 0721)
SYMBOL_COLON = 9  # the colon of the "ここに、" list of the minimum bars: after Pvmax (as 0400's)
PILE_ANCHOR_BAR = "pile_anchor_bar"  # Aggre-SE's 杭の段落とし計算書 of ⑧ (0711, 0721 of piles with a cut-off, decision 98)


def render_seismic_check(path: str | Path, pages: Mapping[str, bytes]) -> Path:
    """Aggre-SE's report as the report at *path*, as it is; atomically replaces *path*."""
    if set(pages) != {SEISMIC_CHECK}:
        raise ValueError(f"耐震性能照査の計算書には Aggre-SE の帳票だけを受け取ります: {'・'.join(sorted(pages))}")
    return write_as_is(pages[SEISMIC_CHECK], path)


def minimum_bars(m: Manuscript, result: PileSeismicResult) -> None:
    """(1) of the sample 0440 2.4 with the Pvmax of the direction of the stage (decision 98)."""
    found = result.minimum
    pv, fck, fsyd = sub("P", "vmax"), sub("f'", "ck"), sub("f", "syd")
    m.heading("minimum.heading", PILE_MINIMUM_TITLE, 1, tag=PILE_MINIMUM_TAG)
    m.line("minimum.formula", Row("As ＝ 0.0104・", pv, " / (0.85・", fck, " ＋ 0.008・", fsyd, ")", gap=0))
    m.definitions("minimum.symbols", Definition(pv, "杭頭反力の最大値(kN)"),
                  Definition(fck, Row("コンクリートの設計圧縮強度(N/mm", sup("", "2"), ")", gap=0)),
                  Definition(fsyd, Row("鉄筋の降伏点強度(N/mm", sup("", "2"), ")", gap=0)), colon=SYMBOL_COLON)
    m.line("minimum.pvmax", Row(pv, f" ＝ {value(found.pvmax)} kN（Ｌ２応答時：{found.direction}）", gap=0))
    m.line("minimum.required", Row(f"As' ＝ {value(MINIMUM_FACTOR)} × {value(found.pvmax)} × ", sup("10", "3"),
                                   f" ／ ({value(MINIMUM_CONCRETE)} × {value(found.fck)} ＋ {value(MINIMUM_STEEL)} × "
                                   f"{value(found.fsyd)})", gap=0))
    m.line("minimum.result", Row(f"　　＝ {value(found.required)} mm", sup("", "2"), gap=0))
    section = found.section
    relation = "＞" if found.section.bar_area.value > found.required.value else "≦" if found.ok else "＜"
    m.line("minimum.check", Row(f"As ＝ D{value(section.bar_diameter)} － {section.bar_count} 本 ＝ "
                                f"{value(section.bar_area)} mm", sup("", "2"), f"　{relation}　{value(found.required)} mm",
                                sup("", "2"), gap=0))


def render_pile_seismic_check(stage_id: str, result: PileSeismicResult, first_case: int | None, path: str | Path,
                      pages: Mapping[str, bytes]) -> Path:
    """The pages of the 応答変位法 when *result* has it, Aggre-SE's report, the page of 杭頭反力の最大値から定める最小鉄筋量
    and the 杭の段落とし計算書 when the piles have a cut-off (decision 98; a 鋼管ソイルセメント杭 has neither, decision 122);
    atomically replaces *path*."""
    if not {SEISMIC_CHECK} <= set(pages) <= {SEISMIC_CHECK, PILE_ANCHOR_BAR}:
        raise ValueError(f"耐震性能照査の計算書には Aggre-SE の帳票だけを受け取ります: {'・'.join(sorted(pages))}")
    m = Manuscript(f"{stage_id}/")
    if result.response is not None:
        assert first_case is not None
        response_displacement(m, result.response, first_case)
    if result.minimum is None:  # a 鋼管ソイルセメント杭 (decision 122): the 応答変位法, if any, then Aggre-SE's report
        if not m.units:
            return render_seismic_check(path, pages)
        return render_with_pages(tuple(m.units), (Insertion(SEISMIC_CHECK, m.units[-1].key),), pages, path)
    minimum_bars(m, result)
    units = tuple(m.units)
    insertions = (Insertion(SEISMIC_CHECK, f"{stage_id}/minimum.heading", before=True),
                  Insertion(PILE_ANCHOR_BAR, units[-1].key, optional=True))
    return render_with_pages(units, insertions, pages, path)
