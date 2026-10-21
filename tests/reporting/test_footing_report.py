"""The 0800 report (decision 60): 12.1 応答値の算定 of both directions, laid out by WebPier from the calc result.

The sample is 12_フーチング.pdf 244〜253: for each direction the table of the five columns with the distribution of the
base pressure and the figure of Case 1〜4, the effective width with its figure, the base reaction, the self weight and
the buoyancy of the chosen overhang, and the design moment and shear per metre. The chapter heading (§12) and 12.1
are not printed (decision 60). The numbers are the result's, written independently of webpier.reporting
(frame_report_cases.text).
"""

from __future__ import annotations

from dataclasses import replace

import pymupdf
import pytest

from footing_report_cases import completed
from frame_report_cases import text
from webpier.calc.footing import FootingResult
from webpier.reporting.stages.footing import build_footing, content, records, render_footing

HEADINGS = ("(1) 線路方向の計算", "1) 設計鉛直地盤反力度の算定", "2) 有効幅", "3) 地盤反力による断面力",
            "4) フーチング自重および上載土による断面力", "5) 浮力による断面力", "6) 設計曲げモーメント",
            "よって、下側引張となる。", "7) 発生せん断力", "(2) 線路直角方向の計算")


@pytest.fixture(scope="module")
def result() -> FootingResult:
    return FootingResult(completed("0800_longitudinal"), completed("0800_transverse"))


def printed(result: FootingResult) -> str:
    return "".join(record["text"] for record in records(result))


def test_the_report_begins_with_the_longitudinal_direction_without_the_chapter_heading(result):
    found = records(result)
    assert (found[0]["id"], found[0]["text"]) == ("0800/longitudinal.heading", "(1) 線路方向の計算")
    assert not any(record["text"].startswith(("§", "12.")) or "応答値の算定" in record["text"] for record in found)
    assert len({record["id"] for record in found}) == len(found)


def test_the_headings_follow_the_sample_in_order_for_both_directions(result):
    shown = printed(result)
    positions = [shown.index(heading) for heading in HEADINGS]
    assert positions == sorted(positions)
    second = shown[positions[-1]:]
    assert [heading for heading in HEADINGS[1:-1] if heading in second] == list(HEADINGS[1:-1])


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
def test_the_tables_print_every_value_of_every_column(result, direction):
    found, shown = getattr(result, direction), printed(result)
    for column in found.columns:
        for name in ("vd", "hd", "md", "alpha_b"):
            assert text(getattr(column, name)) in shown, (column.key, name)
        for name in ("ex", "b_effective", "area_effective", "delta", "gamma_e2", "i_gamma", "i_q", "beta_b", "b_e",
                     "term_gamma", "term_q", "qvd", "qd_unlimited", "mmd"):
            assert text(getattr(column.capacity, name)) in shown, (column.key, name)
        assert f"Case {column.distribution.case}" in shown
        for name in ("apex", "qd1", "qd2", "x1", "x2"):
            assert text(getattr(column.distribution, name)) in shown, (column.key, name)
        side = column.sides[column.chosen]
        for segment in side.segments:
            for name in ("q1", "length", "w", "x", "m"):
                assert text(getattr(segment, name)) in shown, (column.key, name)
            if not segment.uniform:
                assert text(segment.q2) in shown
        for name in ("m_reaction", "m_full", "m_per_m", "m_self", "m_buoyancy", "md", "v_reaction", "v_full",
                     "v_per_m", "v_self", "v_buoyancy", "vd", "la"):
            assert text(getattr(side.forces, name)) in shown, (column.key, name)


def test_the_column_headers_and_the_conditions_are_printed(result):
    shown = printed(result)
    for header in ("安全性Ｍd最大", "安全性Ｖd最大", "使用性短期", "使用性長期", "地震時"):
        assert header in shown.replace(" ", "").replace("\n", ""), header
    basis = result.longitudinal.basis.check
    for line in (f"B (m){text(basis.b)}", f"L (m){text(basis.l)}", f"Df (m){text(basis.depth)}",
                 f"φ (度){text(basis.friction_angle)}", f"γe1 (kN/m3){text(basis.gamma_e1)}",
                 f"Nγ{text(basis.n_gamma)}", f"Nq{text(basis.n_q)}", "αb = 1.0 + 0.2・B′ / L",
                 "βb = 0.5 − 0.2・B′ / L", "frγ0.670.670.500.33", "frq0.670.670.500.33", "frγ1.0", "frq1.0"):
        assert line in shown, line


def test_the_effective_width_and_the_weights_of_the_chosen_overhang_are_printed(result):
    found, shown = result.longitudinal, printed(result)
    width = found.basis.width
    assert "【ＲＣ標準 13.6.3】" in shown and "下　側" in shown
    assert (f"be = {text(width.left_effective)} + {text(width.column)} + {text(width.right_effective)}"
            f" = {text(width.be)} m ≦ {text(width.full)} m") in shown
    for value in (width.d, width.cover, width.height, width.left, width.right):
        assert text(value) in shown
    assert {column.chosen for column in found.columns} == {0}
    side = found.basis.sides[0]
    for row in (side.weight.overburden, side.weight.footing, side.water.high, side.water.normal, side.water.low):
        for name in ("height", "length", "volume", "unit_weight", "w", "x", "m"):
            assert text(getattr(row, name)) in shown, name
    assert f"合　　計－－{text(side.weight.w)}{text(side.weight.m)}" in shown
    for label in ("①", "②", "高水位", "平水位", "低水位", "計　算　式", "M = W・x"):
        assert label in shown, label
    assert "終点側" not in shown


def test_both_overhangs_are_printed_when_the_columns_choose_different_sides(result):
    found = result.longitudinal
    mixed = replace(found, columns=(replace(found.columns[0], chosen=1), *found.columns[1:]))
    shown = printed(FootingResult(mixed, result.transverse))
    assert "・起点側" in shown and "・終点側" in shown
    assert shown.count("合　　計") == 3  # two overhangs along the track, one across it


def test_the_figures_carry_their_labels(result):
    found = records(result)
    figures = {record["id"]: record["text"] for record in found if record["id"].endswith(".figure")}
    assert len(figures) == 8
    cases = figures["0800/longitudinal.pressure.cases.figure"]
    for label in ("Case 1", "Case 2", "Case 3", "Case 4", "x", "x1", "x2", "pd1", "pd2", "pd1=qd"):
        assert label in cases, label
    width = result.longitudinal.basis.width
    for value in (width.left, width.column, width.right, width.full, width.height, width.d, width.cover):
        assert text(value) in figures["0800/longitudinal.width.figure"]
    side = result.longitudinal.basis.sides[0]
    assert text(side.length) in figures["0800/longitudinal.reaction.起点側.figure"]
    for label in ("q1", "q2", "x", "L1"):
        assert label in figures["0800/longitudinal.reaction.起点側.figure"], label
    weight = figures["0800/longitudinal.weight.起点側.figure"]
    for value in (side.length, side.cover_depth, width.height):
        assert text(value) in weight
    assert "①" in weight and "②" in weight


def test_the_design_forces_name_the_full_and_the_effective_width(result):
    shown = printed(result)
    width = result.longitudinal.basis.width
    for line in (f"全幅当り B = {text(width.full)} m", f"1 m当たりモーメント (kN・m) Be = {text(width.be)} m",
                 "フーチング自重と上載土によるモーメント (kN・m)", "浮力によるモーメント (kN・m)",
                 "設計曲げモーメント Md (kN・m)", "地盤反力によるせん断力 (kN/m)", f"1 m当たりせん断力 (kN) Be = {text(width.be)} m",
                 "設計せん断力 Vd (kN)", "せん断スパン La = Md / Vd (m)"):
        assert line in shown, line


def test_the_report_renders_the_same_bytes_every_time(tmp_path, result):
    first = render_footing(result, tmp_path / "a.pdf").read_bytes()
    second = render_footing(result, tmp_path / "b.pdf").read_bytes()
    assert first == second
    with pymupdf.open(stream=first) as pages:
        words = "".join(page.get_text() for page in pages)
    for heading in HEADINGS:
        assert heading in words, heading
    assert "Case 1" in words and "pd1=qd" in words


def test_duplicated_unit_keys_are_refused(monkeypatch, result):
    from webpier.reporting.stages import footing as report
    units = report.content(result)
    monkeypatch.setattr(report, "content", lambda *args: (*units, units[0]))
    with pytest.raises(ValueError, match="重複したキー"):
        build_footing(result)


def test_the_tables_and_figures_stand_on_the_grid_within_the_body(result):
    """GridLayoutPdf's common grid: tables and figures take whole grid columns and rows and end by the body's right
    edge (column 30); a table's header is two grid rows (two-line titles), every other row one."""
    units = content(result)
    tables = [unit.value for unit in units if unit.kind == "table"]
    figures = [unit.value for unit in units if unit.kind == "figure"]
    assert len(tables) == 18 and len(figures) == 8
    for spec in tables:
        assert all(isinstance(width, int) for width in (spec.left, *spec.widths))
        assert spec.left + sum(spec.widths) <= 30
        assert spec.row_heights == (2, *(1,) * (len(spec.rows) - 1))
    for spec in figures:
        assert spec.left + spec.block.col_span <= 30 and isinstance(spec.block.rows, int)
