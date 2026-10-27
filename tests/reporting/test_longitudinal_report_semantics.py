"""0610 semantics: every printed number is a value of the results at its digits, in Example2 08's order.

The expected records are written here from the LongitudinalResult, the 0600
ReactionResult and the input with this module's own formatter, never by
calling the report. The wording follows Example2 08 pp.8-1..8-11; deliberate
additions (the node/member tables, the formula lines that make every printed
value checkable) are listed in ADDITIONS.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from frame_report_cases import CASES, chain, part_weight, text
from webpier.calc.frame import NodeRole, Region
from webpier.calc.longitudinal import BasicCase, Item, SpringTerm
from webpier.core.printed import Printed
from webpier.calc.reaction.longitudinal import LAYOUT_CASES
from webpier.calc.reaction.train import Layout

ADDITIONS = {
    "0610/model.nodes": "節点座標（Example橋脚 7-2 の節点座標表）",
    "0610/model.members": "部材の端点・剛域・材料",
    "0610/fixed.overlap": "q の載荷区間とはり・ハンチの重複 Δh を式で示す（Example2 は 2.00 のみ）",
    "0610/fixed.overlap.note": "Δh の定義（入力票の記号 H2・H3 は印刷しない）",
    "0610/train.double.origin": "複線の鉛直力 = 単線 × 載荷線数（0600）",
    "0610/impact.service_single": "使用性の衝撃（組合せ 5, 7, 15, 16 で用いる）",
    "0610/factors.maximum": "1.1ρ の計算",
}
REGIONS = {Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.COLUMN_BASE: "柱下端の微小部材",
           Region.FOOTING_UPPER: "フーチング天端～重心", Region.FOOTING_LOWER: "フーチング重心～底面",
           Region.PEDESTAL_ARM: "桁受けまでの剛域", Region.PEDESTAL: "桁受け", Region.GIRDER: "支承から桁までの剛域"}
ROLES = {NodeRole.CAP_TOP: "はり天端", NodeRole.BEAM_BOTTOM: "はり下端", NodeRole.COLUMN_TOP: "柱上端",
         NodeRole.MICRO_TOP: "微小部材上端", NodeRole.FOOTING_TOP: "フーチング天端",
         NodeRole.FOOTING_CENTROID: "フーチング重心", NodeRole.FOOTING_BOTTOM: "フーチング底面",
         NodeRole.PEDESTAL_BASE: "桁受け下端", NodeRole.PEDESTAL_TOP: "桁受け天端",
         NodeRole.GIRDER_ORIGIN: "起点側の桁", NodeRole.GIRDER_END: "終点側の桁"}
UNITS = {"kN": "kN", "kN m": "kN・m", "kN/m": "kN/m", "m": "m", "m2": "m2", "m4": "m4"}


def squeeze(value: str) -> str:
    return re.sub(r"\s+", "", value)


def t(value: Printed, **options) -> str:
    return text(value, **options)


def paren(value: Printed) -> str:
    return f"({t(value)})" if value.value < 0 else t(value)


def u(value: Printed) -> str:
    return UNITS[value.unit]


def figure_texts(frame, pier, reaction) -> str:
    out = [str(node.number) for node in frame.nodes] + [str(member.number) for member in frame.members]
    out += [t(member.height) for member in frame.members if member.height.value > 0]
    out += [t(frame.pier_height), t(frame.node(NodeRole.FOOTING_TOP).y), t(max(frame.nodes, key=lambda n: n.y.value).y)]
    b = pier.substructure.b
    out += [t(b[i]) for i in (7, 8, 9) if b[i].value > 0] + [t(reaction.self_weight.footing_length)]
    out += ["KvKsKr", {"可動": "M", "固定": "F"}[pier.spans.origin.bearing], {"可動": "M", "固定": "F"}[pier.spans.end.bearing]]
    return "".join(out)


def node_rows(frame, springs: bool = True) -> str:
    """With *springs* the footing bottom is the spring node (0610, 0620); 0710 and 0720 show no springs."""
    out = "節点番号X座標(m)Y座標(m)位置"
    for node in frame.nodes:
        out += str(node.number) + t(node.x) + t(node.y) + "・".join(
            name + ("（ばね）" if springs and role is NodeRole.FOOTING_BOTTOM else "")
            for role, name in ROLES.items() if role in node.roles)
    return out


def member_rows(frame) -> str:
    out = "部材番号i端j端高さ(m)水平距離(m)部位断面f'ck(N/mm2)"
    for m in frame.members:
        section = "剛域" if m.section is None else "桁受け" if m.region is Region.PEDESTAL else "柱"
        out += (f"{m.number}{m.start}{m.end}{t(m.height)}{t(m.offset)}{REGIONS[m.region]}{section}"
                + (t(m.material.strength) if m.material else "－"))
    return out


def springs(frame) -> str:
    a, b = frame.support.long_term, frame.support.short_term
    return ("記号安定計算時単位長期短期"
            f"鉛直ばねKv{t(a.kv, thousands=True)}{t(b.kv, thousands=True)}kN/m"
            f"せん断ばねKs{t(a.ks, thousands=True)}{t(b.ks, thousands=True)}kN/m"
            f"回転ばねKr{t(a.kr, thousands=True)}{t(b.kr, thousands=True)}kN・m/rad")


def section(prefix: str, s) -> dict[str, str]:
    return {f"{prefix}.size": f"b={t(s.width)}mh={t(s.depth)}m",
            f"{prefix}.area": f"断面積A={t(s.width)}×{t(s.depth)}={t(s.area)}m2",
            f"{prefix}.inertia": f"断面二次モーメントI=1/12×{t(s.width)}×{t(s.depth)}3={t(s.inertia)}m4"}


def material(prefix: str, label: str, c) -> dict[str, str]:
    return {f"{prefix}.strength": f"{label}f'ck={t(c.strength)}N/mm2",
            f"{prefix}.modulus": f"Ec={t(c.modulus)}×107kN/m2",
            f"{prefix}.table": f"（表のf'ck={t(c.lower.strength)}N/mm2でEc={t(c.lower.modulus)}kN/mm2，"
                               f"f'ck={t(c.upper.strength)}N/mm2でEc={t(c.upper.modulus)}kN/mm2から直線補間）"}


def top(rows, n, m) -> str:
    names = {Item.ORIGIN: "起点側RB", Item.END: "終点側RC", Item.BEAM: "はり"}
    return ("鉛直力(kN)アーム(m)モーメント(kN・m)" + "".join(names[r.item] + t(r.n) + t(r.arm) + t(r.m) for r in rows)
            + f"合計{t(n)}{t(m)}")


def seat(frame, n, m, point) -> str | None:
    e = frame.bearing_offset
    return None if not e.value else f"桁受け天端M={t(m)}−{t(n)}×{paren(e)}={t(point.m)}kN・m"


def seat_tables(add, frame, key, tables, table_text) -> None:
    """D2 by seat as 8.2 / 9.2 print it (decision 81): with a pedestal, the tables with a load (all when none has)
    under ・はり天端 / ・桁受け天端; without one, the beam top under ・橋脚天端に作用する荷重."""
    if frame.pedestal_section is None:
        add(f"{key}.heading", "・橋脚天端に作用する荷重")
    found = [(anchor, table) for anchor, table in tables if table is not None and table.rows]
    for anchor, table in [item for item in found if any(row.n.value for row in item[1].rows)] or found:
        where = key if anchor is NodeRole.CAP_TOP else f"{key}.pedestal"
        if frame.pedestal_section is not None:
            add(f"{where}.seat", "・はり天端" if anchor is NodeRole.CAP_TOP else "・桁受け天端")
        add(where, table_text(table))
        if anchor is NodeRole.PEDESTAL_TOP:
            add(f"{where}.note", pedestal_note(frame))


def pedestal_note(frame) -> str | None:
    """Under a table at the pedestal top off the column axis (decision 81)."""
    off = frame.node(NodeRole.PEDESTAL_TOP).x != frame.node(NodeRole.CAP_TOP).x
    return "（アームは桁受けの中心から）" if off else None


def brake(reaction, case) -> tuple[str, str]:
    forces = reaction.longitudinal.case(case)
    factors = [f.brake_factor for f in (forces.origin, forces.end) if f.brake_factor is not None]
    if not factors:
        return "", ""
    if len({f.value for f in factors}) == 1:
        return f"{t(factors[0])}B", f"{t(factors[0])}B"
    return "B", f"B（起点{t(factors[0])}，終点{t(factors[1])}）"


RAILS = ["0.8LR", "1.0LR", "1.0LR", "1.1LR", "1.0LR", "1.0LR", "1.0LR", "1.0LR"]
REQUIREMENTS = ["使用性", "使用性", "安全性", "安全性", "安全性", "安全性", "復旧性", "復旧性"]
BASIC = [("固定死荷重", "", "D1"), ("付加死荷重", "", "D2"), ("浮力", "高水位", "WP1"), ("浮力", "平水位", "WP2"),
         ("浮力", "低水位", "WP3"), ("雪荷重", "2年確率", "SS2"), ("雪荷重", "10年確率", "SS10"),
         ("雪荷重", "30年確率", "SS30"), ("列車荷重", "単線", "L1"), ("列車荷重", "複線", "L2"),
         ("衝撃荷重", "安全性・復旧性　単線", "I1"), ("衝撃荷重", "安全性・復旧性　複線", "I2")]


def horizontal_names(result, reaction):
    found = []
    for index, row in enumerate(result.horizontal):
        short, full = brake(reaction, row.case)
        rail = RAILS[index]
        name = "ﾛﾝｸﾞﾚｰﾙ+制動" if short else "ﾛﾝｸﾞﾚｰﾙ縦荷重"
        found.append((name, REQUIREMENTS[index], rail + (f" + {full}" if full else ""),
                      rail.removesuffix("LR") + "LR" + (f"+{short}" if short else ""),
                      rail + (f" + {short}" if short else "")))
    return found


def dead_records(add, pier, reaction, frame, fixed, additional, number: int = 1) -> None:
    """The records of (1) 固定死荷重 and (2) 付加死荷重 as 8.2 prints them; 10.2 prints the same (decision 78)."""
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
    add("fixed.top", top(fixed.table.rows, fixed.table.n, fixed.table.m))
    add("fixed.overlap", f"重複区間Δh={t(s.h[2])}+{t(s.h[3])}={t(fixed.overlap)}m")
    add("fixed.overlap.note", "ここに、Δh：はりの高さ＋ハンチの高さ（柱のqと重なる長さ）")
    add("fixed.n", f"鉛直力N={t(fixed.table.n)}−{t(fixed.column_q)}×{t(fixed.overlap)}={t(fixed.n)}kN")
    add("fixed.m", f"モーメントM={t(fixed.m)}kN・m")
    if fixed.pedestal is not None:
        add("fixed.pedestal.seat", "・桁受け天端")
        add("fixed.pedestal.top", top(fixed.pedestal.rows, fixed.pedestal.n, fixed.pedestal.m))
        add("fixed.pedestal.note", pedestal_note(frame))
    add("additional.heading", f"({number + 1})付加死荷重")
    soil = additional.soil
    add("additional.soil", f"載荷土P={part_weight(sw.overburden)}={t(soil.n)}kN")
    if soil.arm.value:
        add("additional.soil.moment", f"MP={t(soil.n)}×{paren(soil.arm)}={t(soil.m)}kN・m")
    seat_tables(add, frame, "additional.top", ((NodeRole.CAP_TOP, additional.table),
                                               (NodeRole.PEDESTAL_TOP, additional.pedestal)),
                lambda table: top(table.rows, table.n, table.m))


def expected(case: str) -> dict[str, str]:
    pier, reaction, result, _ = chain(case)
    frame, s, sw = result.frame, pier.substructure, reaction.self_weight
    out: dict[str, str] = {}

    def add(key: str, value: str | None) -> None:
        if value is not None:
            out["0610/" + key] = value

    def item(number: int) -> str:  # decision 69: without snow (4) 雪荷重 is not printed and the items move up
        return f"({number if result.snow is not None else number - 1})"

    add("title", "§8.線路方向の計算（地震時以外）")
    add("model.heading", "8.1検討モデル")
    add("model.figure.heading", "(1)骨組図")
    add("model.figure", figure_texts(frame, pier, reaction))
    add("model.figure.note", "太線は剛域を示す．Ⓜは可動支承，Ⓕは固定支承．寸法の単位はm．")
    add("model.springs.caption", "フーチング底面のばね")
    add("model.springs", springs(frame))
    add("model.nodes.heading", "(2)節点と部材")
    add("model.nodes", node_rows(frame))
    add("model.members", member_rows(frame))
    add("section.heading", "(3)部材の断面諸元")
    add("section.column.heading", "1)柱（はり・ハンチを含む）")
    out.update({"0610/" + k: v for k, v in section("section.column", frame.column_section).items()})
    number = 2
    if frame.pedestal_section is not None:
        add("section.pedestal.heading", "2)桁受け")
        out.update({"0610/" + k: v for k, v in section("section.pedestal", frame.pedestal_section).items()})
        number = 3
    add("section.footing.heading", f"{number})フーチング")
    add("section.footing.rigid", "フーチングはすべて剛域とする．")
    add("section.footing.centroid", f"断面の重心位置yG={t(frame.node(NodeRole.FOOTING_CENTROID).y)}m")
    add("section.material.heading", f"{number + 1})弾性係数")
    elastic = {m.region for m in frame.members if not m.rigid}
    key, label = ("body", "く体") if elastic & {Region.BEAM, Region.HAUNCH} else ("column", "柱")
    out.update({"0610/" + k: v for k, v in material(f"section.material.{key}", label, frame.materials.column).items()})
    add("actions.heading", "8.2作用の計算")
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
            snow = result.snow[index]
            add(f"snow.{key}", top(snow.rows, snow.n, snow.m))
            add(f"snow.{key}.seat", seat(frame, snow.n, snow.m, result.basic(case_).points[0]))
    add("train.heading", f"{item(5)}列車荷重")
    # decision 102: the train of ①, ② and ③ in turn; ①'s keys as before, ② and ③ add the placing
    placings = [(Layout.BOTH, result.train, result.impact),
                *((placed.layout, placed.train, placed.impact) for placed in result.one_girder)]
    for index, (layout, trains, _) in enumerate(placings):
        key = "train" if layout is Layout.BOTH else f"train.{layout.name.lower()}"
        single, double = trains.single, trains.double
        add(f"{key}.single.heading", f"{2 * index + 1})単線載荷（{layout.value}）")
        add(f"{key}.single", top(single.rows, single.n, single.m))
        add(f"{key}.single.seat", seat(frame, single.n, single.m,
                                       result.basic(BasicCase.TRAIN_SINGLE, layout).points[0]))
        add(f"{key}.double.heading", f"{2 * index + 2})複線載荷（{layout.value}）")
        add(f"{key}.double.origin", f"載荷線数を乗じるRB={t(single.row(Item.ORIGIN).n)}×"
                                    f"{t(reaction.dead.origin.track_total)}={t(double.row(Item.ORIGIN).n)}kN")
        add(f"{key}.double.end", f"RC={t(single.row(Item.END).n)}×{t(reaction.dead.end.track_total)}="
                                 f"{t(double.row(Item.END).n)}kN")
        add(f"{key}.double", top(double.rows, double.n, double.m))
        add(f"{key}.double.seat", seat(frame, double.n, double.m,
                                       result.basic(BasicCase.TRAIN_DOUBLE, layout).points[0]))
    add("impact.heading", f"{item(6)}衝撃荷重")
    add("impact.note", "鉛直力は列車荷重に橋脚く体の衝撃係数を乗じた値とする．")
    number = 0
    for layout, trains, impact in placings:
        for key, label, table, train, case_ in (
                ("ultimate_single", "単線載荷（安全性・復旧性", impact.ultimate_single, trains.single,
                 BasicCase.IMPACT_SINGLE),
                ("ultimate_double", "複線載荷（安全性・復旧性", impact.ultimate_double, trains.double,
                 BasicCase.IMPACT_DOUBLE),
                ("service_single", "単線載荷（使用性", impact.service_single, trains.single, None),
                ("service_double", "複線載荷（使用性", impact.service_double, trains.double, None)):
            number += 1
            name = f"impact.{key}" if layout is Layout.BOTH else f"impact.{key}.{layout.name.lower()}"
            add(f"{name}.heading", f"{number}){label}，{layout.value}）")
            names = {Item.ORIGIN: "起点側RB", Item.END: "終点側RC"}
            add(name, "列車荷重(kN)衝撃係数鉛直力(kN)アーム(m)モーメント(kN・m)"
                + "".join(names[r.item] + t(r.train) + t(r.coefficient) + t(r.n) + t(r.arm) + t(r.m) for r in table.rows)
                + f"合計{t(train.n)}{t(table.n)}{t(table.m)}")
            if case_ is not None:
                point = result.basic(case_, layout).points[0]
            else:  # the serviceability impact as the serviceability combinations of the placing put it on the frame
                wanted = BasicCase.IMPACT_SINGLE if key == "service_single" else BasicCase.IMPACT_DOUBLE
                point = next(c.source.points[0] for combo in result.combinations for c in combo.components
                             if c.case is wanted and c.basis.value == "service_impact" and combo.layout is layout)
            add(f"{name}.seat", seat(frame, table.n, table.m, point))
    add("horizontal.heading", f"{item(7)}水平荷重")
    add("horizontal.summary.heading", "1)支承に働く水平荷重のまとめ")
    groups = {"使用性": "使用性", "安全性": "安全性（破壊）", "復旧性": "復旧性"}
    rows, previous = "荷　重　種　別起点桁(kN)終点桁(kN)合計(kN)", ""
    marks = {Layout.BOTH: "①", Layout.ORIGIN: "②", Layout.END: "③"}
    for (name, requirement, full, _, _), row in zip(horizontal_names(result, reaction), result.horizontal):
        listed = [(row, None)]
        if row.case in LAYOUT_CASES:  # ①, ② and ③ of a case with the train or braking (decision 102)
            listed = [(row, Layout.BOTH), *((next(r for r in placed.horizontal if r.case is row.case), placed.layout)
                                            for placed in result.one_girder)]
        for shown, layout in listed:
            rows += ((groups[requirement] if requirement != previous else "") + ("" if layout is None else marks[layout])
                     + full + t(shown.origin) + t(shown.end) + t(shown.total))
            previous = requirement
    add("horizontal", rows)
    # Decision 44: the load diagrams are FEMPython's pages after the heading; the section has no text of its own.
    add("diagrams.heading", "8.3荷重図")
    add("combination.heading", "8.4設計作用の組合せ")
    add("basic.heading", "(1)基本ケース")
    names = [(n, q) for n, q, _ in BASIC] + [(n, f"{r}　{full}") for n, r, full, _, _ in horizontal_names(result, reaction)]

    short = {Layout.BOTH: "両側", Layout.ORIGIN: "起点側", Layout.END: "終点側"}  # 備考 (decision 102)
    add("basic", "No荷重名称区分備考バネ" + "".join(
        f"{a.number}{''.join(names[a.case.value - 1])}{'' if a.layout is None else short[a.layout]}"
        f"{1 if a.spring is SpringTerm.LONG else 2}" for a in result.basic_cases))
    add("basic.note", "バネ1は長期，2は短期のフーチング底面のばねを用いる．")
    add("define.heading", "(2)Defineケース")
    symbols = [sym for _, _, sym in BASIC] + [sym for _, _, _, sym, _ in horizontal_names(result, reaction)]
    qualifiers = [q for _, q, _ in BASIC] + [r for _, r, _, _, _ in horizontal_names(result, reaction)]
    placings = {Layout.BOTH: "1", Layout.ORIGIN: "2", Layout.END: "3"}

    def placed_symbol(case, layout):  # L1-1 of ① (Example橋脚4 表2.3.1), 1.0LR+1.23B-2 of ②
        symbol = symbols[case.value - 1]
        return symbol if layout is None else f"{symbol}-{placings[layout]}"

    add("define", "NoC1C2C3記号荷重名称区分" + "".join(
        f"{d.number}{result.basic(d.case, d.layout or Layout.BOTH).number}{-d.number if -1 in d.signs else ''}"
        f"{placed_symbol(d.case, d.layout)}{names[d.case.value - 1][0]}{qualifiers[d.case.value - 1]}"
        for d in result.define_cases))
    add("define.note", "C2は水平荷重を逆向きにも作用させることを示す．")
    add("factors.heading", "(3)組合せケースと荷重係数")
    f, train = result.factors, pier.train
    add("factors.ultimate", f"安全性・復旧性ρ={t(train.factor_ultimate)}≒{t(f.ultimate)}")
    add("factors.maximum", f"列車最大1.1ρ=1.1×{t(train.factor_ultimate)}={t(f.maximum)}")
    add("factors.service", f"使用性ρ={t(train.factor_service)}≒{t(f.service)}")
    add("factors.service_impact", f"使用性の衝撃0.75ρ=0.75×{t(train.factor_service)}={t(f.service_impact)}")
    add("combination", combination_text(result, placed_symbol, names))
    services = [str(c.number) for c in result.combinations if any(k.basis.value == "service_impact" for k in c.components)]
    add("combination.note", f"組合せ{'，'.join(services)}の衝撃荷重には，使用性の衝撃係数（3/4を含む）による8.2{item(6)}3)，"
                            f"4)の値にρ={t(f.service)}を乗じる．")
    add("extraction.heading", "(4)抽出ケース")
    width = min(max(len(e.combinations) for e in result.extractions), 9)  # 9 numbers a line, then the next line
    labels = ["安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "使用性（損傷）", "安全性（安定）", "長期支持性能",
              "短期支持性能"]
    add("extraction", "No名称" + "".join(f"C{i}" for i in range(1, width + 1)) + "".join(
        f"{e.number}{labels[e.number - 1]}" + "".join(map(str, e.combinations)) for e in result.extractions))
    return out


# The 16 checks of 8-10 as Example2 heads them: requirement, performance item, remark
CHECK_HEADS = [("安全性", "破壊", "列車最大"), ("安全性", "破壊", "制動最大"), ("安全性", "破壊", "ﾛﾝｸﾞ最大"),
               ("安全性", "破壊", "雪最大"), ("耐久性・使用性", "ひび割れ", "縁応力度"), ("耐久性・使用性", "ひび割れ", "永久荷重"),
               ("耐久性・使用性", "ひび割れ", "変動荷重"), ("使用性", "損傷", "列車最大"), ("使用性", "損傷", "雪最大"),
               ("安全性", "地盤の安定", "列車最大"), ("安全性", "地盤の安定", "制動最大"), ("安全性", "地盤の安定", "ﾛﾝｸﾞ最大"),
               ("安全性", "地盤の安定", "雪最大"), ("使用性", "長期", ""), ("使用性", "短期", ""), ("使用性", "短期", "")]
SHORT_PLACINGS = {Layout.BOTH: "両側", Layout.ORIGIN: "起点側", Layout.END: "終点側"}


def merged(texts) -> str:
    """A header row: neighbours with the same text share one cell."""
    return "".join(text for index, text in enumerate(texts) if not index or text != texts[index - 1])


def combination_text(result, placed_symbol, names) -> str:
    heads = [CHECK_HEADS[c.check.value - 1] for c in result.combinations]
    remarks = [head[2] + ("" if c.layout is None else SHORT_PLACINGS[c.layout]) for head, c in
               zip(heads, result.combinations)]  # decision 102: a check with the train names its placing
    header = ("No記号荷重名称" + merged([head[0] for head in heads]) + merged([head[1] for head in heads])
              + merged(remarks) + "".join(str(c.number) for c in result.combinations))
    body = ""
    for row, action in enumerate(result.basic_cases):  # the coefficients by the cases made (decision 69)
        body += f"{action.number}{placed_symbol(action.case, action.layout)}{names[action.case.value - 1][0]}" + "".join(
            t(c.coefficients[row]) if c.coefficients[row] is not None else "－" for c in result.combinations)
    return header + body


def actual(case: str) -> dict[str, str]:
    from webpier.reporting.stages.longitudinal import semantic_records

    pier, reaction, result, _ = chain(case)
    records = semantic_records(result, reaction, pier)
    ids = [record["id"] for record in records]
    assert len(ids) == len(set(ids))
    return {record["id"]: squeeze(record["text"]) for record in records}


@pytest.mark.parametrize("case", list(CASES))
def test_every_record_prints_the_result_values_at_their_digits_in_order(case: str):
    want = {key: squeeze(value) for key, value in expected(case).items()}
    got = actual(case)
    assert list(got) == list(want)
    for key in want:
        assert got[key] == want[key], key


def test_current_input_prints_the_example2_values():
    got = actual("current")
    assert "5740.00-0.325-1865.50" in got["0610/fixed.top"]
    assert got["0610/fixed.column"].endswith("=297.68kN/m")
    assert got["0610/fixed.footing"].endswith("=4167.45kN")
    assert got["0610/fixed.n"].endswith("=8299.53kN") and got["0610/fixed.m"] == "モーメントM=-610.00kN・m"
    assert got["0610/additional.soil"].endswith("=1830.60kN")
    assert got["0610/buoyancy.high"].endswith("=-2381.40kN")
    assert got["0610/section.column.inertia"].endswith("=7.38113m4")
    assert got["0610/section.material.body.modulus"] == "Ec=2.65×107kN/m2"
    assert "12,788,24425,576,488" in got["0610/model.springs"]
    assert "0.8LR160.0080.00240.00" in got["0610/horizontal"]
    assert got["0610/factors.maximum"] == "列車最大1.1ρ=1.1×1.231=1.35"
    for key in ADDITIONS:
        assert key in got


def test_variants_change_what_is_printed():
    current, pedestal, asymmetric, merged = (actual(case) for case in ("current", "pedestal", "asymmetric", "merged"))
    # Decision 80: the pedestal q, the beam top and the pedestal top each with its table, D2 at the pedestal top only.
    assert "0610/fixed.pedestal" in pedestal and "0610/section.pedestal.inertia" in pedestal
    assert pedestal["0610/fixed.top.seat"] == "・はり天端" and "0610/fixed.top.seat" not in current
    assert pedestal["0610/fixed.pedestal.note"] == "（アームは桁受けの中心から）"
    assert "0610/additional.top.pedestal" in pedestal and "0610/additional.top" not in pedestal
    # Decision 77: Ds 3013.33, 1 − 3013.33/(1134.78 + 8380 + 3013.33) = 0.759; 0.167 × 0.759 = 0.127 and
    # 0.391 × 0.759 = 0.297; N = 544.94 × 0.127 + 589.84 × 0.297 = 69.21 + 175.18 = 244.39 and
    # M = 69.21 × −0.325 + 175.18 × 0.675 = −22.49 + 118.25 = 95.76; 95.76 − 244.39 × 0.175 = 52.99.
    assert pedestal["0610/impact.service_double.seat"].startswith("桁受け天端M=95.76−244.39×0.175=")
    assert "0610/fixed.footing.moment" in asymmetric and "0610/fixed.footing.moment" not in current
    assert "柱上端" in merged["0610/model.nodes"] and merged["0610/model.nodes"].count("はり天端・はり下端・柱上端") == 1


def test_the_report_reads_the_results_not_the_input():
    pier, reaction, result, _ = chain("current")
    sentinel = replace(result, fixed=replace(result.fixed, column_q=Printed(123.45, 2, "kN/m"),
                                             n=Printed(1.11, 2, "kN")),
                       factors=replace(result.factors, maximum=Printed(9.99, 2, "")))
    from webpier.reporting.stages.longitudinal import semantic_records

    got = {r["id"]: squeeze(r["text"]) for r in semantic_records(sentinel, reaction, pier)}
    assert got["0610/fixed.column"].endswith("=123.45kN/m")
    assert got["0610/fixed.n"] == "鉛直力N=9103.27−123.45×2.700=1.11kN"
    assert got["0610/factors.maximum"].endswith("=9.99")


def test_unsupported_nodes_and_duplicate_keys_are_rejected():
    from webpier.reporting.stages.frame_report import Manuscript, document, plain

    with pytest.raises(TypeError, match="Unsupported"):
        plain(object())
    m = Manuscript("x/")
    m.paragraph("a", "一")
    m.paragraph("a", "二")
    with pytest.raises(ValueError, match="重複"):
        document(m.units)
