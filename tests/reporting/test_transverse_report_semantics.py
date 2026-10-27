"""0620 semantics: every printed number is a value of the results at its digits, in Example2 09's order.

The expected records are written here from the TransverseResult, the 0600
ReactionResult and the input with this module's own formatter. The wording
follows Example2 09 pp.9-1..9-15; the formula lines, the per-bearing tables
with their factors, the wind segments above the ground (decision 12) and the
centrifugal tables (decision 33) are additions that make every value checkable.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from frame_report_cases import TRANSVERSE_CASES, part_weight, text, transverse_chain
from test_longitudinal_report_semantics import (
    material, member_rows, node_rows, paren, pedestal_note, seat_tables, section, springs, squeeze,
)
from webpier.calc.frame import NodeRole, Region
from webpier.calc.longitudinal.actions import SpringTerm
from webpier.calc.transverse import BasicCase, Item, Track
from webpier.core.printed import Printed

t = text
WIND = {Region.BEAM: ("Hw1", "Hw1"), Region.HAUNCH: ("Hw1", "Hw2"), Region.COLUMN: ("Hw3", "Hw3"),
        Region.PEDESTAL: ("Hw4", "Hw4")}
PARTS = {Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.PEDESTAL: "桁受け"}
BASIC = {1: ("固定死荷重", "", "D1"), 2: ("付加死荷重", "", "D2"), 3: ("浮力", "高水位", "WP1"), 4: ("浮力", "平水位", "WP2"),
         5: ("浮力", "低水位", "WP3"), 6: ("雪荷重", "2年確率", "SS2"), 7: ("雪荷重", "10年確率", "SS10"),
         8: ("雪荷重", "30年確率", "SS30"), 9: ("列車荷重", "単線　上り", "L1"), 10: ("列車荷重", "単線　下り", "L1"),
         11: ("列車荷重", "複線", "L2"), 12: ("衝撃荷重", "安全性・復旧性　単線　上り", "I1"),
         13: ("衝撃荷重", "安全性・復旧性　単線　下り", "I1"), 14: ("衝撃荷重", "安全性・復旧性　複線", "I2"),
         15: ("車両横荷重", "単線", "LF1"), 16: ("車両横荷重", "複線", "LF2"), 17: ("風荷重", "列車荷重がある場合", "W1"),
         18: ("風荷重", "列車荷重がない場合", "W2"), 19: ("遠心荷重", "単線　上り", "CF1"),
         20: ("遠心荷重", "単線　下り", "CF1"), 21: ("遠心荷重", "複線", "CF2")}
# the remark of each of the 16 checks; a check with the train adds its loading (decision 106)
REMARKS = {1: "列車最大", 2: "車横最大", 3: "風最大", 4: "雪最大", 5: "縁応力度", 6: "永久荷重", 7: "変動荷重", 8: "列車最大",
           9: "雪最大", 10: "列車最大", 11: "車横最大", 12: "風最大", 13: "雪最大", 14: "", 15: "低水位", 16: "高水位"}


def bearing(item, slot) -> str:
    return ("起点側RB" if item is Item.ORIGIN else "終点側RC") + f"G{slot + 1}"


def top(table) -> str:
    names = {Item.BEAM: "はり"}
    return ("鉛直力(kN)アーム(m)モーメント(kN・m)"
            + "".join((bearing(r.item, r.slot) if r.slot is not None else names[r.item]) + t(r.n) + t(r.arm) + t(r.m)
                      for r in table.rows) + f"合計{t(table.n)}{t(table.m)}")


def products(header: str, rows, total) -> str:
    return (header + "鉛直力(kN)アーム(m)モーメント(kN・m)"
            + "".join(bearing(r.item, r.slot) + "".join(t(v) for v in values) for r, values in rows)
            + f"合計{t(total.n)}{t(total.m)}")


def seat(frame, n, m, point) -> str | None:
    e = frame.bearing_offset
    return None if not e.value else f"桁受け天端M={t(m)}−{t(n)}×{paren(e)}={t(point.m)}kN・m"


def dead_records(add, pier, reaction, frame, fixed, additional, number: int = 1) -> None:
    """The records of (1) 固定死荷重 and (2) 付加死荷重 as 9.2 prints them; 11.2 prints the same (decision 78)."""
    s, sw = pier.substructure, reaction.self_weight
    add("fixed.heading", f"({number})固定死荷重")
    if fixed.pedestal_q is not None:
        add("fixed.pedestal", f"桁受けq={t(s.w[3])}×{t(s.b[3])}×{t(s.unit_weight_body)}={t(fixed.pedestal_q)}kN/m")
    add("fixed.column", f"柱q={t(s.w[6])}×{t(s.b[6])}×{t(s.unit_weight_body)}={t(fixed.column_q)}kN/m")
    add("fixed.footing", f"フーチングP={part_weight(sw.footing)}={t(fixed.footing.n)}kN")
    if fixed.footing.arm.value:
        add("fixed.footing.moment", f"MP={t(fixed.footing.n)}×{paren(fixed.footing.arm)}={t(fixed.footing.m)}kN・m")
    add("fixed.top.heading", "・橋脚天端に作用する荷重")
    add("fixed.top.beam", f"はり・ハンチN={part_weight(sw.beam)}={t(fixed.table.row(Item.BEAM).n)}kN")
    if frame.pedestal_section is not None:
        add("fixed.top.seat", "・はり天端")
    add("fixed.top", top(fixed.table))
    add("fixed.overlap", f"重複区間Δh={t(s.h[2])}+{t(s.h[3])}={t(fixed.overlap)}m")
    add("fixed.overlap.note", "ここに、Δh：はりの高さ＋ハンチの高さ（柱のqと重なる長さ）")
    add("fixed.n", f"鉛直力N={t(fixed.table.n)}−{t(fixed.column_q)}×{t(fixed.overlap)}={t(fixed.n)}kN")
    add("fixed.m", f"モーメントM={t(fixed.m)}kN・m")
    if fixed.pedestal is not None:
        add("fixed.pedestal.seat", "・桁受け天端")
        add("fixed.pedestal.top", top(fixed.pedestal))
        add("fixed.pedestal.note", pedestal_note(frame))
    add("additional.heading", f"({number + 1})付加死荷重")
    soil = additional.soil
    add("additional.soil", f"載荷土P={part_weight(sw.overburden)}={t(soil.n)}kN")
    if soil.arm.value:
        add("additional.soil.moment", f"MP={t(soil.n)}×{paren(soil.arm)}={t(soil.m)}kN・m")
    seat_tables(add, frame, "additional.top", ((NodeRole.CAP_TOP, additional.table),
                                               (NodeRole.PEDESTAL_TOP, additional.pedestal)), top)


def expected(case: str) -> dict[str, str]:
    pier, reaction, result, _ = transverse_chain(case)
    frame, s, sw = result.frame, pier.substructure, reaction.self_weight
    out: dict[str, str] = {}

    def add(key: str, value: str | None) -> None:
        if value is not None:
            out["0620/" + key] = value

    def item(number: int) -> str:  # decision 69: without snow (4) 雪荷重 is not printed and the items move up
        return f"({number if result.snow is not None else number - 1})"

    add("title", "§9.線路直角方向の計算（地震時以外）")
    add("model.heading", "9.1検討モデル")
    add("model.figure.heading", "(1)骨組図")
    figure = [str(n.number) for n in frame.nodes] + [str(m.number) for m in frame.members]
    figure += [t(m.height) for m in frame.members if m.height.value > 0]
    figure += [t(frame.pier_height), t(frame.node(NodeRole.FOOTING_TOP).y), t(max(frame.nodes, key=lambda n: n.y.value).y)]
    figure += [t(s.w[i]) for i in (7, 8, 9) if s.w[i].value > 0] + [t(sw.footing_width), "KvKsKr"]
    add("model.figure", "".join(figure))
    add("model.figure.note", "太線は剛域を示す．寸法の単位はm．")
    add("model.springs.caption", "フーチング底面のばね")
    add("model.springs", springs(frame))
    add("model.nodes.heading", "(2)節点と部材")
    add("model.nodes", node_rows(frame))
    add("model.members", member_rows(frame))
    add("section.heading", "(3)部材の断面諸元")
    add("section.column.heading", "1)柱（はり・ハンチを含む）")
    out.update({"0620/" + k: v for k, v in section("section.column", frame.column_section).items()})
    number = 2
    if frame.pedestal_section is not None:
        add("section.pedestal.heading", "2)桁受け")
        out.update({"0620/" + k: v for k, v in section("section.pedestal", frame.pedestal_section).items()})
        number = 3
    add("section.footing.heading", f"{number})フーチング")
    add("section.footing.rigid", "フーチングはすべて剛域とする．")
    add("section.footing.centroid", f"断面の重心位置yG={t(frame.node(NodeRole.FOOTING_CENTROID).y)}m")
    add("section.material.heading", f"{number + 1})弾性係数")
    elastic = {m.region for m in frame.members if not m.rigid}
    key, label = ("body", "く体") if elastic & {Region.BEAM, Region.HAUNCH} else ("column", "柱")
    out.update({"0620/" + k: v for k, v in material(f"section.material.{key}", label, frame.materials.column).items()})
    add("actions.heading", "9.2作用の計算")
    dead_records(add, pier, reaction, frame, result.fixed, result.additional)
    add("buoyancy.heading", "(3)浮力")
    for (key, label, suffix), row, water in zip((("high", "高水位", "1"), ("normal", "平水位", "2"), ("low", "低水位", "3")),
                                                result.buoyancy, (sw.buoyancy_high, sw.buoyancy_normal, sw.buoyancy_low)):
        add(f"buoyancy.{key}", f"{label}ω{suffix}={t(water.body.unit_weight)}×{t(water.body.volume)}={t(row.n)}kN")
        if row.arm.value:
            add(f"buoyancy.{key}.moment", f"MP={t(row.n)}×{paren(row.arm)}={t(row.m)}kN・m")
    if result.snow is not None:
        add("snow.heading", "(4)雪荷重")
        for index, (key, label, case_) in enumerate((("2", "1)2年確率", BasicCase.SNOW2),
                                                     ("10", "2)10年確率", BasicCase.SNOW10),
                                                     ("30", "3)30年確率", BasicCase.SNOW30))):
            add(f"snow.{key}.heading", label)
            add(f"snow.{key}", top(result.snow[index]))
            add(f"snow.{key}.seat", seat(frame, result.snow[index].n, result.snow[index].m,
                                         result.basic(case_).points[0]))
    add("train.heading", f"{item(5)}列車荷重")
    add("train.note", "鉛直力は0600の1線分の反力に支承の分担率を乗じた値とする（上り線L2，下り線L1）．")
    names = {Track.UP: "上り線載荷", Track.DOWN: "下り線載荷", Track.DOUBLE: "複線載荷"}
    trains = {Track.UP: BasicCase.TRAIN_UP, Track.DOWN: BasicCase.TRAIN_DOWN, Track.DOUBLE: BasicCase.TRAIN_DOUBLE}
    for track, case_ in trains.items():
        table = result.train.table(track)
        add(f"train.{track.value}.heading", "・" + names[track])
        add(f"train.{track.value}", products("反力(kN)分担率", [(r, (r.reaction, r.share, r.n, r.arm, r.m))
                                                             for r in table.rows], table))
        add(f"train.{track.value}.seat", seat(frame, table.n, table.m, result.basic(case_).points[0]))
    add("impact.heading", f"{item(6)}衝撃荷重")
    add("impact.note", "鉛直力は列車荷重に橋脚く体の衝撃係数を乗じた値とする．")
    impacts = {Track.UP: BasicCase.IMPACT_UP, Track.DOWN: BasicCase.IMPACT_DOWN, Track.DOUBLE: BasicCase.IMPACT_DOUBLE}
    for usage, label, impact_set in (("ultimate", "安全性・復旧性", result.impact.ultimate),
                                     ("service", "使用性", result.impact.service)):
        for track, case_ in impacts.items():
            table = impact_set.table(track)
            key = f"impact.{usage}.{track.value}"
            add(key + ".heading", f"・{names[track]}（{label}）")
            add(key, products("列車荷重(kN)衝撃係数", [(r, (r.train, r.coefficient, r.n, r.arm, r.m))
                                                       for r in table.rows], table))
            if frame.bearing_offset.value:
                point = (result.basic(case_).points[0] if usage == "ultimate" else
                         next(a.source.points[0] for c in result.combinations for comp in c.components
                              for a in comp.alternatives if a.case is case_ and a.basis.value == "service_impact"))
                add(key + ".seat", seat(frame, table.n, table.m, point))
    lateral = result.lateral
    add("lateral.heading", f"{item(7)}車両横荷重")
    add("lateral.single.heading", "1)単線載荷の場合")
    add("lateral.h", f"水平力H={t(lateral.origin.h)}+{t(lateral.end.h)}={t(lateral.h)}kN")
    add("lateral.m", f"モーメントM={t(lateral.origin.h)}×{t(lateral.origin.y)}+{t(lateral.end.h)}×{t(lateral.end.y)}"
                     f"={t(lateral.m)}kN・m")
    add("lateral.double.heading", "2)複線載荷の場合")  # two tracks (decision 106)
    add("lateral.double.h", f"水平力H=2×{t(lateral.h)}={t(lateral.double_h)}kN")
    add("lateral.double.m", f"モーメントM=2×{t(lateral.m)}={t(lateral.double_m)}kN・m")
    add("wind.heading", f"{item(8)}風荷重")
    ground = result.wind_with_train.pier
    add("wind.ground.heading", "・く体の受風範囲（地表面はフーチング天端から起点側・終点側の土かぶりの小さい方だけ上）")
    add("wind.ground", f"地表面の高さz={t(frame.node(NodeRole.FOOTING_TOP).y)}+min({t(s.df1)},{t(s.df2)})={t(ground.ground)}m")
    add("wind.exposure", f"受風高さh={t(frame.bearing_seat.y)}−{t(ground.ground)}={t(ground.exposure)}m")
    for key, label, wind in (("with_train", "1)列車荷重がある場合", result.wind_with_train),
                             ("without_train", "2)列車荷重がない場合", result.wind_without_train)):
        k = f"wind.{key}"
        add(f"{k}.heading", label)
        add(f"{k}.pressure", f"風圧ω1={t(wind.pressure)}kN/m2")
        add(f"{k}.girder", "・桁に作用する風荷重（支承位置）")
        add(f"{k}.h", f"水平力H={t(wind.rows[0].h)}+{t(wind.rows[1].h)}={t(wind.h)}kN")
        add(f"{k}.table", "水平力(kN)高さ(m)モーメント(kN・m)" + "".join(
            ("起点側桁" if r.item is Item.ORIGIN else "終点側桁") + t(r.h) + t(r.y) + t(r.m) for r in wind.rows)
            + f"合計{t(wind.h)}{t(wind.m)}")
        add(f"{k}.pier", "・く体に作用する風荷重（地表面より上）")
        add(f"{k}.segments", "部位上端(m)下端(m)長さ(m)幅（上端）(m)幅（下端）(m)" + "".join(
            PARTS[g.region] + t(g.top) + t(g.bottom) + t(g.length) + t(g.width_top) + t(g.width_bottom)
            for g in wind.pier.segments))
        seen = set()
        for g in wind.pier.segments:
            for name, width, load in zip(WIND[g.region], (g.width_top, g.width_bottom), (g.load_top, g.load_bottom)):
                if name not in seen:
                    seen.add(name)
                    add(f"{k}.{name}", f"{PARTS[g.region]}H{name[1:]}={t(wind.pressure)}×{t(width)}={t(load)}kN/m")
    if result.centrifugal is not None:
        add("centrifugal.heading", f"{item(9)}遠心荷重")
        add("centrifugal.note", f"水平力は列車荷重（9.2{item(5)}）に0600の遠心荷重係数αを乗じ，支承位置から遠心荷重の作用高さyに作用させる．")
        for track in Track:
            table = result.centrifugal.table(track)
            add(f"centrifugal.{track.value}.heading", "・" + names[track])
            add(f"centrifugal.{track.value}", "列車荷重(kN)α水平力(kN)高さ(m)モーメント(kN・m)" + "".join(
                ("起点側" if r.item is Item.ORIGIN else "終点側") + t(r.train) + t(r.coefficient) + t(r.h) + t(r.y)
                + t(r.m) for r in table.rows) + f"合計{t(table.h)}{t(table.m)}")
    # Decision 44: the load diagrams are FEMPython's pages after the heading; the section has no text of its own.
    add("diagrams.heading", "9.3荷重図")
    add("combination.heading", "9.4設計作用の組合せ")
    add("basic.heading", "(1)基本ケース")
    add("basic", "No荷重名称区分バネ" + "".join(
        f"{a.number}{BASIC[a.case.value][0]}{BASIC[a.case.value][1]}{1 if a.spring is SpringTerm.LONG else 2}"
        for a in result.basic_cases))
    add("basic.note", "バネ1は長期，2は短期のフーチング底面のばねを用いる．")
    add("define.heading", "(2)Defineケース")
    width = max(len(d.cases) * len(d.signs) for d in result.define_cases)
    qualifiers = {9: "単線", 11: "安全性・復旧性　単線", 17: "単線"}
    define = "No" + "".join(f"C{i}" for i in range(1, width + 1)) + "記号荷重名称区分"
    for d in result.define_cases:
        name, qualifier, symbol = BASIC[d.cases[0].value]
        define += f"{d.number}" + "".join(str(sign * result.basic(c).number) for sign in d.signs for c in d.cases)
        define += symbol + name + qualifiers.get(d.define.value, qualifier)
    add("define", define)
    add("define.note", "C1・C2は同じDefineで選ぶ基本ケース（単線は上り・下りのいずれか），負の番号は逆向きに作用させることを示す．")
    f = result.factors
    add("factors.heading", "(3)組合せケースと荷重係数")
    add("factors.ultimate", f"安全性・復旧性ρ={t(pier.train.factor_ultimate)}≒{t(f.ultimate)}")
    add("factors.maximum", f"列車最大1.1ρ=1.1×{t(pier.train.factor_ultimate)}={t(f.maximum)}")
    add("factors.service", f"使用性ρ={t(pier.train.factor_service)}≒{t(f.service)}")
    add("factors.service_impact", f"使用性の衝撃0.75ρ=0.75×{t(pier.train.factor_service)}={t(f.service_impact)}")
    remarks = "".join(REMARKS[c.check.value] + ("" if c.loading is None else c.loading.value) for c in result.combinations)
    header = ("No記号荷重名称安全性耐久性・使用性使用性安全性使用性破壊ひび割れ損傷地盤の安定長期短期" + remarks
              + "".join(str(c.number) for c in result.combinations))
    body = "".join(f"{d.number}{BASIC[d.cases[0].value][2]}{BASIC[d.cases[0].value][0]}" + "".join(
        t(c.coefficients[i]) if c.coefficients[i] is not None else "－" for c in result.combinations)
        for i, d in enumerate(result.define_cases))
    add("combination", header + body)
    add("combination.note", "列はDefineケースである．単線の列車荷重・衝撃荷重（遠心荷重）は一つの組合せで同じ線とし，"
                            "車両横荷重・風荷重は正負それぞれを組み合わせる．組合せ7，8，10，11，22，23，24，25の衝撃荷重には，"
                            f"使用性の衝撃係数（3/4を含む）による値にρ={t(f.service)}を乗じる．")
    add("extraction.heading", "(4)抽出ケース")
    labels = ["安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "使用性（損傷）", "安全性（安定）", "長期支持性能",
              "短期支持性能"]
    width = max(len(e.combinations) for e in result.extractions)
    add("extraction", "No名称" + "".join(f"C{i}" for i in range(1, width + 1)) + "".join(
        f"{e.number}{labels[e.number - 1]}" + "".join(map(str, e.combinations)) for e in result.extractions))
    return out


def actual(case: str, result=None) -> dict[str, str]:
    from webpier.reporting.stages.frame_report import plain
    from webpier.reporting.stages.transverse import content

    pier, reaction, transverse, _ = transverse_chain(case)
    units = content(result or transverse, reaction, pier)
    assert len({unit.key for unit in units}) == len(units)
    return {unit.key: squeeze(plain(unit.value)) for unit in units}


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_every_record_prints_the_result_values_at_their_digits_in_order(case: str):
    want = {key: squeeze(value) for key, value in expected(case).items()}
    got = actual(case)
    assert list(got) == list(want)
    for key, value in want.items():
        assert got[key] == value, key


def test_current_input_prints_the_example2_values():
    got = actual("current")
    assert "起点側RBG11530.00-3.800-5814.00" in got["0620/fixed.top"]
    assert got["0620/fixed.n"].endswith("=8299.53kN")
    assert got["0620/lateral.h"] == "水平力H=52.71+58.98=111.69kN"
    assert got["0620/lateral.m"].endswith("=430.01kN・m")
    assert "起点側RBG1272.47-0.020-5.45-3.800" in got["0620/train.up"]
    assert got["0620/wind.with_train.h"] == "水平力H=197.00+108.88=305.88kN"
    assert got["0620/wind.with_train.Hw1"] == "はりHw1=1.5×2.700=4.05kN/m"
    assert "0620/centrifugal.heading" not in got


def test_variants_change_what_is_printed():
    curve, ground = actual("curve"), actual("haunch_ground")
    assert "0620/centrifugal.double" in curve and "遠心荷重複線" in curve["0620/basic"].replace("　", "")
    assert curve["0620/combination"].count("CF") == 2
    assert "柱" not in ground["0620/wind.with_train.segments"][len("部位上端"):]  # the ground cuts the haunch
    assert "0620/wind.with_train.Hw2" in ground


def test_the_report_reads_the_results_not_the_input():
    _, _, result, _ = transverse_chain("current")
    lateral = replace(result.lateral, h=Printed(1.23, 2, "kN"))
    assert actual("current", replace(result, lateral=lateral))["0620/lateral.h"].endswith("=1.23kN")
