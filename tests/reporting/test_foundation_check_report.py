"""The 0612 / 0622 report (decision 54): n.10 基礎の照査 with its formulas and the vertical and horizontal tables.

The printed texts follow Example2 08 pp.8-27 to 8-32 as decision 54 writes them differently (pd1, kN/m2, the long term
limit beside the unlimited qd, Be, a judgement row in both tables); the numbers are those of the result, written
independently of webpier.reporting (frame_report_cases.text).
"""

from __future__ import annotations

from dataclasses import replace

import pymupdf
import pytest

from foundation_check_cases import chapter, result
from frame_report_cases import text
from webpier.calc import foundation_check as fc
from webpier.core.printed import Printed
from webpier.reporting.stages.foundation_check import build_foundation_check, records, render_foundation_check


def printed(stage: str, check: fc.FoundationCheckResult | None = None) -> str:
    return "".join(record["text"] for record in records(check or result(stage), chapter(stage)))


@pytest.mark.parametrize("stage,number", [("0612", 8), ("0622", 9)])
def test_the_section_continues_the_column_check_of_its_direction(stage, number):
    first = records(result(stage), chapter(stage))[0]
    assert (first["id"], first["text"]) == (f"{stage}/heading", f"{number}.10 基礎の照査")


@pytest.mark.parametrize("stage", ["0612", "0622"])
def test_the_tables_print_every_value_of_the_result(stage):
    check = result(stage)
    shown = printed(stage, check)
    for column in check.columns:
        for name in ("vd", "hd", "md", "ex", "b_effective", "area_effective", "delta", "pd1", "pd2", "gamma_e2",
                     "i_gamma", "i_q", "beta_b", "b_e", "term_gamma", "term_q", "qvd", "qd_unlimited", "qd", "rhb"):
            assert text(getattr(column, name)) in shown, (column.key, name)
        for judged in column.judgements:
            assert text(judged.value) in shown
    assert "判　　定ＯＫＯＫＯＫＯＫ" in shown and "ＮＧ" not in shown


def test_the_conditions_are_printed_from_the_basis():
    check = result("0612")
    shown, basis = printed("0612", check), check.basis
    assert "支持層は砂質土なので洪積砂地盤・沖積砂礫地盤とし" in shown
    assert f"上限値qd≦300+12.8×4.700={text(basis.long_term_limit)}kN/m2" in shown
    assert "平水位γe2=(2.000 × 18.0 + 2.700 × 9.0)/4.700=12.8kN/m3" in shown
    assert "高水位γe2=(0.920 × 18.0 + 3.780 × 9.0)/4.700=10.8kN/m3" in shown
    assert "地盤抵抗係数（長期支持 0.33，短期支持 0.50，安全性 0.67）" in shown
    for line in ("Df：フーチング底面の有効根入れ深さ(= 4.700 m)", "B：荷重作用方向のフーチング幅(= 7.000 m)",
                 "γi：構造物係数(= 1.2)", "frs：直接基礎の水平支持力に対する地盤抵抗係数(= 0.33)",
                 "γi・γa・pd1 / qd ≦ 1.0", "γi・Hd / Rhd ≦ 1.0"):
        assert line in shown


def test_a_failed_check_prints_ng_and_a_dash_for_a_missing_mmd():
    check = result("0612", fc.SupportReaction(1, 0, -3000000, 20000))
    shown = printed("0612", check)
    assert "Mmd (kN・m)" in shown and "－" in shown and "ＮＧ" in shown


def test_a_triangular_distribution_is_named():
    check = result("0612", fc.SupportReaction(1, 0, -16000, 20000))
    assert "形状三角形三角形三角形三角形" in printed("0612", check)
    assert "形状台形台形台形台形" in printed("0612")


def test_a_ground_without_the_cover_term_prints_its_limit_alone():
    check = result("0612")
    clay = replace(check, basis=replace(check.basis, ground=fc.GROUND_KINDS[2],
                                        long_term_limit=Printed(200.0, 2, "kN/m2")))
    assert "上限値qd≦200=200.00" in printed("0612", clay)


@pytest.mark.parametrize("stage", ["0612", "0622"])
def test_the_report_renders_the_same_bytes_every_time(tmp_path, stage):
    first = render_foundation_check(result(stage), tmp_path / "a.pdf", chapter(stage)).read_bytes()
    second = render_foundation_check(result(stage), tmp_path / "b.pdf", chapter(stage)).read_bytes()
    assert first == second
    pages = pymupdf.open(stream=first)
    words = "".join(page.get_text() for page in pages)
    assert "基礎の照査" in words and "水平支持に対する検討表" in words


def test_duplicated_unit_keys_are_refused(monkeypatch):
    from webpier.reporting.stages import foundation_check as report
    units = report.content(result("0612"), chapter("0612"))
    monkeypatch.setattr(report, "content", lambda *args: (*units, units[0]))
    with pytest.raises(ValueError, match="重複したキー"):
        build_foundation_check(result("0612"), chapter("0612"))
