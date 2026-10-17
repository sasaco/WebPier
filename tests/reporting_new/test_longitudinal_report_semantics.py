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

from frame_report_cases import CASES, chain, text
from webpier.calc.frame import NodeRole, Region
from webpier.calc.longitudinal import BasicCase, Item, SpringTerm
from webpier.core.printed import Printed

ADDITIONS = {
    "0610/model.nodes": "節点座標（Example橋脚 7-2 の節点座標表）",
    "0610/model.members": "部材の端点・剛域・材料",
    "0610/fixed.overlap": "q の載荷区間とはりの重複 H2 + H3 を式で示す（Example2 は 2.00 のみ）",
    "0610/train.double.origin": "複線の鉛直力 = 単線 × 載荷線数（0600）",
    "0610/impact.service_single": "使用性の衝撃（組合せ 5, 7, 15, 16 で用いる）",
    "0610/factors.maximum": "1.1ρ の計算",
}
REGIONS = {Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.COLUMN_BASE: "柱下端の微小部材",
           Region.FOOTING_UPPER: "フーチング天端～重心", Region.FOOTING_LOWER: "フーチング重心～底面",
           Region.PEDESTAL_ARM: "桁受けまでの剛域", Region.PEDESTAL: "桁受け"}
ROLES = {NodeRole.CAP_TOP: "はり天端", NodeRole.BEAM_BOTTOM: "はり下端", NodeRole.COLUMN_TOP: "柱上端",
         NodeRole.MICRO_TOP: "微小部材上端", NodeRole.FOOTING_TOP: "フーチング天端",
         NodeRole.FOOTING_CENTROID: "フーチング重心", NodeRole.FOOTING_BOTTOM: "フーチング底面（ばね）",
         NodeRole.PEDESTAL_BASE: "桁受け下端", NodeRole.PEDESTAL_TOP: "桁受け天端"}
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
    out += [t(frame.node(NodeRole.FOOTING_TOP).y), t(max(frame.nodes, key=lambda n: n.y.value).y)]
    b = pier.substructure.b
    out += [t(b[i]) for i in (7, 8, 9) if b[i].value > 0] + [t(reaction.self_weight.footing_length)]
    out += ["KvKsKr", {"可動": "M", "固定": "F"}[pier.spans.origin.bearing], {"可動": "M", "固定": "F"}[pier.spans.end.bearing]]
    return "".join(out)


def node_rows(frame) -> str:
    out = "節点番号X座標(m)Y座標(m)位置"
    for node in frame.nodes:
        out += str(node.number) + t(node.x) + t(node.y) + "・".join(name for role, name in ROLES.items()
                                                                    if role in node.roles)
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
    names = {Item.ORIGIN: "起点側RB", Item.END: "終点側RC", Item.PEDESTAL: "桁受け", Item.BEAM: "はり"}
    return ("鉛直力(kN)アーム(m)モーメント(kN・m)" + "".join(names[r.item] + t(r.n) + t(r.arm) + t(r.m) for r in rows)
            + f"合計{t(n)}{t(m)}")


def seat(frame, n, m, point) -> str | None:
    e = frame.bearing_offset
    return None if not e.value else f"桁受け天端M={t(m)}−{t(n)}×{paren(e)}={t(point.m)}kN・m"


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


def point_lines(points, horizontal: bool) -> str:
    anchors = {p.anchor for p in points}
    top_h = any(p.h.value for p in points if p.anchor in (NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP))
    out = ""
    for p in points:
        if p.anchor in (NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP):
            prime = "'" if p.anchor is NodeRole.CAP_TOP and NodeRole.PEDESTAL_TOP in anchors else ""
            names = {"n": "N" + prime, "m": "M" + prime, "h": "H" + prime}
        else:
            names = {"n": "P", "m": "MP", "h": "HP" if top_h else "H"}
        listed = [c for c in "nmh" if getattr(p, c).value] or (["h"] if horizontal else ["n"])
        for c in listed:
            value = getattr(p, c)
            out += f"{names[c]}={t(value)}{u(value)}"
    return out


def glyph_labels(points, line_loads, horizontal: bool) -> str:
    anchors = {p.anchor for p in points}
    top_h = any(p.h.value for p in points if p.anchor in (NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP))
    out = ""
    for p in points:
        if p.anchor in (NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP):
            prime = "'" if p.anchor is NodeRole.CAP_TOP and NodeRole.PEDESTAL_TOP in anchors else ""
            names = {"n": "N" + prime, "m": "M" + prime, "h": "H" + prime}
        else:
            names = {"n": "P", "m": "MP", "h": "HP" if top_h else "H"}
        out += "".join(names[c] for c in ([c for c in "nmh" if getattr(p, c).value] or (["h"] if horizontal else ["n"])))
    return out + "".join("q" for line in line_loads if line.n.value)


def expected(case: str) -> dict[str, str]:
    pier, reaction, result, _ = chain(case)
    frame, s, sw = result.frame, pier.substructure, reaction.self_weight
    out: dict[str, str] = {}

    def add(key: str, value: str | None) -> None:
        if value is not None:
            out["0610/" + key] = value

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
    fixed = result.fixed
    add("actions.heading", "8.2作用の計算")
    add("fixed.heading", "(1)固定死荷重")
    add("fixed.column", f"柱q={t(s.w[6])}×{t(s.b[6])}×{t(s.unit_weight_body)}={t(fixed.column_q)}kN/m")
    add("fixed.footing", f"フーチングP={t(sw.footing.unit_weight)}×{t(sw.footing.volume)}={t(fixed.footing.n)}kN")
    if fixed.footing.arm.value:
        add("fixed.footing.moment", f"MP={t(fixed.footing.n)}×{paren(fixed.footing.arm)}={t(fixed.footing.m)}kN・m")
    add("fixed.top.heading", "・橋脚天端に作用する荷重")
    if s.h[1].value > 0:
        add("fixed.top.pedestal", f"桁受けN={t(sw.pedestal.unit_weight)}×{t(sw.pedestal.volume)}="
                                  f"{t(fixed.table.row(Item.PEDESTAL).n)}kN")
    add("fixed.top.beam", f"はり・ハンチN={t(sw.beam.unit_weight)}×{t(sw.beam.volume)}={t(fixed.table.row(Item.BEAM).n)}kN")
    add("fixed.top", top(fixed.table.rows, fixed.table.n, fixed.table.m))
    add("fixed.overlap", f"重複区間H2+H3={t(s.h[2])}+{t(s.h[3])}={t(fixed.overlap)}m")
    add("fixed.n", f"鉛直力N={t(fixed.table.n)}−{t(fixed.column_q)}×{t(fixed.overlap)}={t(fixed.n)}kN")
    add("fixed.m", f"モーメントM={t(fixed.m)}kN・m")
    if frame.bearing_offset.value:
        d1 = result.basic(BasicCase.D1).points
        seat_point = next(p for p in d1 if p.anchor is NodeRole.PEDESTAL_TOP)
        cap = next(p for p in d1 if p.anchor is NodeRole.CAP_TOP)
        bearings = [r for r in fixed.table.rows if r.item in (Item.ORIGIN, Item.END)]
        body = [r for r in fixed.table.rows if r.item not in (Item.ORIGIN, Item.END)]
        add("fixed.seat.heading", "・桁受け天端とはり天端への載荷")
        add("fixed.seat.n", "桁受け天端N=" + "+".join(t(r.n) for r in bearings) + f"={t(seat_point.n)}kN")
        add("fixed.seat.m", "M=" + "+".join(t(r.m) if i == 0 else paren(r.m) for i, r in enumerate(bearings))
            + f"−{t(seat_point.n)}×{paren(frame.bearing_offset)}={t(seat_point.m)}kN・m")
        add("fixed.cap.n", "はり天端N'=" + "+".join(t(r.n) for r in body)
            + f"−{t(fixed.column_q)}×{t(fixed.overlap)}={t(cap.n)}kN")
        add("fixed.cap.m", "M'=" + "+".join(t(r.m) if i == 0 else paren(r.m) for i, r in enumerate(body))
            + f"={t(cap.m)}kN・m")
    add("additional.heading", "(2)付加死荷重")
    soil = result.additional.soil
    add("additional.soil", f"載荷土P={t(sw.overburden.unit_weight)}×{t(sw.overburden.volume)}={t(soil.n)}kN")
    if soil.arm.value:
        add("additional.soil.moment", f"MP={t(soil.n)}×{paren(soil.arm)}={t(soil.m)}kN・m")
    add("additional.top.heading", "・橋脚天端に作用する荷重")
    table = result.additional.table
    add("additional.top", top(table.rows, table.n, table.m))
    add("additional.top.seat", seat(frame, table.n, table.m, result.basic(BasicCase.D2).points[0]))
    add("buoyancy.heading", "(3)浮力")
    for (key, label, suffix), row, water in zip((("high", "高水位", "1"), ("normal", "平水位", "2"), ("low", "低水位", "3")),
                                                result.buoyancy, (sw.buoyancy_high, sw.buoyancy_normal, sw.buoyancy_low)):
        add(f"buoyancy.{key}", f"{label}ω{suffix}={t(water.body.unit_weight)}×{t(water.body.volume)}={t(row.n)}kN")
        if row.arm.value:
            add(f"buoyancy.{key}.moment", f"MP={t(row.n)}×{paren(row.arm)}={t(row.m)}kN・m")
    add("snow.heading", "(4)雪荷重")
    for index, (key, label, case_) in enumerate((("2", "1)2年確率", BasicCase.SNOW2), ("10", "2)10年確率", BasicCase.SNOW10),
                                                 ("30", "3)30年確率", BasicCase.SNOW30))):
        add(f"snow.{key}.heading", label)
        snow = result.snow[index]
        add(f"snow.{key}", top(snow.rows, snow.n, snow.m))
        add(f"snow.{key}.seat", seat(frame, snow.n, snow.m, result.basic(case_).points[0]))
    add("train.heading", "(5)列車荷重")
    add("train.single.heading", "1)単線載荷")
    single, double = result.train.single, result.train.double
    add("train.single", top(single.rows, single.n, single.m))
    add("train.single.seat", seat(frame, single.n, single.m, result.basic(BasicCase.TRAIN_SINGLE).points[0]))
    add("train.double.heading", "2)複線載荷")
    add("train.double.origin", f"載荷線数を乗じるRB={t(single.row(Item.ORIGIN).n)}×{t(reaction.dead.origin.track_total)}="
                               f"{t(double.row(Item.ORIGIN).n)}kN")
    add("train.double.end", f"RC={t(single.row(Item.END).n)}×{t(reaction.dead.end.track_total)}={t(double.row(Item.END).n)}kN")
    add("train.double", top(double.rows, double.n, double.m))
    add("train.double.seat", seat(frame, double.n, double.m, result.basic(BasicCase.TRAIN_DOUBLE).points[0]))
    add("impact.heading", "(6)衝撃荷重")
    add("impact.note", "鉛直力は列車荷重に桁の衝撃係数を乗じた値とする．")
    impact = result.impact
    for key, label, table, train, case_ in (
            ("ultimate_single", "1)単線載荷（安全性・復旧性）", impact.ultimate_single, single, BasicCase.IMPACT_SINGLE),
            ("ultimate_double", "2)複線載荷（安全性・復旧性）", impact.ultimate_double, double, BasicCase.IMPACT_DOUBLE),
            ("service_single", "3)単線載荷（使用性）", impact.service_single, single, None),
            ("service_double", "4)複線載荷（使用性）", impact.service_double, double, None)):
        add(f"impact.{key}.heading", label)
        names = {Item.ORIGIN: "起点側RB", Item.END: "終点側RC"}
        add(f"impact.{key}", "列車荷重(kN)衝撃係数鉛直力(kN)アーム(m)モーメント(kN・m)"
            + "".join(names[r.item] + t(r.train) + t(r.coefficient) + t(r.n) + t(r.arm) + t(r.m) for r in table.rows)
            + f"合計{t(train.n)}{t(table.n)}{t(table.m)}")
        if case_ is not None:
            add(f"impact.{key}.seat", seat(frame, table.n, table.m, result.basic(case_).points[0]))
    add("horizontal.heading", "(7)水平荷重")
    add("horizontal.summary.heading", "1)支承に働く水平荷重のまとめ")
    groups = {"使用性": "使用性", "安全性": "安全性（破壊）", "復旧性": "復旧性"}
    rows, previous = "荷　重　種　別起点桁(kN)終点桁(kN)合計(kN)", ""
    for (name, requirement, full, _, _), row in zip(horizontal_names(result, reaction), result.horizontal):
        rows += (groups[requirement] if requirement != previous else "") + full + t(row.origin) + t(row.end) + t(row.total)
        previous = requirement
    add("horizontal", rows)
    add("diagrams.heading", "8.3荷重図")
    add("diagrams.note", "鉛直力N・Pは下向き，水平力Hは終点側（右向き），モーメントMは時計回りを正とし，"
                         "矢印は作用の向きを示す．N'，M'ははり天端の荷重を示す．")
    titles = [q for _, q, _ in BASIC] + [f"{r}　{short}" for _, r, _, _, short in horizontal_names(result, reaction)]
    for key, name, numbers in (("d1", "固定死荷重（D1）", (1,)), ("d2", "付加死荷重（D2）", (2,)),
                               ("buoyancy", "浮力（Wp）", (3, 4, 5)), ("snow", "雪荷重（Ss）", (6, 7, 8)),
                               ("train", "列車荷重（L）", (9, 10)), ("impact", "衝撃荷重（I）", (11, 12)),
                               ("horizontal", "水平荷重（LR+B）", tuple(range(13, 21)))):
        actions = [result.basic_cases[n - 1] for n in numbers]
        span = f"Case{numbers[0]}" if len(numbers) == 1 else f"Case{numbers[0]}～{numbers[-1]}"
        add(f"diagrams.{key}.title", span + name)
        lines = ""
        for action in actions:
            if len(actions) > 1:
                lines += f"Case{action.case.value}{titles[action.case.value - 1]}"
            lines += point_lines(action.points, action.horizontal)
            lines += "".join(f"q={t(line.n)}kN/m" for line in action.line_loads if line.n.value)
        add(f"diagrams.{key}", glyph_labels(actions[0].points, actions[0].line_loads, actions[0].horizontal) + lines)
    add("combination.heading", "8.4設計作用の組合せ")
    add("basic.heading", "(1)基本ケース")
    names = [(n, q) for n, q, _ in BASIC] + [(n, f"{r}　{full}") for n, r, full, _, _ in horizontal_names(result, reaction)]
    add("basic", "No荷重名称区分バネ" + "".join(
        f"{a.case.value}{names[i][0]}{names[i][1]}{1 if a.spring is SpringTerm.LONG else 2}"
        for i, a in enumerate(result.basic_cases)))
    add("basic.note", "バネ1は長期，2は短期のフーチング底面のばねを用いる．")
    add("define.heading", "(2)Defineケース")
    symbols = [sym for _, _, sym in BASIC] + [sym for _, _, _, sym, _ in horizontal_names(result, reaction)]
    qualifiers = [q for _, q, _ in BASIC] + [r for _, r, _, _, _ in horizontal_names(result, reaction)]
    add("define", "NoC1C2C3記号荷重名称区分" + "".join(
        f"{d.number}{d.case.value}{-d.number if -1 in d.signs else ''}{symbols[i]}{names[i][0]}{qualifiers[i]}"
        for i, d in enumerate(result.define_cases)))
    add("define.note", "C2は水平荷重を逆向きにも作用させることを示す．")
    add("factors.heading", "(3)組合せケースと荷重係数")
    f, train = result.factors, pier.train
    add("factors.ultimate", f"安全性・復旧性ρ={t(train.factor_ultimate)}≒{t(f.ultimate)}")
    add("factors.maximum", f"列車最大1.1ρ=1.1×{t(train.factor_ultimate)}={t(f.maximum)}")
    add("factors.service", f"使用性ρ={t(train.factor_service)}≒{t(f.service)}")
    add("factors.service_impact", f"使用性の衝撃0.75ρ=0.75×{t(train.factor_service)}={t(f.service_impact)}")
    add("combination", combination_text(result, symbols, names))
    add("combination.note", "組合せ5，7，15，16の衝撃荷重には，使用性の衝撃係数（3/4を含む）による8.2(6)3)，4)の値に"
                            f"ρ={t(f.service)}を乗じる．")
    add("extraction.heading", "(4)抽出ケース")
    width = max(len(e.combinations) for e in result.extractions)
    labels = ["安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "復旧性（損傷）", "安全性（安定）", "長期支持性能",
              "短期支持性能"]
    add("extraction", "No名称" + "".join(f"C{i}" for i in range(1, width + 1)) + "".join(
        f"{e.number}{labels[e.number - 1]}" + "".join(map(str, e.combinations)) for e in result.extractions))
    return out


def combination_text(result, symbols, names) -> str:
    header = ("No記号荷重名称安全性耐久性・使用性復旧性安全性使用性破壊ひび割れ損傷地盤の安定長期短期"
              "列車最大制動最大ﾛﾝｸﾞ最大雪最大縁応力度永久荷重変動荷重列車最大雪最大列車最大制動最大ﾛﾝｸﾞ最大雪最大"
              + "".join(str(c.number) for c in result.combinations))
    body = ""
    for action in result.basic_cases:
        index = action.case.value - 1
        body += f"{action.case.value}{symbols[index]}{names[index][0]}" + "".join(
            t(c.coefficients[index]) if c.coefficients[index] is not None else "－" for c in result.combinations)
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
    assert "0610/fixed.seat.m" in pedestal and "0610/section.pedestal.inertia" in pedestal
    assert "0610/additional.top.seat" in pedestal and "0610/additional.top.seat" not in current
    assert "0610/fixed.footing.moment" in asymmetric and "0610/fixed.footing.moment" not in current
    assert "柱上端" in merged["0610/model.nodes"] and merged["0610/model.nodes"].count("はり天端・はり下端・柱上端") == 1
    assert pedestal["0610/diagrams.d1"].startswith("NMN'M'Pq")


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


def test_glyph_runs_split_when_directions_differ_and_zero_fits_either():
    from webpier.calc.frame import PointLoad
    from webpier.reporting.stages.frame_report import CaseLoads, Manuscript, diagram_groups

    _, _, result, _ = chain("current")
    frame = result.frame
    node = frame.node(NodeRole.FOOTING_CENTROID).number

    def case(number: int, n: float) -> CaseLoads:
        point = PointLoad(NodeRole.FOOTING_CENTROID, node, Printed(n, 2, "kN"), Printed(0.0, 2, "kN"),
                          Printed(0.0, 2, "kN m"))
        return CaseLoads(number, f"c{number}", (point,))

    m = Manuscript("x/")
    diagram_groups(m, frame, [("g", "G", [case(1, 0.0), case(2, -5.0), case(3, 0.0), case(4, 7.0)])],
                   lambda name, cases: f"{cases[0].number}-{cases[-1].number}")
    titles = [u.value for u in m.units if u.key.endswith(".title")]
    assert titles == ["1-3", "4-4"]
    signs = [[g.sign for g in u.value.figure.glyphs] for u in m.units if u.kind == "diagram"]
    assert signs == [[-1], [1]]


def test_unsupported_nodes_and_duplicate_keys_are_rejected():
    from webpier.reporting.stages.frame_report import Manuscript, document, plain

    with pytest.raises(TypeError, match="Unsupported"):
        plain(object())
    m = Manuscript("x/")
    m.paragraph("a", "一")
    m.paragraph("a", "二")
    with pytest.raises(ValueError, match="重複"):
        document(m.units, "{page}")
