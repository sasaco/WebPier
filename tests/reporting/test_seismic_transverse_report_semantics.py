"""0720 semantics: every printed number is a SeismicTransverseResult value at its digits (Example2 11 pp.11-1..11-13).

Example2 11 prints the JRSNAP pages 11-2..11-7; this report prints the same
model as tables, like 0710, without springs and without load diagrams (decision
41). One combination per track (decision 21); the earthquake acts toward W9 (→,
decision 30).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from frame_report_cases import TRANSVERSE_CASES, text, transverse_chain
from test_longitudinal_report_semantics import material, member_rows, node_rows, section, squeeze
from test_transverse_report_semantics import bearing, dead_records, paren, seat, top
from webpier.calc.frame import NodeRole, Region
from webpier.calc.seismic_transverse import SeismicCase
from webpier.calc.transverse import Item, Track
from webpier.core.printed import Printed

t = text
CASES = ["固定死荷重", "付加死荷重", "浮力（平水位）", "雪荷重（2年確率）", "列車荷重（上り）", "列車荷重（下り）",
         "地震時桁荷重慣性力", "地震時列車荷重慣性力", "自重による地震時慣性力"]
SYMBOLS = ["D1", "D2", "Wp", "Sw2", "L", "L", "EQ1", "EQL", "EQ2"]


def names(result) -> list[str]:
    kh = {7: result.girder_inertia.kh, 8: result.train_inertia.kh, 9: result.self_weight.kh}
    return [name + (f"（Kh={t(kh[i])}）" if i in kh else "") for i, name in enumerate(CASES, 1)]


def expected(case: str) -> dict[str, str]:
    pier, reaction, _, result = transverse_chain(case)
    frame = result.frame
    out: dict[str, str] = {}

    def add(key: str, value: str | None) -> None:
        if value is not None:
            out["0720/" + key] = value

    add("title", "§11.線路直角方向の計算（地震時）")
    add("model.heading", "11.1検討モデル")
    add("model.figure.heading", "(1)骨組図")
    figure = [str(n.number) for n in frame.nodes] + [str(m.number) for m in frame.members]
    figure += [t(m.height) for m in frame.members if m.height.value > 0]
    figure += [t(frame.pier_height), t(frame.node(NodeRole.FOOTING_TOP).y), t(max(frame.nodes, key=lambda n: n.y.value).y)]
    add("model.figure", "".join(figure))
    add("model.figure.note", "太線は剛域を示す．◎は柱下端の微小部材（長さ0.010m）を示す．最上段の節点は桁の高さ"
                             "（支承位置からh1+h2）である．寸法の単位はm．")
    add("model.nodes.heading", "(2)節点と部材")
    add("model.nodes", node_rows(frame, springs=False))
    add("model.members", member_rows(frame))
    add("section.heading", "(3)部材の断面諸元")
    add("section.rigid", "柱下端の微小部材以外の部材はすべて剛域とする．")
    add("section.micro.heading", "1)柱下端の微小部材")
    micro = next(m for m in frame.members if m.region is Region.COLUMN_BASE)
    out.update({"0720/" + k: v for k, v in section("section.micro", micro.section).items()})
    add("section.footing.centroid", f"フーチング重心yG={t(frame.node(NodeRole.FOOTING_CENTROID).y)}m")
    add("section.material.heading", "2)弾性係数")
    out.update({"0720/" + k: v for k, v in material("section.material.column", "柱", frame.materials.column).items()})
    add("actions.heading", "11.2作用の計算")
    # Decision 78: D1, D2, the buoyancy at the normal water level and the 2-year snow as 9.2, no reference to §9.
    sw = reaction.self_weight
    dead_records(add, pier, reaction, frame, result.fixed, result.additional)
    add("buoyancy.heading", "(3)浮力（平水位）")
    row, water = result.buoyancy, sw.buoyancy_normal
    add("buoyancy", f"ω={t(water.body.unit_weight)}×{t(water.body.volume)}={t(row.n)}kN")
    if row.arm.value:
        add("buoyancy.moment", f"MP={t(row.n)}×{paren(row.arm)}={t(row.m)}kN・m")
    if result.snow is not None:
        add("snow.heading", "(4)雪荷重（2年確率）")
        add("snow", top(result.snow))
        add("snow.seat", seat(frame, result.snow.n, result.snow.m, result.basic(SeismicCase.SNOW).points[0]))

    def item(number: int) -> str:  # decision 69: the items follow those of 9.2, without (4) 雪荷重 when no snow
        return f"({number if result.snow is not None else number - 1})"

    add("train.heading", f"{item(5)}列車荷重")
    add("train.note", "鉛直力は0600の地震時列車荷重による反力に支承の分担率を乗じた値とする（上り線L2，下り線L1）．")
    for track, label in ((Track.UP, "上り"), (Track.DOWN, "下り")):
        table = result.train(track)
        add(f"train.{track.value}.heading", f"・{label}線載荷")
        add(f"train.{track.value}", "反力(kN)分担率鉛直力(kN)アーム(m)モーメント(kN・m)" + "".join(
            bearing(r.item, r.slot) + "".join(t(v) for v in (r.reaction, r.share, r.n, r.arm, r.m)) for r in table.rows)
            + f"合計{t(table.n)}{t(table.m)}")
    for key, heading, inertia in (("girder", f"{item(6)}地震時桁荷重慣性力", result.girder_inertia),
                                  ("train_inertia", f"{item(7)}地震時列車荷重慣性力", result.train_inertia)):
        add(f"{key}.heading", heading)
        add(f"{key}.h", f"水平力H={t(inertia.rows[0].h)}+{t(inertia.rows[1].h)}={t(inertia.h)}kN")
        add(f"{key}.table", "水平力(kN)高さ(m)モーメント(kN・m)" + "".join(
            ("起点側桁" if r.item is Item.ORIGIN else "終点側桁") + t(r.h) + t(r.y) + t(r.m) for r in inertia.rows)
            + f"合計{t(inertia.h)}{t(inertia.m)}")
    add("inertia.source", f"{item(6)}，{item(7)}は0600の支承の水平力（桁荷重Kh={t(result.girder_inertia.kh)}，列車荷重Kh="
                          f"{t(result.train_inertia.kh)}）をそのまま用い，支承位置からの高さyでM=H×yとする．")
    inertia = result.self_weight
    add("inertia.heading", f"{item(8)}自重による地震時慣性力")
    add("inertia.kh", f"設計水平震度Kh={t(inertia.kh)}")
    add("inertia.body", "・橋脚く体に作用する水平力")
    for key, label, name, value in (("beam_top", "はり", "w1", inertia.beam_top),
                                    ("beam_bottom", "ハンチ下端", "w2", inertia.beam_bottom),
                                    ("column", "柱", "w3", inertia.column), ("pedestal", "桁受け", "w4", inertia.pedestal)):
        if value is not None:
            add(f"inertia.{key}", f"{label}H{name}={t(value.along)}×{t(value.across)}×{t(value.unit_weight)}×"
                                  f"{t(value.kh)}={t(value.value)}kN/m")
    add("inertia.footing.heading", "・フーチング重心に作用する水平力")
    f = inertia.footing
    add("inertia.footing.formula", "H=V×(γ−γ')×Kh")
    add("inertia.footing", f"H={t(f.volume)}×({t(f.unit_weight)}−{t(f.displaced)})×{t(f.kh)}={t(f.force)}kN")
    add("inertia.footing.note", "ここに、V：フーチングの体積（§6）γ'：排除した土（表層）の湿潤単位体積重量")
    add("diagrams.heading", "11.3荷重図")
    add("combination.heading", "11.4作用の組合せ")
    add("basic.caption", "基本Case")
    arrows = {"downward": "↓", "upward": "↑", "toward_w9": "→", "toward_w1": "←"}  # ← the reversed down track
    kinds = {"fixed": "固定", "incremental": "増分", "limited_incremental": "限定増分"}
    add("basic", "Case記号作用方向荷重種別荷　重　名　称" + "".join(
        f"{a.number}{SYMBOLS[a.case.value - 1]}{arrows[a.direction.value]}{kinds[a.increment.value]}"
        f"{names(result)[a.case.value - 1]}"
        for a in result.basic_cases))
    add("combination.caption", "組合せCase")
    add("combination", "Case列車αf／ρm作用方向荷重補正係数＋基本Case地盤抵抗TYPE" + "".join(
        f"{c.number}{'上り' if c.track is Track.UP else '下り'}{t(c.alpha_f)}／{t(c.rho_m)}{arrows[c.direction.value]}"
        + "+".join(str(result.basic(case).number) for case in c.cases) + str(c.ground_resistance_type) for c in result.combinations))
    add("combination.note", "上り線・下り線の列車荷重をそれぞれ組み合わせる．")
    return out


def actual(case: str, result=None) -> dict[str, str]:
    from webpier.reporting.stages.frame_report import plain
    from webpier.reporting.stages.seismic_transverse import content

    pier, reaction, _, seismic = transverse_chain(case)
    units = content(result or seismic, reaction, pier)
    assert len({unit.key for unit in units}) == len(units)
    return {unit.key: squeeze(plain(unit.value)) for unit in units}


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_every_record_prints_the_result_values_at_their_digits_in_order(case: str):
    want = {key: squeeze(value) for key, value in expected(case).items()}
    got = actual(case)
    assert list(got) == list(want)
    for key in want:
        assert got[key] == want[key], key


def test_current_input_prints_the_example2_values():
    got = actual("current")
    assert "起点側RBG1320.00-0.020-6.40-3.80024.32" in got["0720/train.up"]
    assert got["0720/train.up"].endswith("合計480.001028.62")
    assert got["0720/train_inertia.h"] == "水平力H=96.00+48.00=144.00kN"
    assert got["0720/train_inertia.table"].endswith("合計144.00770.40")
    assert "13.050" in got["0720/model.figure"] and "1+2+3+4+5+7+8+9" in got["0720/combination"]
    assert "1+2+3+4+6+7+8+9" in got["0720/combination"]
    assert not any("§9" in text for text in got.values())  # decision 78: 11.2 prints D1 to S2 itself
    assert got["0720/fixed.n"].endswith("=8299.53kN")  # the 9-3 value of 0620


def test_the_report_reads_the_results_not_the_input():
    _, _, _, result = transverse_chain("current")
    girder = replace(result.girder_inertia, h=Printed(1.23, 2, "kN"))
    assert actual("current", replace(result, girder_inertia=girder))["0720/girder.h"].endswith("=1.23kN")
