"""The input sheets 下部構造・上部構造・地盤データ・JRSNAPの設定, laid out like the original input forms.

Derived values are not inputs and have no cells: the unit weight of the displaced soil is calculated and printed
by 0710 / 0720, and each bearing position f is entered on both sides. The 表層 thickness may stay blank: it is
then the rest of Df (H6+H5+min(df1,df2)) below the other layers (decision 64). B9 is entered; "B7と同じ" writes B7 into it explicitly. The 耐震設計条件 (地域別・地盤区分) are on the
地盤データ page: one for the pier, used only by the static nonlinear analysis (decision 49).
"""

from __future__ import annotations

import copy
from tkinter import messagebox, ttk
from typing import Any

from ..export.jrsnap import LONGITUDINAL, TRANSVERSE
from ..inputs import choices
from ..inputs.choices import LAYER_SUPPORT, LAYER_SURFACE
from . import bearings
from .document import EditorError
from .form import Form, unit_of

SUB = ("下部構造",)
SUPER = ("上部構造",)
SIDES = ("起点側", "終点側")
RESERVED = "（予約項目：形式と桁だけを確認し、計算には使いません）"


def substructure(form: Form) -> None:
    body = form.section("01  橋脚の寸法", note="B：側面　W：正面　H：高さ（m）。B9 も入力します（「B7と同じ」で B7 の値を書き込めます）。")
    values = ttk.Frame(body)
    values.pack(anchor="w")
    for column, (title, group, prefix, count) in enumerate((("側面 B", "側面", "B", 9), ("正面 W", "正面", "W", 9),
                                                             ("高さ H", "高さ", "H", 6))):
        table = ttk.Frame(values, padding=(0, 0, 10, 0))
        table.grid(row=0, column=column, sticky="n")
        rows = [[f"{prefix}{i}", (*SUB, "寸法", group, f"{prefix}{i}")] for i in range(1, count + 1)]
        form.table(table, [title, f"値 ({unit_of((*SUB, '寸法', group, f'{prefix}1'))})"], rows, [65, 95])
        if prefix == "B":
            form.editor.b7_button = form.button(table, "B9：B7と同じ", lambda: same_as_b7(form))
    form.figure(body, "substructure", "側面・正面の寸法記号 / 原図・記号確認用")

    body = form.section("02  土かぶり・水位・斜角", note="水位は基礎下面からの高さです。斜角は" + RESERVED)
    form.properties(body, [((*SUB, group, key), label) for group, key, label in (
        ("土かぶり", "起点側_df1", "起点側の土かぶり df1"), ("土かぶり", "終点側_df2", "終点側の土かぶり df2"),
        ("水位", "高水位_hw1", "高水位 hw1"), ("水位", "平水位_hw2", "平水位 hw2"), ("水位", "低水位_hw3", "低水位 hw3"),
        ("斜角", "θ", "斜角 θ（予約）"), ("斜角", "タイプ", "斜角のタイプ（予約）"))])
    form.figure(body, "skew", "タイプ1・2 / 原図・記号確認用")

    body = form.section("03  単位体積重量", note="排除した土の単位体積重量は、地盤データのうちフーチング高さ（H5＋H6）の範囲にある層の"
                        "湿潤単位体積重量を厚さで平均して計算します。杭の単位体積重量は「杭基礎」のページで入力します。")
    weights = (*SUB, "単位体積重量")
    form.properties(body, [((*weights, "梁・躯体"), "梁・躯体"), ((*weights, "フーチング"), "フーチング"),
                           ((*weights, "上載土"), "上載土")])

    body = form.section("04  基礎形式", note="直接基礎のほか、場所打ち杭・鋼管ソイルセメント杭を選べます。杭基礎の杭の条件と配置は"
                        "「杭基礎」のページで入力します（杭基礎の計算は、段ごとに対応を広げています）。")
    form.properties(body, [((*SUB, "基礎形式"), "基礎形式")], widths=[260, 200, 100])


def same_as_b7(form: Form) -> bool:
    if not form.editor.ready_to_restructure():
        return False
    try:
        bearings.same_as_b7(form.data)
    except EditorError as exc:
        messagebox.showerror("B9 を書き込めません", str(exc), parent=form.editor.root)
        return False
    form.editor.bindings.refresh()
    form.editor.changed()
    return True


# decision 59: the rubber bearings and the stoppers of each girder, used only by 0900
BEARING_DEVICES = ("ゴム支承の箇所数", "ストッパーの箇所数", "片持ち梁上のゴム支承", "片持ち梁上のストッパー")
SPAN_COLUMNS = ((("桁長", "L1"), "桁端 L1"), (("桁長", "スパン長"), "スパン長"), (("桁長", "L2"), "桁端 L2"),
                (("衝撃係数_単線終局",), "衝撃係数\n単線終局"), (("曲線半径",), "曲線半径"), (("列車速度",), "列車速度"),
                (("遠心作用方向",), "遠心作用方向\n（予約）"), *((("高さ", f"h{i}"), f"高さ h{i}") for i in range(1, 5)),
                (("重心高_hs",), "重心高 hs"), (("支承位置_f",), "支承位置 f"))
TRAIN = ((("車両名",), "車両名"), (("1両の長さ",), "1両の長さ"), (("軸距", "a1_連結部"), "軸距 a1（連結部）"),
         (("軸距", "a2"), "軸距 a2"), (("軸重", "地震以外"), "軸重：地震以外"), (("軸重", "地震"), "地震時列車荷重"),
         (("編成数",), "編成数"), (("車両高", "受風高"), "車両高：受風高"), (("車両高", "遠心重心高"), "車両高：遠心重心高"),
         (("車両高", "地震重心高"), "車両高：地震重心高"), (("荷重修正係数", "使用性"), "荷重修正係数：使用性"),
         (("荷重修正係数", "安全性(破壊)"), "荷重修正係数：安全性（破壊）"),
         (("荷重修正係数", "安全性(疲労)"), "荷重修正係数：安全性（疲労）"))


def superstructure(form: Form) -> None:
    body = form.section("01  桁と支承位置", note="支承位置 f は起点側・終点側とも入力します。重心高 hs は直角地震時慣性力の作用高さです。")
    headers = [f"{label}\n{unit_of((*SUPER, '起点側', *tail))}".rstrip() for tail, label in SPAN_COLUMNS]
    form.table(body, headers, [[(*SUPER, side, *tail) for tail, _ in SPAN_COLUMNS] for side in SIDES],
               [80, 85, 80, 90, 85, 85, 100, 75, 75, 75, 75, 85, 85], row_labels=list(SIDES), index_width=80)
    form.figure(body, "superstructure", "桁長・高さ・支承位置 / 原図・記号確認用")

    body = form.section("02  支承データ", note="復旧性制動係数：空欄のときは安全性（破壊）の荷重修正係数から求めます。"
                        "ゴム支承・ストッパーの箇所数と片持ち梁上の個数は片持ち梁の照査（0900、決定59）だけが使い、ほかは空欄のままで構いません。")
    support = (*SUPER, "支承データ")
    form.table(body, ["支承名", "摩擦係数 μ", "復旧性制動係数", *BEARING_DEVICES],
               [[(*support, side, key) for key in ("支承名", "摩擦係数_μ", "復旧性制動係数", *BEARING_DEVICES)]
                for side in SIDES],
               [120, 100, 120, 110, 120, 130, 130], row_labels=list(SIDES), index_width=80)

    body = form.section("03  列車", note="車両名は一覧から選びます（EA-17：EA-17の規定式、P-16：軸重式）。")
    table = ttk.Frame(body)
    table.pack(side="left", anchor="n")
    form.properties(table, [((*SUPER, "列車", *tail), label) for tail, label in TRAIN])
    picture = ttk.Frame(body, padding=(18, 20))
    picture.pack(side="left", fill="x", expand=True, anchor="n")
    form.figure(picture, "train", "軸距・1両の長さ / 原図・記号確認用")


GROUND_COLUMNS = (("層番", ("層番",)), ("層厚\n(m)", ("層厚",)), ("土質区分", ("土質区分",)), ("N値", ("N値",)),
                  ("単位体積重量\n湿潤", ("単位体積重量", "湿潤")), ("単位体積重量\n水中", ("単位体積重量", "水中")),
                  ("内部摩擦角\nφd (°)", ("内部摩擦角_φd",)), ("φd の上限値\n(°)", ("内部摩擦角の上限値",)),
                  ("粘着力\nc (kN/m²)", ("粘着力_c",)), ("変形係数\nEd (kN/m²)", ("変形係数_Ed",)),
                  ("液状化の\n低減係数 De", ("De",)))


def _layers(form: Form) -> list:
    return form.data["地盤データ"]["層"]


def blank_layer() -> dict[str, Any]:
    return {"層番": None, "層厚": None, "土質区分": None, "N値": None, "単位体積重量": {"湿潤": None, "水中": None},
            "内部摩擦角_φd": None, "粘着力_c": None, "変形係数_Ed": None, "De": None}


def _thickness_keys(layers: list) -> None:
    """Every layer has the key; a blank 表層 is the rest of Df (decision 64)."""
    for layer in layers:
        layer.setdefault("層厚", None)


def ground(form: Form) -> None:
    body = form.section("地層一覧", note=f"先頭は「{LAYER_SURFACE}」です。地表から順に並べ、「{LAYER_SUPPORT}」より上の層は層厚を"
                        f"入力します。{LAYER_SUPPORT}の Df 内の厚さは Df（H6＋H5＋min(df1,df2)）から上の層厚の合計を引いた残りです。"
                        f"{LAYER_SURFACE}の層厚が空欄のときは Df から下の層の層厚を引いて計算します（{LAYER_SUPPORT}は基礎底面から）。"
                        "湿潤・水中の単位体積重量は kN/m³。土質区分は一覧から選びます。")
    controls = ttk.Frame(body)
    controls.pack(fill="x", pady=(0, 12))
    for label, action in (("＋ 層を追加", lambda: soil_change(form, "add")),
                          ("選択層を複製", lambda: soil_change(form, "duplicate")),
                          ("↑ 上へ", lambda: soil_change(form, "up")), ("↓ 下へ", lambda: soil_change(form, "down")),
                          ("選択層を削除", lambda: soil_change(form, "delete"))):
        ttk.Button(controls, text=label, command=action).pack(side="left", padx=(0, 8))
    layers = _layers(form)
    rows = [[("地盤データ", "層", index, *tail) for _, tail in GROUND_COLUMNS] for index in range(len(layers))]
    sheet = form.table(body, [label for label, _ in GROUND_COLUMNS], rows,
                       [90, 75, 150, 60, 95, 95, 90, 90, 110, 110, 110])
    editor = form.editor
    editor.soil_selected = min(editor.soil_selected, max(0, len(layers) - 1))

    def selected(event: Any) -> None:
        current = sheet.get_currently_selected()
        if current:
            editor.soil_selected = current.row

    sheet.bind("<<SheetSelect>>", selected, add="+")
    if layers:
        sheet.select_cell(editor.soil_selected, 0)
    editor.soil_sheet = sheet

    body = form.section("耐震設計条件", note="線路方向・線路直角方向で共通です。静的非線形解析（0711・0721）の結果を"
                        "Aggre-SE で照査する入力（post の線路方向.xml・線路直角方向.xml）に書きます。それ以外の計算には使いません。")
    form.properties(body, [(("耐震設計条件", "地域別"), "地域別"), (("耐震設計条件", "地盤区分"), "地盤区分（耐震設計上）")])


def soil_change(form: Form, action: str) -> bool:
    editor = form.editor
    if not editor.ready_to_restructure():
        return False
    layers = _layers(form)
    index = editor.soil_selected
    if action == "add":
        layers.append(blank_layer())
        index = len(layers) - 1
    elif not 0 <= index < len(layers):
        return False
    elif action == "duplicate":
        layers.insert(index + 1, copy.deepcopy(layers[index]))
        index += 1
    elif action == "delete":
        name = layers[index].get("層番") or ""
        if not messagebox.askyesno("地層の削除", f"{index + 1}行目（{name}）を削除しますか？", parent=editor.root):
            return False
        del layers[index]
        index = max(0, min(index, len(layers) - 1))
    else:
        target = index + (-1 if action == "up" else 1)
        if not 0 <= target < len(layers):
            return False
        layers[index], layers[target] = layers[target], layers[index]
        index = target
    _thickness_keys(layers)
    editor.soil_selected = index
    editor.rebuild()
    return True


PILES = ("杭基礎",)
PILE_ROWS = {
    choices.CAST_IN_PLACE_PILE: ((("場所打ち杭", "杭径"), "杭径 D"), (("場所打ち杭", "f'ck"), "コンクリートの設計基準強度 f'ck"),
                                 (("場所打ち杭", "施工条件"), "施工条件")),
    choices.STEEL_SOIL_CEMENT_PILE: (
        (("鋼管ソイルセメント杭", "ソイルセメント径"), "ソイルセメント径 Dsc"), (("鋼管ソイルセメント杭", "鋼管外径"), "鋼管外径 Dsp"),
        (("鋼管ソイルセメント杭", "鋼管厚"), "鋼管厚 t（腐食代を含む）"), (("鋼管ソイルセメント杭", "腐食代"), "腐食代 c"), (("鋼管ソイルセメント杭", "鋼管材質"), "鋼管の材質")),
}
LAYOUT_DIRECTIONS = (("線路方向の列の位置", "線路方向の列", "線路方向"), ("線路直角方向の列の位置", "線路直角方向の列", "線路直角方向"))


def piles(form: Form) -> None:
    """杭基礎 (decision 80): the items of the chosen 基礎形式 only; the other form's are kept in the input and not shown."""
    foundation = form.data.get("下部構造", {}).get("基礎形式")
    layout = form.data.get("杭基礎", {}).get("配置")
    if foundation not in choices.PILE_FOUNDATIONS or not isinstance(layout, dict):
        form.section("杭基礎", note=f"基礎形式が{foundation}のため、杭基礎の項目は使いません。基礎形式は「下部構造」のページで選びます。")
        return
    body = form.section("01  杭の諸元", note=f"基礎形式：{foundation}。長さは m、鋼管厚と腐食代は mm です。杭の単位体積重量は"
                        "杭の有効重量（SOIL-JR の入力）に使います。")
    form.properties(body, [((*PILES, "杭長"), "杭長 L"), ((*PILES, "杭の単位体積重量"), "杭の単位体積重量"),
                           *(((*PILES, *tail), label) for tail, label in PILE_ROWS[foundation])], widths=[260, 150, 100])

    body = form.section("02  杭の配置", note="杭列の位置はフーチングの中心からの距離（m）で、小さい順に並べます（骨組の x・y の向き）。"
                        "格子配置は全交点に杭があります。千鳥配置は両方向とも奇数列で、列の番号の和が偶数の位置にだけ杭があります。"
                        "列ごとの本数・間隔は位置から求めます。")
    form.properties(body, [((*PILES, "配置", "形式"), "配置の形式")], widths=[260, 150, 100])
    tables = ttk.Frame(body)
    tables.pack(anchor="w", pady=(10, 0))
    for column, (key, _, direction) in enumerate(LAYOUT_DIRECTIONS):
        box = ttk.Frame(tables, padding=(0, 0, 18, 0))
        box.grid(row=0, column=column, sticky="n")
        positions = layout.get(key, [])
        form.table(box, [f"{direction}の列の位置\n(m)"], [[(*PILES, "配置", key, index)] for index in range(len(positions))],
                   [170], row_labels=[str(index + 1) for index in range(len(positions))], pack=False).pack(anchor="w")
        buttons = ttk.Frame(box)
        buttons.pack(anchor="w", pady=(6, 0))
        ttk.Button(buttons, text="＋ 列を追加", command=lambda key=key: pile_change(form, key, "add")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="最後の列を削除", command=lambda key=key: pile_change(form, key, "delete")).pack(side="left")
    box = ttk.Frame(tables, padding=(0, 0, 18, 0))
    box.grid(row=0, column=2, sticky="n")
    removed = layout.get("抜く杭", [])
    form.table(box, ["抜く杭\n線路方向の列", "抜く杭\n線路直角方向の列"],
               [[(*PILES, "配置", "抜く杭", index, column) for _, column, _ in LAYOUT_DIRECTIONS]
                for index in range(len(removed))],
               [130, 150], row_labels=[str(index + 1) for index in range(len(removed))], pack=False).pack(anchor="w")
    buttons = ttk.Frame(box)
    buttons.pack(anchor="w", pady=(6, 0))
    ttk.Button(buttons, text="＋ 抜く杭を追加", command=lambda: pile_change(form, "抜く杭", "add")).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="最後を削除", command=lambda: pile_change(form, "抜く杭", "delete")).pack(side="left")


def pile_change(form: Form, key: str, action: str) -> bool:
    """Add a column position or a pile left out, or delete the last one."""
    editor = form.editor
    if not editor.ready_to_restructure():
        return False
    items = form.data["杭基礎"]["配置"][key]
    if action == "add":
        items.append({"線路方向の列": None, "線路直角方向の列": None} if key == "抜く杭" else None)
    elif items:
        items.pop()
    else:
        return False
    editor.rebuild()
    return True


JRSNAP_ROWS = (("shear_factor_vcd", "部材係数 γb（Vcd）"), ("shear_factor_vsd", "部材係数 γb（Vsd）"),
               ("shear_factor_vdd", "部材係数 γb（Vdd）"), ("analysis_steps", "解析のステップ数"),
               ("limited_final_step", "限定増分の最終ステップ"), ("target_displacement_m", "目標変位（大きさ）"))


def jrsnap(form: Form) -> None:
    """The JRSNAP conditions of each direction, written into its NDU by 0710 / 0720 (decision 72 moved them here)."""
    body = form.section("JRSNAP 5.2-L03", note="線路方向の計算（地震時）を選ぶと線路方向の、線路直角方向の計算（地震時）を選ぶと"
                        "線路直角方向の全項目が必要です。空欄は補いません。")
    for profile, direction in ((LONGITUDINAL, "線路方向（0710）"), (TRANSVERSE, "線路直角方向（0720）")):
        box = ttk.LabelFrame(body, text=direction, padding=8)
        box.pack(side="left", anchor="n", padx=(0, 8))
        form.properties(box, [((f"jrsnap_{profile.jrsnap}", key), label) for key, label in JRSNAP_ROWS],
                        widths=[220, 110, 60])
        ttk.Label(box, text=f"目標変位の向き：{profile.earthquake_text}（地震の向き。自動で決めます）",
                  style="Muted.TLabel").pack(anchor="w")
