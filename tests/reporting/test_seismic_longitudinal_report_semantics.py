"""0710 semantics: every printed number is a SeismicLongitudinalResult value at its digits (Example2 10 pp.10-1..10-12).

The expected records are written here from the results with this module's own
formatter. Example2 10 prints the JRSNAP pages 10-2..10-7 (element, nonlinear
and section number figures, the section rebar, the spring distribution); this
report prints the same model as the node/member tables and the section of the
micro member, and leaves the rebar to the JRSNAP output (decision 32). It shows
no springs and no load diagrams (decision 41).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from frame_report_cases import CASES, chain, text
from test_longitudinal_report_semantics import (
    material, member_rows, node_rows, section, squeeze,
)
from webpier.calc.frame import NodeRole, Region
from webpier.calc.longitudinal import Item
from webpier.calc.seismic_longitudinal import SeismicCase
from webpier.core.printed import Printed

t = text
CASE_NAMES = ["固定死荷重", "付加死荷重", "浮力（平水位）", "雪荷重（2年確率）", "列車荷重", "地震時桁荷重慣性力",
              "地震時列車荷重慣性力", "自重による地震時慣性力"]
SYMBOLS = ["D1", "D2", "Wp", "Sw2", "L", "EQ1", "EQL", "EQ2"]


def names(result) -> list[str]:
    kh = {6: result.girder_inertia.kh, 7: result.train_inertia.kh, 8: result.self_weight.kh}
    return [name + (f"（Kh={t(kh[i])}）" if i in kh else "") for i, name in enumerate(CASE_NAMES, 1)]


def model_figure(frame) -> str:
    out = [str(node.number) for node in frame.nodes] + [str(member.number) for member in frame.members]
    out += [t(member.height) for member in frame.members if member.height.value > 0]
    out += [t(frame.pier_height), t(frame.node(NodeRole.FOOTING_TOP).y), t(max(frame.nodes, key=lambda n: n.y.value).y)]
    return "".join(out)


def expected(case: str) -> dict[str, str]:
    pier, reaction, _, result = chain(case)
    frame = result.frame
    out: dict[str, str] = {}

    def add(key: str, value: str | None) -> None:
        if value is not None:
            out["0710/" + key] = value

    add("title", "§10.線路方向の計算（地震時）")
    add("model.heading", "10.1検討モデル")
    add("model.figure.heading", "(1)骨組図")
    add("model.figure", model_figure(frame))
    add("model.figure.note", "太線は剛域を示す．◎は柱下端の微小部材（長さ0.010m）を示す．寸法の単位はm．")
    add("model.nodes.heading", "(2)節点と部材")
    add("model.nodes", node_rows(frame, springs=False))
    add("model.members", member_rows(frame))
    add("section.heading", "(3)部材の断面諸元")
    add("section.rigid", "柱下端の微小部材以外の部材はすべて剛域とする．")
    add("section.micro.heading", "1)柱下端の微小部材")
    micro = next(m for m in frame.members if m.region is Region.COLUMN_BASE)
    out.update({"0710/" + k: v for k, v in section("section.micro", micro.section).items()})
    add("section.footing.centroid", f"フーチング重心yG={t(frame.node(NodeRole.FOOTING_CENTROID).y)}m")
    add("section.material.heading", "2)弾性係数")
    out.update({"0710/" + k: v for k, v in material("section.material.column", "柱", frame.materials.column).items()})
    add("actions.heading", "10.2作用の計算")
    add("actions.note", "下記以外の作用については，§8.線路方向の計算（地震時以外）と同様とする．")
    add("train.heading", "(1)列車荷重")
    add("train.single", "・単線載荷")
    train = result.train
    labels = {Item.ORIGIN: "起点側RB", Item.END: "終点側RC"}
    add("train", "鉛直力(kN)アーム(m)モーメント(kN・m)" + "".join(labels[r.item] + t(r.n) + t(r.arm) + t(r.m)
                                                           for r in train.rows) + f"合計{t(train.n)}{t(train.m)}")
    e = frame.bearing_offset
    if e.value:
        point = result.basic(SeismicCase.TRAIN).points[0]
        paren = f"({t(e)})" if e.value < 0 else t(e)
        add("train.seat", f"桁受け天端M={t(train.m)}−{t(train.n)}×{paren}={t(point.m)}kN・m")
    add("horizontal.heading", "(2)水平荷重")
    add("horizontal.summary.heading", "1)支承に働く水平荷重のまとめ")
    g, r = result.girder_inertia.forces, result.train_inertia.forces
    add("horizontal", "荷　重　種　別起点桁(kN)終点桁(kN)合計(kN)"
        f"地震時1.0EQ（桁荷重）{t(g.origin.force)}{t(g.end.force)}{t(g.total)}"
        f"1.0EQ（列車荷重）{t(r.origin.force)}{t(r.end.force)}{t(r.total)}")
    add("horizontal.note", f"0600の支承の水平力（桁荷重Kh={t(result.girder_inertia.kh)}，"
                           f"列車荷重μ={t(result.train_inertia.kh)}）をそのまま用いる．")
    inertia = result.self_weight
    add("inertia.heading", "(3)自重による地震時慣性力")
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
    add("diagrams.heading", "10.3荷重図")
    add("combination.heading", "10.4作用の組合せ")
    add("basic.caption", "基本Case")
    arrows = {"downward": "↓", "upward": "↑", "toward_origin": "←"}
    kinds = {"fixed": "固定", "incremental": "増分", "limited_incremental": "限定増分"}
    add("basic", "Case記号作用方向荷重種別荷　重　名　称" + "".join(
        f"{a.number}{SYMBOLS[a.case.value - 1]}{arrows[a.direction.value]}{kinds[a.increment.value]}"
        f"{names(result)[a.case.value - 1]}"
        for a in result.basic_cases))
    add("combination.caption", "組合せCase")
    add("combination", "Caseαf／ρm作用方向荷重補正係数＋基本Case地盤抵抗TYPE" + "".join(
        f"{c.number}{t(c.alpha_f)}／{t(c.rho_m)}{arrows[c.direction.value]}"
        + "+".join(str(result.basic(case).number) for case in c.cases) + str(c.ground_resistance_type) for c in result.combinations))
    return out


def actual(case: str, result=None) -> dict[str, str]:
    from webpier.reporting.stages.seismic_longitudinal import semantic_records

    pier, _, _, seismic = chain(case)
    records = semantic_records(result or seismic, pier)
    assert len({r["id"] for r in records}) == len(records)
    return {r["id"]: squeeze(r["text"]) for r in records}


@pytest.mark.parametrize("case", list(CASES))
def test_every_record_prints_the_result_values_at_their_digits_in_order(case: str):
    want = {key: squeeze(value) for key, value in expected(case).items()}
    got = actual(case)
    assert list(got) == list(want)
    for key in want:
        assert got[key] == want[key], key


def test_current_input_prints_the_example2_values():
    got = actual("current")
    assert "起点側RB320.00-0.325-104.00" in got["0710/train"] and got["0710/train"].endswith("合計480.004.00")
    assert "6790.004740.0011530.00" in got["0710/horizontal"] and "64.0064.00128.00" in got["0710/horizontal"]
    assert got["0710/inertia.beam_top"] == "はりHw1=2.700×9.000×24.5×1.00=595.35kN/m"
    assert got["0710/inertia.column"].endswith("=297.68kN/m")
    assert got["0710/inertia.footing"] == "H=170.100×(24.5−18.0)×1.00=1105.65kN"
    assert "1+2+3+4+5+6+7+8" in got["0710/combination"]
    assert "4.8900.010" in got["0710/model.figure"]  # the column and the micro member below it


def test_variants_change_what_is_printed():
    pedestal, current = actual("pedestal"), actual("current")
    assert "0710/inertia.pedestal" in pedestal and "0710/inertia.pedestal" not in current
    assert "0710/train.seat" in pedestal


def test_the_report_reads_the_results_not_the_input():
    _, _, _, result = chain("current")
    footing = replace(result.self_weight.footing, force=Printed(1.23, 2, "kN"))
    sentinel = replace(result, self_weight=replace(result.self_weight, footing=footing))
    assert actual("current", sentinel)["0710/inertia.footing"].endswith("=1.23kN")
