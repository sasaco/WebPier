"""Native 0620 engineering manuscript, preserving supplied canonical values."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence
from typing import Any

from gridlayoutpdf import Document, render_pdf

from ...frame_outline import dimension_text, frame_dimensions
from ...reaction_math import excel_round
from ..equations import script
from .frame_content import Header, Manuscript, Merged, Unit, atoms, build_document, semantic_sections

_PART = {"beam": "梁", "column": "柱", "footing": "フーチング"}
_ROLE = {"cap_top": "梁天端", "footing_top": "基礎天端", "footing_centroid": "基礎重心",
         "footing_bottom": "基礎底面", "h2_h3": "H2/H3", "h3_h4": "H3/H4",
         "parapet_base": "H1基部", "parapet_top": "H1上端"}
_SIDES = {"B": "起点側 RB", "C": "終点側 RC"}


def _f(value: float | None, places: int = 3) -> str:
    return "－" if value is None else f"{excel_round(value, places):.{places}f}"


def _point(loads: dict[str, Any], anchor: str) -> dict[str, Any]:
    return next(point for point in loads["points"] if point["anchor"] == anchor)


def _active(loads: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in loads["rows"] if row.get("active", True)
            and not (row.get("side") is None and row.get("label") == "桁受け"
                     and all(row[key] == 0 for key in ("N", "H", "M")))]


def _model(m: Manuscript, result: dict[str, Any]) -> None:
    frame = result["frame"]
    m.section("frame")
    m.title("線路直角方向　骨組図")
    labels = (*[str(node["id"]) for node in frame["nodes"]], *[str(member["id"]) for member in frame["members"]],
              *[dimension_text(value) for value in frame_dimensions(frame)])
    m.add(labels, "figure", figure=(result["input"]["geometry"], frame, "w"))
    m.text(f"支持節点：{frame['support_node_id']}　　太線：剛域　　破線：橋脚外形")
    m.text("寸法単位：m。荷重は梁天端、基礎重心および柱の分布区間に作用する。")
    m.section("model")
    m.title("骨組条件・材料・基礎ばね")
    m.title("節点座標", left=73.44)
    m.table(("節点", "x (m)", "y (m)", "位置"),
            [[node["id"], _f(node["x"]), _f(node["y"]), " / ".join(_ROLE[role] for role in node["roles"])]
             for node in frame["nodes"]], (43, 90, 90, 276))
    m.title("部材・断面", left=73.44)
    rows = []
    for member in frame["members"]:
        rigid = member["behavior"] == "rigid"
        section = None if rigid else frame["sections"][member["section_ref"]]
        rows.append([member["id"], f"{member['node_i']} → {member['node_j']}", "剛域" if rigid else _PART[member["material_ref"]],
                     "－" if rigid else _f(section["area"], 3), "－" if rigid else _f(section["inertia"], 5)])
    m.table(("部材", "節点 i → j", "材料", "A (m²)", "I (m⁴)"), rows, (43, 90, 90, 138, 138))
    m.title("コンクリート", left=73.44)
    m.table(("部位", "設計基準強度 (N/mm²)", "弾性係数 Ec (kN/m²)"),
            [[_PART[key], _f(value["fck"], 1), f"{value['Ec']:,.0f}"] for key, value in frame["materials"].items()], (139, 150, 210))
    m.title("直接基礎ばね（線路直角方向）", left=73.44)
    m.table(("条件", "Kv (kN/m)", "Ks (kN/m)", "Kr (kN・m/rad)"),
            [[label, *[f"{frame['springs'][term][key]:,.0f}" for key in ("Kv", "Ks", "Kr")]]
             for term, label in (("long_term", "長期：1"), ("short_term", "短期：2"))], (100, 133, 133, 133))


def _bearing(m: Manuscript, loads: dict[str, Any], *, kind: str = "simple", title: str | None = None,
             total_n: float | None = None, train_loads: dict[str, Any] | None = None) -> None:
    if title:
        m.title(title, left=87.96) if not title.startswith("・") else m.text(title)
    rows = []
    previous = None
    train = {(row.get("side"), row.get("bearing")): row for row in (train_loads or {}).get("rows", [])}
    for row in _active(loads):
        side = row.get("side")
        if kind == "simple":
            label = f"{_SIDES[side]} G{row['bearing']}" if side is not None else row.get("label", "")
            if label == "はり・ハンチ等価荷重":
                label = "はり・ハンチ等価"
            rows.append([label, _f(row["N"], 2), _f(row["arm"], 3), _f(row["M"], 2)])
        else:
            prefix = [_SIDES[side] if kind == "train" or side != previous else "", f"G{row['bearing']} ="] if side is not None else [row.get("label", ""), ""]
            left = row["upstream_N"] if kind == "train" else train[(side, row["bearing"])]["N"]
            middle = row["factor"] if kind == "train" else row["impact_coefficient"]
            rows.append([*prefix, _f(left, 2), "×", _f(middle, 3), "=" if kind == "train" else "→",
                         _f(row["N"], 2), _f(row["arm"], 3), _f(row["M"], 2)])
        previous = side
    total = loads["table_totals"]
    if kind == "simple":
        rows.append(["合計", _f(total["N"] if total_n is None else total_n, 2), "", _f(total["M"], 2)])
        m.table(("", "鉛直力 (kN)", "アーム (m)", "ﾓｰﾒﾝﾄ (kN･m)"), rows, (140, 110, 110, 110))
    else:
        rows.append(["", "", "", "", "", "Σ", _f(total["N"], 2), "", _f(total["M"], 2)])
        m.table(("", "", "", "", "", "", "鉛直力 (kN)", "アーム (m)", "ﾓｰﾒﾝﾄ(kN･m)"), rows,
                (63, 42, 75, 15, 65, 15, 75, 65, 75))


def _dead(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("dead_additional")
    m.title("9.2　作用の計算")
    m.title("(1) 固定死荷重", left=73.44)
    geometry, actions = result["input"]["geometry"], result["actions"]
    fixed, additional = actions["dead_fixed"], actions["dead_additional"]
    details, g = fixed["details"], geometry
    m.formula(f"柱　q = {_f(g['b6'], 2)} × {_f(g['w6'], 2)} × {_f(g['unit_weight_body'], 1)} = {_f(details['column_intensity'], 2)} kN/m")
    breadth, width = g["b7"] + g["b8"] + g["b9"], g["w7"] + g["w8"] + g["w9"]
    footing = _point(fixed, "footing_centroid")
    product = g["unit_weight_footing"] * breadth * width * g["h6"]
    expression = (f"{_f(g['unit_weight_footing'], 1)} × {_f(breadth, 2)} × {_f(width, 2)} × {_f(g['h6'], 2)} = "
                  if g["h5"] == 0 and _f(product, 2) == _f(footing["N"], 2) else "")
    m.formula(f"フーチング　W3 = {expression}{_f(footing['N'], 2)} kN")
    if footing["M"]:
        m.formula(f"M3 = {_f(footing['M'], 2)} kN･m")
    m.text("・橋脚天端に作用する荷重")
    lower_width = g["w1"] - g["w4"] - g["w5"]
    product = g["b1"] * (g["w1"] * g["h2"] + (g["w1"] + lower_width) * g["h3"] / 2) * g["unit_weight_body"]
    if g["b4"] + g["b5"] == 0 and _f(product, 2) == _f(details["beam_N"], 2):
        m.formula(f"はり・ハンチ等価荷重　Wb = {_f(g['b1'], 2)} × {{{_f(g['w1'], 2)} × {_f(g['h2'], 2)}", left=87.96)
        m.text(f"＋ ({_f(g['w1'], 2)} ＋ {_f(lower_width, 2)}) × {_f(g['h3'], 2)} / 2}} × {_f(g['unit_weight_body'], 1)} = {_f(details['beam_N'], 2)} kN")
    else:
        m.formula(f"はり・ハンチ等価荷重　Wb = {_f(details['beam_N'], 2)} kN", left=87.96)
    _bearing(m, fixed, total_n=details["gross_top_N"])
    top = _point(fixed, "cap_top")
    m.formula(f"N = {_f(details['gross_top_N'], 2)} − {_f(details['column_intensity'], 2)} × {_f(details['overlap_height'], 3)} = {_f(top['N'], 2)} kN")
    m.formula(f"M = {_f(top['M'], 2)} kN･m")
    m.text("柱との重複区間を橋脚天端荷重から控除する。はり・ハンチは等価荷重を用いる。")
    m.title("(2) 付加死荷重", left=73.44)
    soil = _point(additional, "footing_centroid")
    upper = g["unit_weight_soil"] * breadth * width * g["df1"]
    excluded = -g["unit_weight_soil"] * g["w6"] * g["b6"] * g["df1"]
    if g["h5"] == 0 and g["df1"] == g["df2"] and _f(upper + excluded, 2) == _f(soil["N"], 2):
        m.formula(f"載荷土　P = {_f(g['unit_weight_soil'], 1)} × {_f(breadth, 2)} × {_f(width, 2)} × {_f(g['df1'], 2)} = {_f(upper, 2)} kN")
        m.formula(f"P = −{_f(g['unit_weight_soil'], 1)} × {_f(g['w6'], 2)} × {_f(g['b6'], 2)} × {_f(g['df1'], 2)} = {_f(excluded, 2)} kN")
        m.formula(f"ΣP = {_f(soil['N'], 2)} kN")
    else:
        m.formula(f"載荷土　ΣP = {_f(soil['N'], 2)} kN（基礎重心）")
    if soil["M"]:
        m.formula(f"M4 = {_f(soil['M'], 2)} kN･m")
    m.text("・橋脚天端に作用する荷重")
    _bearing(m, additional)


def _water_snow(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("water_snow")
    m.title("(3) 浮力", left=73.44)
    g, actions = result["input"]["geometry"], result["actions"]
    breadth, width = g["b7"] + g["b8"] + g["b9"], g["w7"] + g["w8"] + g["w9"]
    rectangular_top = g["h5"] + g["h6"] + min(g["df1"], g["df2"])
    for key, label in (("high", "高水位"), ("normal", "平水位"), ("low", "低水位")):
        loads = actions[f"buoyancy_{key}"]
        point, level = _point(loads, "footing_centroid"), loads["details"]["water_level"]
        if level <= rectangular_top and _f(-10 * breadth * width * level, 2) == _f(point["N"], 2):
            m.formula(f"{label}　U = −10 × {_f(breadth, 2)} × {_f(width, 2)} × {_f(level, 2)} = {_f(point['N'], 2)} kN")
        else:
            m.formula(f"{label}　h = {_f(level, 3)} m　U = {_f(point['N'], 2)} kN")
        if point["M"]:
            m.formula(f"M = {_f(point['M'], 2)} kN･m")
    m.text("基礎重心に作用する。鉛直力は下向きを正とする。")
    m.title("(4) 雪荷重", left=73.44)
    for index, years in enumerate((2, 10, 30), 1):
        _bearing(m, actions[f"snow_{years}_year"], title=f"{index}) {years}年確率")


def _train_impact(m: Manuscript, result: dict[str, Any], *, impact: bool = False,
                  service: bool = False, selected: dict[str, Any] | None = None) -> None:
    m.section("service_impact" if service else "impact" if impact else "train")
    actions = result["actions"] if selected is None else selected
    m.title("補足　使用性の衝撃荷重" if service else f"({'6' if impact else '5'}) {'衝撃荷重' if impact else '列車荷重'}", left=73.44)
    if service:
        factor = result["factor_parameters"]["service_factor"]
        if factor == 0:
            m.text("使用性の荷重修正係数が0のため、使用性の列車・衝撃荷重は0とする。")
            return
        m.text(f"使用性の荷重修正係数 a = {_f(factor, 3)} を適用済み。")
        m.text("衝撃係数には使用性の低減0.75を含む。")
    m.title("1) 単線載荷", left=87.96)
    prefix = "impact" if impact else "train"
    for track, label in (("up", "・上り線載荷"), ("down", "・下り線載荷"), ("double", "2) 複線載荷")):
        _bearing(m, actions[f"{prefix}_{track}"], kind="impact" if impact else "train", title=label,
                 train_loads=actions[f"train_{track}"] if impact else None)
    if impact:
        m.text("→：支点総衝撃力を0.1 kNに丸め、その差を分担率の絶対値に応じて配分した鉛直力。")
        m.text("モーメントは配分後の未丸め鉛直力と各支承のアームから求める。")
    else:
        m.text("列車・衝撃・車両横荷重の基本値は荷重修正係数 a = 1.00。組合せ時に係数を適用する。")


def _horizontal_sum(m: Manuscript, loads: dict[str, Any], *, moment: bool = False) -> None:
    if moment:
        m.formula("M = HB × hB ＋ HC × hC")
        m.formula("   = " + " ＋ ".join(f"{_f(row['H'], 2)} × {_f(row['arm'], 3)}" for row in loads["rows"]))
        m.formula(f"   = {_f(loads['table_totals']['M'], 2)} kN･m")
    else:
        m.formula("H = HB ＋ HC")
        m.formula("   = " + " ＋ ".join(_f(row["H"], 2) for row in loads["rows"]) + f" = {_f(loads['table_totals']['H'], 2)} kN")


def _wind(m: Manuscript, result: dict[str, Any], key: str, label: str) -> None:
    start = len(m.units)
    loads = result["actions"][key]
    m.title(label, left=87.96)
    m.text("・橋脚天端に作用する荷重")
    _horizontal_sum(m, loads)
    m.text("・く体に作用する風荷重")
    m.formula(f"qH = {_f(loads['details']['pressure'], 1)} × {_f(result['input']['geometry']['b6'], 2)} = {_f(loads['line_loads'][0]['qH'], 2)} kN/m")
    rows = [[_SIDES[row["side"]], _f(row["H"], 2), _f(row["N"], 2), _f(row["arm"], 3), _f(row["M"], 2)] for row in loads["rows"]]
    rows.append(["合計", "", "", "M =", _f(loads["table_totals"]["M"], 2)])
    m.table(("", "水平力(kN)", "鉛直力(kN)", "アーム(m)", "ﾓｰﾒﾝﾄ(kN･m)"), rows, (100, 85, 85, 85, 100))
    m.text("起点側・終点側の荷重をそれぞれ集約して示す。")
    m.keep_since(start)


def _horizontal(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("horizontal")
    m.title("(7) 車両横荷重", left=73.44)
    loads = result["actions"]["vehicle_lateral"]
    m.text("・節点に作用する荷重")
    _horizontal_sum(m, loads)
    m.text("・橋脚天端～梁軸芯のトルクによるモーメント")
    _horizontal_sum(m, loads, moment=True)
    m.title("(8) 風荷重", left=73.44)
    _wind(m, result, "wind_with_train", "1) 列車荷重がある場合")
    m.section("wind_unloaded")
    _wind(m, result, "wind_without_train", "2) 列車荷重がない場合")


def _symbol(value: str) -> Any:
    return script(value[0], subscript=value[1:]) if len(value) > 1 else value


def _cases(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("cases")
    m.title("9.4 設計作用の組合せおよび応力算出点")
    m.title("(1) 基本ケース", left=73.44)
    rows = []
    for case in result["basic_cases"]:
        parts = case["label"].split()
        label = " ".join(parts[:4] if case["family"] == "impact" else parts[:3])
        rows.append([case["id"], label, case["spring_case"]])
    m.table(("No", "荷　重　名　称", "バネ"), rows, (28, 280, 55), row_height=12.84)
    m.title("(2) Defineケース", left=73.44)
    basics = {case["id"]: case for case in result["basic_cases"]}
    rows = []
    for case in result["define_cases"]:
        basic = basics[abs(case["signed_basic_case_ids"][0])]
        parts = basic["label"].split()
        condition = parts[2] if basic["family"] == "impact" else parts[1] if len(parts) > 1 else ""
        references = list(case["signed_basic_case_ids"])
        rows.append([case["id"], *references, *[""] * (3 - len(references)), _symbol(case["source_symbol"]), parts[0] + " " + condition])
    m.table(("No", "C1", "C2", "C3", "記号", "荷　重　名　称"), rows, (28, 36, 36, 36, 60, 240), row_height=12.84)
    _matrix(m, result)
    m.section("extractions")
    m.title("(4) 抽出ケース", left=73.44)
    rows = [[case["id"], case["label"], *case["combination_ids"], *[""] * (4 - len(case["combination_ids"]))]
            for case in result["extraction_cases"]]
    m.table(("No", "荷　重　名　称", "C1", "C2", "C3", "C4"), rows, (29, 160, 29, 29, 29, 29), row_height=12.84)


def _coefficient(value: float) -> str:
    if value == 0:
        return "－"
    text = format(float(value), ".12g")
    return text if "." in text or "e" in text.lower() else text + ".0"


def _matrix(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("combinations")
    m.title("(3) 組合せケースと荷重係数", left=73.44)
    header = [Merged("No", rowspan=2), Merged("要求性能", rowspan=2), Merged("性能項目", rowspan=2),
              Merged("死荷重", colspan=2), Merged("浮力", colspan=3), Merged("雪荷重", colspan=3),
              Merged("列車荷重", colspan=2), Merged("衝撃荷重", colspan=2), "", Merged("風荷重", colspan=2), Merged("備考", rowspan=2)]
    conditions = {0: ("固定",), 1: ("付加",), 2: ("高水位", "HWL"), 3: ("平水位", "MWL"),
                  4: ("低水位", "LWL"), 5: ("2年", "確率"), 6: ("10年", "確率"), 7: ("30年", "確率"),
                  8: ("単線",), 9: ("複線",), 10: ("単線",), 11: ("複線",),
                  12: ("車両", "横荷", "重"), 13: ("列車", "あり"), 14: ("列車", "なし")}
    rows: list[Sequence[Any]] = [header]
    second = []
    cursor = len(atoms(header))
    define_tokens, condition_tokens = [], {}
    for index, case in enumerate(result["define_cases"]):
        values = (str(case["id"]), _symbol(case["combination_symbol"]), *conditions.get(index, ()))
        second.append(Header(values))
        define_tokens.extend((cursor, cursor + 1))
        condition_tokens[index] = list(range(cursor + 2, cursor + len(values)))
        cursor += len(values)
    rows.append(second)
    performances = {0: (4, "安全性"), 4: (3, "使用性耐久性"), 7: (2, "復旧性"), 9: (4, "安全性"), 13: (3, "使用性")}
    items = {0: (4, "破壊"), 4: (3, "ひび割れ"), 7: (2, "損傷"), 9: (4, "地盤の安定"), 13: (2, "長期"), 15: (1, "短期")}
    performance_indices, item_indices, body_indices = {}, {}, []
    for index, case in enumerate(result["combinations"]):
        row: list[Any] = [str(case["id"])]
        body_indices.append(cursor)
        cursor += 1
        for groups, indices in ((performances, performance_indices), (items, item_indices)):
            if index in groups:
                count, label = groups[index]
                row.append(Merged(label, rowspan=count))
                indices[index] = cursor
                cursor += 1
            elif index > 15:
                row.append("")
                body_indices.append(cursor)
                cursor += 1
        values = [_coefficient(value) for value in case["coefficients"]]
        values.append(case["label"].split()[-1] if index < 13 else "")
        row.extend(values)
        body_indices.extend(range(cursor, cursor + len(values)))
        cursor += len(values)
        rows.append(row)
    condition_order = (0, 1, 8, 9, 10, 11, 2, 3, 4, 5, 6, 7, 13, 14, 12)
    order = (0, 1, 2, 10, 3, 4, 5, 6, 7, 9, 8, *define_tokens,
             *[token for key in condition_order for token in condition_tokens[key]],
             *[performance_indices[index] for index in (0, 9, 4, 7, 13)],
             *[item_indices[index] for index in (0, 4, 7, 9, 13, 15)], *body_indices)
    m.rows(rows, (18, 43.2, 54, *([24.6] * 15), 43.8), header_rows=2, row_height=12.84, source_order=order)


def content(result: dict[str, Any]) -> tuple[Unit, ...]:
    if result.get("schema_version") != 2:
        raise ValueError("0620の荷重・ケース形式が対応していません")
    m = Manuscript("0620")
    for compose in (_model, _dead, _water_snow):
        compose(m, result)
    _train_impact(m, result)
    _train_impact(m, result, impact=True)
    _horizontal(m, result)
    selected = {}
    for combination in result["combinations"]:
        if combination["id"] in (5, 7):
            for component in combination["resolved_components"]:
                for candidate in component["candidates"]:
                    if candidate["action_key"].startswith(("train_", "impact_")):
                        selected[candidate["action_key"]] = candidate["loads"]
    _train_impact(m, result, impact=True, service=True, selected=selected)
    _cases(m, result)
    return tuple(m.units)


def semantic_records(result: dict[str, Any]) -> list[dict[str, str]]:
    return semantic_sections(content(result))


def build_report(result: dict[str, Any]) -> Document:
    digest = result["provenance"].get("input_sha256", "未指定")[:12]
    return build_document(content(result), footer=f"0620 直角方向荷重　入力 SHA256: {digest}   {{page}}")


def render(result: dict[str, Any], output_path: str | Path) -> None:
    document = build_report(result)
    pages = document.layout()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(pages, path, document.fonts, invariant=True)
