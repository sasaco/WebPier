"""Deterministic CP932/CRLF V5.2 NDU writer and limited product validator.

The record sequence is significant: the native reader consumes blocks in order.
This validator covers this export dialect, not arbitrary or app-edited NDU.
Independent app-read acceptance uses its own parser and literal fixture.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .inputs import InputError
from .jrsnap_design_conditions import (
    PROFILE_ID,
    TARGET_VERSION,
    TRANSVERSE_PROFILE_ID,
    UNSET,
    number,
)


def _text(value: str, limit: int = 40) -> str:
    if any(ord(char) < 32 or ord(char) == 127 or char in ",=" for char in value):
        raise InputError("JRSNAP: 文字列に制御文字または区切り文字があります")
    try:
        data = value.encode("cp932", errors="strict")
    except UnicodeEncodeError as exc:
        raise InputError("JRSNAP: CP932で表現できない文字があります") from exc
    if len(data) > limit:
        raise InputError(f"JRSNAP: 文字列はCP932で{limit}bytes以内が必要です")
    return value


def _value(value) -> str:
    if value is None:
        return " "
    if isinstance(value, str):
        return _text(value)
    if type(value) is bool:
        return "True" if value else "False"
    number(value, "NDU数値", minimum=-3.402823e38, maximum=3.402823e38)
    if value == 0:
        return "0"
    return str(value) if type(value) is int else repr(float(value))


def _records(model: Mapping) -> list[tuple[str, list | str | None]]:
    metadata, section = model["metadata"], model["section"]
    if (metadata["profile_id"] not in (PROFILE_ID, TRANSVERSE_PROFILE_ID) or metadata["target_version"] != TARGET_VERSION or
            metadata["schema_version"] != 1):
        raise InputError("JRSNAP: profileまたは対象版が一致しません")
    settings, roles = metadata["settings"], metadata["roles"]
    analysis = settings["analysis"]
    nodes, members, elements, cases = (model[key] for key in ("nodes", "members", "elements", "cases"))
    rows: list[tuple[str, list | str | None]] = []

    def add(key: str, *values) -> None:
        rows.append((key, list(values)))

    rows.append(("Virsion", "5.2.3.S.4"))
    rows.append(("DataName", "線路直角方向" if metadata["profile_id"] == TRANSVERSE_PROFILE_ID else "線路方向"))
    for index in range(1, 21):
        rows.append((f"DataTitle{index}", ""))
    add("DataInfo", 1, 1, analysis["steps"], roles[analysis["control_role"]],
        analysis["load_divisions"], analysis["limited_final_step"], None, None, None,
        analysis["intermediate_trials"], analysis["final_trials"], 1, 1, 1, 1, 1,
        model["combination"]["rho_m"], model["combination"]["alpha_f"],
        analysis["target_displacement_m"], analysis["convergence_tolerance"], 0, 1, 0, 0, 0, 0)
    add("ExOptLoad", 1, 1, 1)
    add("ExOptDisp", 2, 2, 1, 0, 0, 1, 0, 0)
    add("JointOrg", roles["footing_top"])
    add("JointNum", len(nodes))
    for node in nodes:
        add(f"JointXY{node['id']}", node["x"], node["y"], node["id"])
    add("MemberNum", len(members))
    for member in members:
        identifier = member["id"]
        rows.append((f"MemberTitle{identifier}", _text(member["region"])))
        add(f"MemberInfo{identifier}", member["node_i"], member["node_j"], 1)
        add(f"MemberLeng{identifier}", member["length"])
        add(f"MemberOkuyuki{identifier}", 1)
        add(f"MemberDvid{identifier}-1", member["length"], 1)
        add(f"MemberShogen{identifier}", 1)
    for member in members:
        add(f"MemberKUI{member['id']}", 0)
    add("KGNum", 0)
    add("ElementNum", len(elements))
    rigid = settings["rigid"]
    for element in elements:
        nonlinear = element["kind"] == 2
        add(f"ElementInfo{element['id']}", element["kind"], 0, 0, 0, element["node_i"], element["node_j"],
            1 if nonlinear else 0, 0, None if nonlinear else rigid["area_m2"],
            None if nonlinear else rigid["inertia_m4"], None if nonlinear else rigid["Ec_kn_mm2"],
            0, 0, element["id"])
    add("HendoCaseInfo", *([0] * 10))
    add("JibanCaseNum", 1)
    for element in elements:
        add(f"JibanShogenInfo{element['id']}", *([None] * 7))
    add("TyakumokuNum", 0)
    for element in elements:
        add(f"ElementTyakumokuNum{element['id']}", 0, 0)
    rows.append(("SHABUZAI_INFO", None))
    for node in nodes:
        add(f"SHABUZAI_JointXY{node['id']}", 0, 0, False)
    for member in members:
        add(f"ShabuzaiMeInfo{member['id']}", *([0] * 9), False, False)
    add("NonLinNum", 1, 1, 0)
    add("NonLinInfo1", 1, 1, 1, 1, 1, 1, 1, 1, 0, _text("柱下端Mθ", 20))
    add("SectNum", 1)
    rows.append(("SectTitle1", "柱"))
    add("SectInfo1", 1, 1, 0, 1, section["width_mm"], section["height_mm"], 0, 0, 0,
        section["shear_span_mm"], UNSET, 0, 0, 0)
    section_settings = settings["section"]
    add("TanbuShiji1", section_settings["end_condition"], section_settings["end_condition_length_mm"])
    add("SectConc1", section["fck"], 0, section["Ec"], 0, section_settings["aggregate_max_mm"])
    layers = section["main_face_layers"]
    add("SectJikuNum1", len(section["rebar"]), layers, layers, layers, layers, 0)
    add("SectJiku1", section["fyk"], section["Es"], 0, 0,
        section["main_face_pitch_mm"], section["main_face_pitch_mm"], 0, 0, 0)
    for index, bar in enumerate(section["rebar"], 1):
        add(f"SectRein1-{index}", bar["center_mm"], bar["diameter_mm"], bar["count"])
    hoop = section["hoop"]
    values = [hoop[key] for key in ("fyk", "diameter_mm", "legs", "pitch_mm")]
    add("SectSher1", *values, 0, 0, *values)
    add("SectSafe1", *(section_settings["safety"][key] for key in
                       ("GC", "GR", "GS", "GB1", "GB2", "GB23", "GBC", "GBV", "GBS", "K", "GBVD", "GBVO")))
    supports, footing = model["supports"], model["footing"]
    add("SuppotNum", len(supports) + 1)
    add("SuppotRow", len(supports))
    add("SuppotAlf", 0, 0)
    add("ShitenCaseNum", 0)
    for index, support in enumerate(supports, 1):
        add(f"SuppotInfo{index}", None, support["node"], support["direction"], support["stiffness"], *([None] * 9))
    add("FootRow", 1)
    add("FootInfo1", None, footing["node"], footing["soil_type"], footing["B"], footing["L"],
        footing["kv"], footing["cohesion"], footing["Df"], footing["gamma1"], footing["gamma2"],
        footing["phi"], settings["foundation"]["KR2"], settings["foundation"]["KR3"], UNSET)
    add("ChokuKisoNum", 0)
    add("G_intCHOKU_KISO_Link_Num", 0)
    for index in range(1, len(supports) + 1):
        add(f"Suppot_ChokuKisoCaseNo{index}", 0)
    add("Foot_ChokuKisoCaseNo1", 0)
    for member in members:
        add(f"Member_BunpuBane{member['id']}", 0)
    # Native initial values for inactive foundation-check tables, not FootInfo.
    for index, coefficient in enumerate((.83, 1, 1), 1):
        add(f"JibanTeikouKeisuu{index}", *([coefficient] * 5))
    add("LoadNum", len(cases))
    add("MLoadNum", sum(len(case["member_loads"]) for case in cases))
    add("JLoadNum", sum(len(case["joint_loads"]) for case in cases))
    m_index = j_index = 0
    for case in cases:
        identifier = case["id"]
        rows.append((f"LoadTitle{identifier}", _text(case["label"])))
        add(f"LoadCase{identifier}", 1, 1, 0)
        add(f"LoadAlph{identifier}", 1)
        add(f"MLoadRow{identifier}", len(case["member_loads"]))
        for load in case["member_loads"]:
            m_index += 1
            add(f"MLoadInfo{m_index}", identifier, None, load["element"], case["increment"], load["kind"],
                None, None, load["q_i"], load["q_j"], None, None, load["label"])
        add(f"JLoadRow{identifier}", len(case["joint_loads"]))
        for load in case["joint_loads"]:
            j_index += 1
            add(f"JLoadInfo{j_index}", identifier, None, load["node"], case["increment"],
                load["H"] or None, load["N"] or None, load["M"] or None, load["label"])
    for name in ("ELoadNum", "ELoadRow", "DLoadNum", "DLoadRow"):
        add(name, 0)
    combination = model["combination"]
    add("SNAPConbNum", 1)
    add("SNAPConb1", combination["rho_m"], combination["alpha_f"], 0, 0,
        *combination["coefficients"], *([None] * (15 - len(cases))), 0, 0)
    add("ConbNum", 1)
    add("ConbAlpf1", *combination["coefficients"])
    for name in ("PickNum", "Conb2Num", "Pick2Num", "TishouNum"):
        add(name, 0)
    rows.append(("Tisou", ""))
    add("SesfNum", 0)
    for element in elements:
        # Empty strings (not a space) are the V52 inactive PiIJ format.
        add(f"SesfPiIJ{element['id']}", 0, 0, 0, 0, "", "")
    for name in ("SesfKihonNum", "SesfPiM", "SesfPiS"):
        add(name, 0)
    add("SesfPiBuzai", 0, 0, 0, 0, 0)
    add("GanmaA", 1.2, 1, 1, 1)
    add("FontColor", 0, 0, 9, 12, 12, 13)
    add("FontSize", 3, 3, 3, 3, 3, 3)
    rows.append(("FontName", "ＭＳ Ｐゴシック"))
    add("LineColor", 0, 13, 10, 11, 12)
    add("LineWidth", 0, 0, 0, 0, 10)
    add("Sunpo", .3, .2)
    add("JointCircle", .5)
    add("Grid", 1, 1, 1, 1)
    add("ErrInfo", *([0] * 11))
    return rows


def serialize_ndu(model: Mapping) -> bytes:
    """Serialize only the defined V5.2 dialect, then validate its own bytes."""
    try:
        lines = []
        for key, values in _records(model):
            body = values if isinstance(values, str) else ",".join(_value(value) for value in values or [])
            lines.append(key if values is None else key + "=" + body)
        data = ("\r\n".join(lines) + "\r\n").encode("cp932", errors="strict")
    except (KeyError, TypeError, UnicodeEncodeError) as exc:
        raise InputError(f"JRSNAP: NDUモデルの必須項目または文字形式が不正です: {exc}") from exc
    validate_ndu_bytes(data)
    return data


def validate_ndu_bytes(data: bytes) -> dict:
    """Check framing, field arity, referential integrity and the v1 contract."""
    if not isinstance(data, bytes) or not data.endswith(b"\r\n") or b"\n" in data.replace(b"\r\n", b"") or b"\r" in data.replace(b"\r\n", b""):
        raise InputError("JRSNAP: NDUは末尾改行のあるCRLF bytesが必要です")
    try:
        text = data.decode("cp932", errors="strict")
    except UnicodeDecodeError as exc:
        raise InputError("JRSNAP: NDUのCP932が不正です") from exc
    records, ordered = {}, []
    for line in text.splitlines():
        if line == "SHABUZAI_INFO":
            key, fields = line, []
        elif "=" in line:
            key, body = line.split("=", 1)
            fields = body.split(",")
        else:
            raise InputError("JRSNAP: NDUレコード形式が不正です")
        if key in records or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:-[0-9]+)?", key):
            raise InputError(f"JRSNAP: NDUキー重複または不正: {key}")
        if any(ord(char) < 32 or ord(char) == 127 for char in line):
            raise InputError("JRSNAP: NDUに制御文字があります")
        records[key] = fields
        ordered.append(key)

    def row(key: str, size: int | None = None) -> list:
        if key not in records or (size is not None and len(records[key]) != size):
            raise InputError(f"JRSNAP: {key}の欠落または欄数不正")
        return records[key]

    def numeric(value: str, label: str, *, blank: bool = False) -> float | None:
        if not value.strip() and blank:
            return None
        if re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", value) is None:
            raise InputError(f"JRSNAP: {label}の数値表記が不正です")
        try:
            result = float(value)
        except ValueError as exc:
            raise InputError(f"JRSNAP: {label}に数値が必要です") from exc
        if not math.isfinite(result) or abs(result) > 3.402823e38:
            raise InputError(f"JRSNAP: {label}の数値範囲が不正です")
        return result

    def integer(value: str, label: str) -> int:
        result = numeric(value, label)
        if result != int(result):
            raise InputError(f"JRSNAP: {label}に整数が必要です")
        return int(result)

    def count(key: str, maximum: int) -> int:
        value = integer(row(key, 1)[0], key)
        if not 0 <= value <= maximum:
            raise InputError(f"JRSNAP: {key}が上限外です")
        return value

    if row("Virsion", 1) != ["5.2.3.S.4"] or ordered[0] != "Virsion":
        raise InputError("JRSNAP: 5.2.3.S.4形式が必要です")
    title = row("DataName", 1)[0]
    if title not in ("線路方向", "線路直角方向"):
        raise InputError("JRSNAP: 対応する方向のDataNameが必要です")
    transverse = title == "線路直角方向"
    case_count = 9 if transverse else 8
    nn, nm, ne = count("JointNum", 2500), count("MemberNum", 400), count("ElementNum", 3500)
    if not nn or not nm or nm != ne:
        raise InputError("JRSNAP: v1は空でない1部材1要素モデルが必要です")
    node_ids, element_ids = set(range(1, nn + 1)), set(range(1, ne + 1))
    nodes = {}
    for index in node_ids:
        values = row(f"JointXY{index}", 3)
        x, y = (numeric(value, "JointXY") for value in values[:2])
        if max(abs(x), abs(y)) > 20000 or integer(values[2], "出力節点") != index:
            raise InputError("JRSNAP: 節点座標/出力番号が不正です")
        nodes[index] = (x, y)
    if len(set(nodes.values())) != nn:
        raise InputError("JRSNAP: 節点位置が重複しています")
    edges, nonlinear = set(), []
    for index in element_ids:
        values = row(f"ElementInfo{index}", 14)
        ints = [integer(value, "ElementInfo") for value in values[:8]]
        kind, first, second, ref = ints[0], ints[4], ints[5], ints[6]
        if kind not in (1, 2) or first not in node_ids or second not in node_ids or first == second or integer(values[13], "出力要素") != index:
            raise InputError("JRSNAP: 要素種別・節点参照・出力番号が不正です")
        if ints[1:4] != [0, 0, 0] or ints[7] != 0 or [integer(v, "element flags") for v in values[11:13]] != [0, 0]:
            raise InputError("JRSNAP: v1未対応の要素flagです")
        edge = frozenset((first, second))
        if edge in edges:
            raise InputError("JRSNAP: 要素接続が重複しています")
        edges.add(edge)
        length = math.dist(nodes[first], nodes[second])
        if length <= 1e-9:
            raise InputError("JRSNAP: 微小長さまたはゼロ長さの要素です")
        if kind == 2:
            nonlinear.append(index)
            if ref != 1 or any(value.strip() for value in values[8:11]) or not math.isclose(length, .01, rel_tol=0, abs_tol=1e-12):
                raise InputError("JRSNAP: 非線形部材参照または0.010 m長さが不正です")
        elif ref != 0 or [numeric(v, "rigid") for v in values[8:11]] != [1000, 1000, 25]:
            raise InputError("JRSNAP: 剛域定義が不正です")
        member = [integer(v, "MemberInfo") for v in row(f"MemberInfo{index}", 3)]
        division = row(f"MemberDvid{index}-1", 2)
        if member != [first, second, 1] or integer(division[1], "division") != 1:
            raise InputError("JRSNAP: 部材/要素の接続・分割が一致しません")
        for value in (division[0], row(f"MemberLeng{index}", 1)[0]):
            if not math.isclose(numeric(value, "member length"), length, rel_tol=1e-12, abs_tol=1e-12):
                raise InputError("JRSNAP: 部材長と座標が一致しません")
    if len(nonlinear) != 1 or row("NonLinNum", 3) != ["1", "1", "0"] or count("SectNum", 500) != 1:
        raise InputError("JRSNAP: 自動非線形1件/断面1件が必要です")
    nonlinear_values = row("NonLinInfo1", 10)
    if [numeric(v, "NonLinInfo") for v in nonlinear_values[:9]] != [1, 1, 1, 1, 1, 1, 1, 1, 0]:
        raise InputError("JRSNAP: 自動Mθの断面参照・構成設定が不正です")
    section_values = [numeric(v, "SectInfo") for v in row("SectInfo1", 14)]
    if (section_values[:4] != [1, 1, 0, 1] or
            any(not .1 <= section_values[index] <= 999999 for index in (4, 5, 9)) or
            section_values[6:9] != [0, 0, 0] or section_values[10:] != [UNSET, 0, 0, 0]):
        raise InputError("JRSNAP: 矩形断面の寸法・軸力未設定値が不正です")
    concrete = [numeric(v, "SectConc") for v in row("SectConc1", 5)]
    if not (18 <= concrete[0] <= 80 and concrete[1] == concrete[3] == 0 and
            0 < concrete[2] <= 999999 and .1 <= concrete[4] <= 999999):
        raise InputError("JRSNAP: コンクリート材料・粗骨材径が範囲外です")
    shear = [numeric(v, "SectSher") for v in row("SectSher1", 10)]
    if shear[4:6] != [0, 0] or shear[:4] != shear[6:] or min(shear[:4]) <= 0 or shear[2] != int(shear[2]):
        raise InputError("JRSNAP: 均一帯筋設定が不正です")
    safety = [numeric(v, "SectSafe") for v in row("SectSafe1", 12)]
    if any(not 0 < value <= 99.99 for index, value in enumerate(safety) if index != 8) or safety[8] != 0:
        raise InputError("JRSNAP: 安全係数が範囲外です")
    info = row("DataInfo", 26)
    for index, value in enumerate(info):
        numeric(value, "DataInfo", blank=index in (6, 7, 8))
    if (integer(info[3], "制御節点") not in node_ids or
            [numeric(v, "DataInfo") for v in info[:3]] != [1, 1, 350 if transverse else 300] or
            [numeric(v, "DataInfo") for v in info[4:6]] != [1000, 300 if transverse else 200] or
            any(v.strip() for v in info[6:9]) or
            [numeric(v, "DataInfo") for v in info[9:]] !=
            [999, 999, 1, 1, 1, 1, 1, 1, 1, .35 if transverse else -.3, .001, 0, 1, 0, 0, 0, 0]):
        raise InputError("JRSNAP: 解析制御・制御節点参照が不正です")
    if integer(row("JointOrg", 1)[0], "原点節点") not in node_ids:
        raise InputError("JRSNAP: 原点節点参照が不正です")
    nr = integer(row("SectJikuNum1", 6)[0], "主筋行数")
    if not 1 <= nr <= 100:
        raise InputError("JRSNAP: 主筋行数は1～100行が必要です")
    main_counts = [integer(v, "主筋段数") for v in records["SectJikuNum1"]]
    if (any(not 1 <= count <= nr for count in main_counts[1:5]) or
            len(set(main_counts[1:5])) != 1 or main_counts[5] != 0):
        raise InputError("JRSNAP: 主筋段数・降伏位置が不正です")
    main = [numeric(v, "SectJiku") for v in row("SectJiku1", 9)]
    if (main[0] not in (295, 345, 390) or main[1] != 200 or main[2:4] != [0, 0] or
            any(not .001 <= value <= 99999 for value in main[4:6]) or main[6:] != [0, 0, 0]):
        raise InputError("JRSNAP: 主筋材質・弾性係数・間隔が不正です")
    previous = -1.0
    height = numeric(records["SectInfo1"][5], "断面高さ")
    for index in range(1, nr + 1):
        center, diameter, bars = [numeric(v, "SectRein") for v in row(f"SectRein1-{index}", 3)]
        if center <= previous or not diameter / 2 <= center <= height - diameter / 2 or diameter <= 0 or bars != int(bars) or bars < 1:
            raise InputError("JRSNAP: 主筋行の順序・芯位置・径・本数が不正です")
        previous = center
    if [count(key, 999) for key in ("SuppotNum", "SuppotRow", "FootRow")] != [3, 2, 1]:
        raise InputError("JRSNAP: 直接基礎の支持件数が不正です")
    support_nodes = []
    for index in (1, 2):
        values = row(f"SuppotInfo{index}", 13)
        support_nodes.append(integer(values[1], "支点"))
        if values[0].strip() or integer(values[2], "方向") != index or numeric(values[3], "ばね") <= 0:
            raise InputError("JRSNAP: 並進ばねの形式が不正です")
    foot = row("FootInfo1", 14)
    support_nodes.append(integer(foot[1], "回転ばね節点"))
    if len(set(support_nodes)) != 1 or support_nodes[0] not in node_ids:
        raise InputError("JRSNAP: 基礎ばね節点が一致しません")
    if foot[0].strip() or integer(foot[2], "地盤種別") != 1:
        raise InputError("JRSNAP: 直接基礎は砂質土系1節点が必要です")
    physics = [numeric(v, "FootInfo") for v in foot[3:]]
    if (any(not 0 < physics[index] <= 999999 for index in (0, 1, 2, 4, 5, 6)) or
            physics[3] != 0 or not 25 <= physics[7] < 90 or physics[8:] != [2, 20, UNSET]):
        raise InputError("JRSNAP: FootInfoのDf・単位重量・φ・勾配比が不正です")
    if count("LoadNum", 100) != case_count:
        raise InputError(f"JRSNAP: {title}の基本荷重{case_count}件が必要です")
    load_totals = {"M": 0, "J": 0}
    for case in range(1, case_count + 1):
        increment = 4 if case == case_count - 1 else (1 if case in (case_count - 2, case_count) else 0)
        for family, size in (("M", 12), ("J", 8)):
            amount = count(f"{family}LoadRow{case}", 9999)
            if family == "M" and amount and case not in (1, case_count):
                raise InputError("JRSNAP: 分布荷重はD1/EQ2だけに対応します")
            for index in range(load_totals[family] + 1, load_totals[family] + amount + 1):
                values = row(f"{family}LoadInfo{index}", size)
                if integer(values[0], "load case") != case or integer(values[3], "load mode") != increment or values[1].strip():
                    raise InputError("JRSNAP: 荷重case・固定/増分/限定増分が不正です")
                target = integer(values[2], "load reference")
                if target not in (element_ids if family == "M" else node_ids):
                    raise InputError("JRSNAP: 荷重の節点/要素参照が不正です")
                if family == "M" and integer(values[4], "load kind") != (4 if case == 1 else 1):
                    raise InputError("JRSNAP: 要素荷重型が不正です")
                for value in values[5 if family == "M" else 4:-1]:
                    force = numeric(value, "荷重", blank=True)
                    if force is not None and abs(force) > 9999999999:
                        raise InputError("JRSNAP: 荷重数値が範囲外です")
                _text(values[-1])
            load_totals[family] += amount
        row(f"LoadCase{case}", 3)
        row(f"LoadAlph{case}", 1)
    for family, amount in load_totals.items():
        if count(f"{family}LoadNum", 9999) != amount:
            raise InputError("JRSNAP: 荷重行の合計が一致しません")
    if count("SNAPConbNum", 99) != 1 or count("ConbNum", 99) != 1:
        raise InputError("JRSNAP: 組合せ1件が必要です")
    combination = row("SNAPConb1", 21)
    coefficients = [1, 1, 1, 1, 1, 0, 1, 1, 1] if transverse else [1] * 8
    if ([numeric(v, "係数") for v in combination[4:4 + case_count]] != coefficients or
            [numeric(v, "係数") for v in row("ConbAlpf1", case_count)] != coefficients or
            [numeric(v, "組合せ条件") for v in combination[:4]] != [1, 1, 0, 0] or
            any(v.strip() for v in combination[4 + case_count:19]) or
            [numeric(v, "組合せ条件") for v in combination[19:]] != [0, 0]):
        raise InputError("JRSNAP: 組合せ係数が不正です")
    for name in ("ChokuKisoNum", "G_intCHOKU_KISO_Link_Num", "TishouNum", "SesfNum"):
        if count(name, 999) != 0:
            raise InputError(f"JRSNAP: {name}は無効である必要があります")
    if row("Tisou", 1) != [""] or any(key.startswith(("CHOKU_KISO", "SoilRenkei")) or key == "NDTPath" for key in records):
        raise InputError("JRSNAP: 旧照査・地層・外部連携が残っています")
    expected = ["Virsion", "DataName", *(f"DataTitle{i}" for i in range(1, 21)),
                "DataInfo", "ExOptLoad", "ExOptDisp", "JointOrg", "JointNum",
                *(f"JointXY{i}" for i in range(1, nn + 1)), "MemberNum"]
    for index in range(1, nm + 1):
        expected.extend([f"{name}{index}" for name in ("MemberTitle", "MemberInfo", "MemberLeng", "MemberOkuyuki")])
        expected.extend([f"MemberDvid{index}-1", f"MemberShogen{index}"])
    expected.extend([*(f"MemberKUI{i}" for i in range(1, nm + 1)), "KGNum", "ElementNum",
                     *(f"ElementInfo{i}" for i in range(1, ne + 1)), "HendoCaseInfo", "JibanCaseNum",
                     *(f"JibanShogenInfo{i}" for i in range(1, ne + 1)), "TyakumokuNum",
                     *(f"ElementTyakumokuNum{i}" for i in range(1, ne + 1)), "SHABUZAI_INFO",
                     *(f"SHABUZAI_JointXY{i}" for i in range(1, nn + 1)),
                     *(f"ShabuzaiMeInfo{i}" for i in range(1, nm + 1)), "NonLinNum", "NonLinInfo1",
                     "SectNum", "SectTitle1", "SectInfo1", "TanbuShiji1", "SectConc1", "SectJikuNum1", "SectJiku1",
                     *(f"SectRein1-{i}" for i in range(1, nr + 1)), "SectSher1", "SectSafe1",
                     "SuppotNum", "SuppotRow", "SuppotAlf", "ShitenCaseNum", "SuppotInfo1", "SuppotInfo2",
                     "FootRow", "FootInfo1", "ChokuKisoNum", "G_intCHOKU_KISO_Link_Num",
                     "Suppot_ChokuKisoCaseNo1", "Suppot_ChokuKisoCaseNo2", "Foot_ChokuKisoCaseNo1",
                     *(f"Member_BunpuBane{i}" for i in range(1, nm + 1)),
                     "JibanTeikouKeisuu1", "JibanTeikouKeisuu2", "JibanTeikouKeisuu3", "LoadNum", "MLoadNum", "JLoadNum"])
    m_count = j_count = 0
    for case in range(1, case_count + 1):
        expected.extend([f"LoadTitle{case}", f"LoadCase{case}", f"LoadAlph{case}", f"MLoadRow{case}"])
        amount = integer(records[f"MLoadRow{case}"][0], "MLoadRow")
        expected.extend(f"MLoadInfo{i}" for i in range(m_count + 1, m_count + amount + 1))
        m_count += amount
        expected.append(f"JLoadRow{case}")
        amount = integer(records[f"JLoadRow{case}"][0], "JLoadRow")
        expected.extend(f"JLoadInfo{i}" for i in range(j_count + 1, j_count + amount + 1))
        j_count += amount
    expected.extend(["ELoadNum", "ELoadRow", "DLoadNum", "DLoadRow", "SNAPConbNum", "SNAPConb1", "ConbNum", "ConbAlpf1",
                     "PickNum", "Conb2Num", "Pick2Num", "TishouNum", "Tisou", "SesfNum",
                     *(f"SesfPiIJ{i}" for i in range(1, ne + 1)), "SesfKihonNum", "SesfPiM", "SesfPiS", "SesfPiBuzai", "GanmaA",
                     "FontColor", "FontSize", "FontName", "LineColor", "LineWidth", "Sunpo", "JointCircle", "Grid", "ErrInfo"])
    if ordered != expected:
        raise InputError("JRSNAP: Native読込の全レコード順序・件数・キー集合が不正です")
    arities = {"ExOptLoad": 3, "ExOptDisp": 8, "HendoCaseInfo": 10, "TanbuShiji1": 2,
               "SectJiku1": 9, "SuppotAlf": 2, "SesfPiBuzai": 5, "GanmaA": 4, "FontColor": 6,
               "FontSize": 6, "LineColor": 5, "LineWidth": 5, "Sunpo": 2, "JointCircle": 1,
               "Grid": 4, "ErrInfo": 11}
    for key, size in arities.items():
        row(key, size)
    for key, fields in records.items():
        if key in ("Virsion", "DataName", "FontName", "Tisou", "SHABUZAI_INFO") or key.startswith(("DataTitle", "MemberTitle", "SectTitle", "LoadTitle")):
            if fields:
                _text(fields[0])
            continue
        limit = len(fields) - (1 if key == "NonLinInfo1" or key.startswith(("MLoadInfo", "JLoadInfo")) else 0)
        for field in fields[:limit]:
            if field in ("False", "True") and key.startswith(("SHABUZAI_JointXY", "ShabuzaiMeInfo")):
                continue
            numeric(field, key, blank=True)
    for index in range(1, ne + 1):
        row(f"JibanShogenInfo{index}", 7)
        row(f"ElementTyakumokuNum{index}", 2)
        row(f"SesfPiIJ{index}", 6)
    for index in range(1, nn + 1):
        row(f"SHABUZAI_JointXY{index}", 3)
    for index in range(1, nm + 1):
        row(f"ShabuzaiMeInfo{index}", 11)
    return {"header": "5.2.3.S.4", "records": records,
            "counts": {"nodes": nn, "members": nm, "elements": ne, "rebar_rows": nr,
                       "member_loads": load_totals["M"], "joint_loads": load_totals["J"]}}
