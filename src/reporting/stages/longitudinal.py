"""Native, variable-page 0610 manuscript from the canonical result only."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row, render_pdf

from ...frame_outline import dimension_text, frame_dimensions
from .frame_content import Manuscript, Merged, Unit, VerticalHeader, build_document, semantic_sections

_PART = {"beam": "梁", "column": "柱", "footing": "フーチング"}
_REGION = {"h1": "H1", "h2": "H2", "h3": "H3", "h4": "H4",
           "footing_top_to_centroid": "基礎天端～重心", "footing_centroid_to_bottom": "基礎重心～底面",
           "parapet_arm": "H1水平アーム"}
_ROLE = {"cap_top": "梁天端", "footing_top": "基礎天端", "footing_centroid": "基礎重心",
         "footing_bottom": "基礎底面", "h2_h3": "H2/H3", "h3_h4": "H3/H4",
         "parapet_base": "H1基部", "parapet_top": "H1上端"}


def _f(value: float, places: int = 2) -> str:
    return f"{value:,.{places}f}"


def _model(m: Manuscript, result: dict[str, Any]) -> None:
    frame = result["frame"]
    m.section("model")
    m.title("1. 骨組モデル・支持ばね（線路方向）")
    labels = (*[str(node["id"]) for node in frame["nodes"]],
              *[str(member["id"]) for member in frame["members"]],
              *[dimension_text(value) for value in frame_dimensions(frame)])
    m.add(labels, "figure", figure=(result["input"]["geometry"], frame, "b"))
    m.text(f"支持節点 {frame['support_node_id']} ：基礎底面。太線は剛域、寸法・節点座標の単位は m。")
    m.title("支持ばね：線路方向・正規 Double 値", left=73.44)
    m.table(("区分", "Kv (kN/m)", "Ks (kN/m)", "Kr (kN m/rad)"),
            [["長期" if term == "long_term" else "短期", *[_f(value[key], 0) for key in ("Kv", "Ks", "Kr")]]
             for term, value in frame["springs"].items()], (75, 145, 145, 150))
    m.text("0500の長期・短期の正規値を、線路方向の支持節点へ接続する。")
    m.text("本書は作用・骨組条件と非地震の組合せを示す。構造解析・断面照査は含まない。")


def _conditions(m: Manuscript, result: dict[str, Any]) -> None:
    frame = result["frame"]
    m.section("conditions")
    m.title("2. 断面・材料および実節点・部材")
    m.table(("材料", "f'ck (N/mm2)", "Ec (kN/m2)"),
            [[_PART[key], _f(value["fck"], 1), _f(value["Ec"], 0)] for key, value in frame["materials"].items()],
            (175, 155, 185))
    m.text("Ecは部位別強度に応じたRcDan表の補間値。フーチングは入力強度を表示し剛域として扱う。")
    m.table(("断面", "幅 (m)", "高さ (m)", "A (m2)", "I (m4)"),
            [[key, _f(value["width"], 3), _f(value["depth"], 3), _f(value["area"], 3), _f(value["inertia"], 5)]
             for key, value in frame["sections"].items()], (125, 85, 85, 105, 115))
    m.table(("節点", "x (m)", "y (m)", "役割"),
            [[node["id"], _f(node["x"], 3), _f(node["y"], 3), " / ".join(_ROLE[role] for role in node["roles"])]
             for node in frame["nodes"]], (45, 90, 90, 290))
    m.table(("部材", "始点", "終点", "区間", "挙動", "断面", "材料"),
            [[member["id"], member["node_i"], member["node_j"], _REGION[member["region"]],
              "剛域" if member["behavior"] == "rigid" else "弾性", member["section_ref"] or "－",
              _PART.get(member["material_ref"], "－")] for member in frame["members"]], (35, 40, 40, 145, 55, 95, 105))
    m.text("H2/H3＝梁、H4＝柱。H1は専用材料入力がないため柱材料を継承する。")
    m.text("フーチングとH1水平アームは剛域。部材の自重は重複して自動加算しない。")


def _dead_water(m: Manuscript, result: dict[str, Any]) -> None:
    vertical, detail = result["vertical"], result["calculation_details"]["fixed"]
    m.section("dead_water")
    m.title("8.2 作用の計算")
    m.title("(1) 固定死荷重 D1", left=73.44)
    m.formula(f"柱分布　q = {_f(vertical['fixed']['column']['intensity'])} kN/m")
    m.formula(f"フーチング　P = {_f(vertical['fixed']['footing']['N'])} kN、M = {_f(vertical['fixed']['footing']['M'])} kN m")
    rows = [[label, *[_f(detail["components"][key][field], places) for field, places in (("N", 2), ("arm", 3), ("M", 2))]]
            for key, label in (("B", "起点側 B"), ("C", "終点側 C"), ("pedestal", "桁受け"), ("beam", "はり等（0600集約）"))]
    rows.append(["合計", _f(detail["sum_N"]), "", _f(detail["sum_M"])])
    m.table(("", "鉛直力 N (kN)", "アーム (m)", "モーメント (kN m)"), rows, (160, 115, 115, 125))
    deduction = detail["column_deduction"]
    m.formula(f"鉛直力　N = {_f(detail['sum_N'])} − {_f(deduction['intensity'])} × {_f(deduction['length'], 3)} = {_f(detail['adopted_top']['N'])} kN")
    m.formula(f"モーメント　M = {_f(detail['adopted_top']['M'])} kN m")
    m.formula(f"柱控除長 H2+H3 = {_f(deduction['length'], 3)} m")
    for index, key in enumerate(("omega2", "omega3"), 2):
        formula = result["reference_formulas"]["fixed"][key]
        m.formula(f"参考 ω{index} = {_f(formula['height'], 3)} × {_f(formula['width'], 3)} × {_f(formula['unit_weight'], 1)} = {_f(formula['value'])} kN/m")
    m.title("(2) 付加死荷重 D2", left=73.44)
    m.formula(f"上載土　P = {_f(vertical['additional']['soil']['N'])} kN、M = {_f(vertical['additional']['soil']['M'])} kN m")
    top = vertical["additional"]["top"]
    rows = [["起点側 B" if side == "B" else "終点側 C", _f(top[side]["N"]), _f(top[side]["arm"], 3), _f(top[side]["M"])] for side in ("B", "C")]
    rows.append(["合計", _f(top["N"]), "", _f(top["M"])])
    m.table(("", "鉛直力 N (kN)", "アーム (m)", "モーメント (kN m)"), rows, (160, 115, 115, 125))
    m.title("(3) 浮力", left=73.44)
    m.text("参考ωは高さ×幅×γの線荷重。採用Nは集中鉛直力、Mは偏心モーメント。")
    for key, label in (("high", "高水位"), ("normal", "平水位"), ("low", "低水位")):
        start = len(m.units)
        formula, load = result["reference_formulas"]["water"][key], vertical["water"][key]
        m.text(label)
        m.formula(f"参考 ω = {_f(formula['height'], 3)} × {_f(formula['width'], 3)} × {_f(formula['unit_weight'], 1)} = {_f(formula['value'])} kN/m")
        m.formula(f"採用 N = {_f(load['N'])} kN、M = {_f(load['M'])} kN m")
        m.keep_since(start)


def _support(m: Manuscript, label: str, load: dict[str, Any]) -> None:
    m.title(label, left=87.96)
    rows = [["起点側 B" if side == "B" else "終点側 C", _f(load[side]["N"]), _f(load[side]["arm"], 3), _f(load[side]["M"])] for side in ("B", "C")]
    rows.append(["合計", _f(load["N"]), "", _f(load["M"])])
    m.table(("", "鉛直力 N (kN)", "アーム (m)", "モーメント (kN m)"), rows, (160, 115, 115, 125))


def _snow_train(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("snow_train")
    m.title("(4) 雪荷重", left=73.44)
    for key, label in (("s2", "1) 2年確率 S2"), ("s10", "2) 10年確率 S10"), ("s30", "3) 30年確率 S30")):
        _support(m, label, result["vertical"]["snow"][key])
    m.title("(5) 列車荷重", left=73.44)
    for track, label in (("single", "1) 単線載荷 L1"), ("double", "2) 複線載荷 L2")):
        _support(m, label, result["vertical"]["train"][track])
    m.text("列車荷重は無係数反力。組合せでは安全性・復旧性の有効係数、または使用性の係数を一度だけ適用する。")


def _impact_horizontal(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("impact_horizontal")
    m.title("(6) 衝撃荷重", left=73.44)
    family = {row["track"]: row for row in result["basic_cases"] if row["id"] in (11, 12)}
    for track, label in (("single", "1) 単線載荷"), ("double", "2) 複線載荷")):
        load, trace = result["vertical"]["impact"]["ultimate"][track], family[track]["usage_resolution"]["ultimate"]
        m.title(f"{label}（安全性）", left=87.96)
        m.formula(f"採用 a = {_f(trace['effective_train_factor'])}")
        rows = [["起点 B" if side == "B" else "終点 C", _f(trace["support_calculation"][side]["train"]), "×",
                 _f(trace["pier_coefficients"][side], 5), "=", _f(load[side]["N"]), _f(load[side]["arm"], 3), _f(load[side]["M"])] for side in ("B", "C")]
        rows.append(["合計", "", "", "", "", _f(load["N"]), "", _f(load["M"])])
        m.table(("", "採用 L (kN)", "", "橋脚 c_p", "", "I (kN)", "アーム (m)", "M (kN m)"), rows,
                (60, 90, 18, 80, 18, 80, 80, 90))
    m.text("c_pは0600の用途別橋脚低減込み。Iは支点別0.1 kN丸め。名目0.75・荷重係数を再乗算しない。")
    m.title("使用性・最大時の補足（最大時も橋脚低減を再評価しない）", left=73.44)
    rows = []
    for usage, label in (("service", "使用性"), ("maximum", "最大")):
        for track, track_label in (("single", "単線"), ("double", "複線")):
            load, trace = result["vertical"]["impact"][usage][track], family[track]["usage_resolution"][usage]
            rows.append([f"{label} {track_label}", _f(trace["effective_train_factor"]),
                         _f(trace["pier_coefficients"]["B"], 5), _f(trace["pier_coefficients"]["C"], 5),
                         _f(load["B"]["N"]), _f(load["C"]["N"]), _f(load["N"]), _f(load["M"])])
    m.table(("用途・線数", "採用 a", "B c_p", "C c_p", "B I (kN)", "C I (kN)", "N (kN)", "M (kN m)"), rows,
            (90, 60, 66, 66, 66, 66, 73, 68))
    m.title("(7) 水平荷重", left=73.44)
    rows = [("用途", "基本", "荷重種別", "起点 B (kN)", "終点 C (kN)", "合計 (kN)")]
    groups = {0: (2, "使用性"), 2: (4, "安全性"), 6: (2, "復旧性")}
    category_indices = []
    index = len(rows[0])
    for number, row in enumerate(result["horizontal"]):
        prefix = []
        if number in groups:
            count, label = groups[number]
            prefix = [Merged(label, rowspan=count)]
            category_indices.append(index)
        label = row["label"].replace("ロングレール縦荷重 ", "").replace("ロングレール+制動 ", "").split(" ", 1)[-1]
        values = (*prefix, str(row["id"]), label, _f(row["B"]), _f(row["C"]), _f(row["total"]))
        rows.append(values)
        index += len(values)
    # The frozen renderer draws all three merged labels before the row values.
    order = (*range(6), *category_indices, *[i for i in range(6, index) if i not in category_indices])
    m.rows(rows, (50, 30, 210, 75, 75, 75), header_rows=1, source_order=order)
    recovery = next(row for row in result["horizontal"] if row["id"] == 19)["upstream_details"]
    coefficients = [recovery[side].get("effective_brake_coefficient") for side in ("B", "C")]
    if all(isinstance(value, (int, float)) for value in coefficients):
        m.text(f"復旧性の側別制動係数：B {_f(coefficients[0])} / C {_f(coefficients[1])}。")
    m.text("支承摩擦は上部工の L+I を含む採用水平力を保持する。鉛直Iの組合せ係数とは別に扱う。")


def _cases(m: Manuscript, result: dict[str, Any]) -> None:
    m.section("definitions")
    m.title("6. 基本ケース・定義ケース (Define)")
    rows = [[basic["id"], basic["symbol"], basic["label"], basic["spring_case"],
             " / ".join(f"{value:+d}" for value in define["signed_basic_case_ids"])]
            for basic, define in zip(result["basic_cases"], result["define_cases"], strict=True)]
    m.table(("ID", "作用", "基本ケース", "ばね", "Define"), rows, (35, 125, 240, 40, 75))
    m.text("Define 1～12は正方向、13～20は当該水平作用のみ正負を選択する。")
    m.section("matrix")
    m.title("7. 荷重組合せ（名目係数）")
    m.text("20基本を列、16組合せを行に示す。－は0。水平作用だけ正負を展開する。")
    m.rows(((Merged("", colspan=2), Merged("死荷重", colspan=2), Merged("水位", colspan=3),
             Merged("雪", colspan=3), Merged("列車", colspan=2), Merged("衝撃", colspan=2), Merged("水平作用", colspan=8)),),
           (18, 54, *([22.8] * 20)))
    headers = ("", "", *[VerticalHeader((basic["symbol"].replace("（側別係数）", ""), str(basic["id"])))
                          for basic in result["basic_cases"]])
    # Narrow tables use a tall header; content is still authored once in its
    # source order, and coefficients keep all existing display digits.
    matrix = [headers]
    matrix.extend((str(case["id"]), case["label"].split()[-1],
                   *["－" if coefficient == 0 else _f(coefficient) for coefficient in case["coefficients"]])
                  for case in result["combinations"])
    m.rows(matrix, (18, 54, *([22.8] * len(result["basic_cases"]))), header_rows=1)
    m.text("組合せ1～9：躯体、10～16：基礎。各組合せの用途は後掲の対応表に示す。")
    m.text("Iの名目係数を、用途別橋脚係数で解決済みのIに再乗算しない。採用荷重は用途別表による。")
    m.section("extractions")
    m.title("8. 抽出ケース")
    m.table(("ID", "性能・用途", "組合せID"),
            [[row["id"], row["label"], ", ".join(map(str, row["combination_ids"]))] for row in result["extraction_cases"]], (45, 275, 195))
    m.title("組合せケースの対応", left=73.44)
    m.table(("ID", "対象", "組合せ"),
            [[row["id"], "躯体" if row["scope"] == "body" else "基礎", row["label"]] for row in result["combinations"]], (45, 80, 390))
    m.text("抽出は組合せの参照群を示す。応答解析による最大・最小値の抽出結果ではない。")


def content(result: dict[str, Any]) -> tuple[Unit, ...]:
    if result.get("schema_version") != 2:
        raise ValueError("0610正規帳票にはschema_version=2の計算結果が必要です")
    manuscript = Manuscript("0610")
    for compose in (_model, _conditions, _dead_water, _snow_train, _impact_horizontal, _cases):
        compose(manuscript, result)
    return tuple(manuscript.units)


def semantic_records(result: dict[str, Any]) -> list[dict[str, str]]:
    return semantic_sections(content(result))


def build_report(result: dict[str, Any]) -> Document:
    digest = result.get("provenance", {}).get("input_sha256", "未記録")[:12]
    return build_document(content(result), header="0610 線路方向荷重", footer=f"入力 SHA256: {digest}   8-{{page}}")


def render(result: dict[str, Any], output_path: str | Path) -> None:
    document = build_report(result)
    pages = document.layout()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(pages, path, document.fonts, invariant=True)
