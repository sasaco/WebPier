"""The input an acceptance may have been recorded from (decisions 72 and 84).

The real-runner acceptances recorded so far were made before the input had ``outputs``, and before it had the pile
foundation (``基礎形式``, ``杭基礎``, ``粘着力_c``, ``De``), and before the joint of the steel soil cement pile
(``結合部``, decision 90) and the bars of the cast-in-place pile (``軸方向鉄筋``, ``帯鉄筋`` of the 杭基礎, decision 91;
``鉄筋.杭`` from decision 92). None is a condition of the calculation of a direct
foundation: the 出力項目 only choose which reports a generation makes (ADR-0011), and the pile items are not read for a
direct foundation, whose layers keep their values (c replaced qu, which was 0 or blank). So such an acceptance still
belongs to current.json when everything but them is the recorded bytes. ``input_sha256s`` gives the SHA256 of the input
as it is (an acceptance recorded from now on), without its last item ``outputs`` (one recorded before decision 72), as it
was with the bars in the 杭基礎 (one recorded under decision 91), as it was before the bars of the cast-in-place pile (one
recorded before decision 91), before the joint (one recorded before decision 90) and before the pile foundation (one
recorded before decision 84), also without ``outputs``; the tests still compare the files the engines are given.
Every such form is also tried with the blank 杭頭定着長 and its stirrup in ``鉄筋.杭.cutoff`` (an acceptance recorded
before decision 98, which made the 杭頭定着長 a calculation; they were never entered in a recorded input), and, for
P-16, with the car, the axles and the seismic train load after 車両名 (an acceptance recorded before decision 101, which
made them the program's: the recorded inputs had P-16's own values, so the calculation is the same), and, with blank
``custom_tables`` of the column, as rebar version 3 with the empty ``table_overrides`` (an acceptance recorded before
decision 111, which replaced them; an empty change of the table is the table made from the bars, as a blank one is).
All of them are also tried with the bearing devices of decision 59 last in ``上部構造.支承データ.起点側`` and ``.終点側``
(after ``摩擦係数_μ`` and ``復旧性制動係数``; an acceptance recorded before decision 125, which removed them: only 0900
read them, and every recorded input had Example2's counts, 起点側 4, 3, 1, 1 and 終点側 2, 7, 1, 0).
"""

import json
import re

from webpier.core.integrity import sha256

_OUTPUTS = re.compile(rb',(\r?\n)  "outputs": \{[^{}]*\}(?=\1\}\s*$)')
_BLANK_PILE_ROW = {"線路方向": {"X": None, "本数": None}, "線路直角方向": {"Y": None, "本数": None}}
_OLD_PILE_ROWS = 6  # the reserved 杭の配置 had six blank rows in every recorded input


def _blank_piles(piles: object) -> bool:
    """Whether the 杭基礎 of an input is the empty one (nothing entered)."""
    return piles == {
        "杭長": None, "杭の単位体積重量": None, "場所打ち杭": {"杭径": None, "f'ck": None, "施工条件": None},
        "鋼管ソイルセメント杭": {"ソイルセメント径": None, "鋼管外径": None, "鋼管厚": None, "腐食代": None,
                      "鋼管材質": None},
        "配置": {"形式": None, "線路方向の列の位置": [], "線路直角方向の列の位置": [], "抜く杭": []}}


BLANK_BARS = {"軸方向鉄筋": {"径": None, "本数": None, "材質": None, "純かぶり": None},
              "帯鉄筋": {"径": None, "材質": None, "間隔": None}}  # decision 91: in the 杭基礎; decision 92 moved them
_HOOP = {"diameter_mm": None, "sets": None, "pitch_mm": None}
BLANK_PILE_REBAR = {  # 鉄筋.杭 with nothing entered (decisions 92 and 98)
    "materials": {"main": None, "transverse": None}, "pure_cover_mm": None, "aggregate_max_mm": None,
    "main_bars": {"diameter_mm": None, "count": None},
    "hoops": {"footing": dict(_HOOP), "zone_2d": dict(_HOOP), "lower": []},
    "cutoff": {"main_bars": {"diameter_mm": None, "count": None}, "hoops": dict(_HOOP),
               "cutoff_length_mm": None, "cutoff_anchorage_mm": None, "joint_reduction": None, "margin_mm": None,
               "no_joint": {"from_head_mm": None, "above_mm": None, "below_mm": None},
               "margin_ratio": {"moment": None, "shear": None}}}
_ANCHORAGE_KEYS = ("head_anchorage_mm", "anchorage_stirrup")  # in 鉄筋.杭.cutoff before decision 98


# decision 59's bearing devices of each girder, as every input recorded before decision 125 had them
BEARING_DEVICES = {"起点側": {"ゴム支承の箇所数": 4, "ストッパーの箇所数": 3, "片持ち梁上のゴム支承": 1, "片持ち梁上のストッパー": 1},
                   "終点側": {"ゴム支承の箇所数": 2, "ストッパーの箇所数": 7, "片持ち梁上のゴム支承": 1, "片持ち梁上のストッパー": 0}}


def _text(document: dict, data: bytes) -> bytes:
    text = json.dumps(document, indent=2, ensure_ascii=False) + ("\n" if data.endswith(b"\n") else "")
    return (text.replace("\n", "\r\n") if b"\r\n" in data else text).encode("utf-8")


P16_TRAIN = {"1両の長さ": 20.0, "軸距": {"a1_連結部": 2.8, "a2": 2.2}, "軸重": {"地震以外": 160.0, "地震": 32.0}}


def _old_train(train: dict) -> dict:
    old: dict = {}
    for key, value in train.items():
        old[key] = value
        if key == "車両名":
            old |= json.loads(json.dumps(P16_TRAIN))
    return old


def before_bearing_devices(data: bytes) -> bytes | None:
    """The input as it was before decision 125 (decision 59's bearing devices last in the 支承データ of each girder), or
    None when it already has them."""
    document = json.loads(data.decode("utf-8"))
    support = document.get("上部構造", {}).get("支承データ") if isinstance(document, dict) else None
    if not isinstance(support, dict) or any(key in support.get(side, {}) for side, devices in BEARING_DEVICES.items()
                                            for key in devices):
        return None
    for side, devices in BEARING_DEVICES.items():
        support[side] |= devices  # last, after 摩擦係数_μ (and 復旧性制動係数 where it is entered)
    return _text(document, data)


BLANK_CUSTOM_TABLES = {"線路": None, "直角": None}  # 鉄筋.柱.custom_tables with nothing entered (decision 111)


def before_custom_tables(data: bytes) -> bytes | None:
    """The input as it was before decision 111 (rebar version 3, the empty table_overrides of the column where the
    custom_tables are), or None when it is not rebar version 4 or a table of the column is entered."""
    document = json.loads(data.decode("utf-8"))
    rebar = document.get("鉄筋") if isinstance(document, dict) else None
    column = rebar.get("柱") if isinstance(rebar, dict) else None
    if not isinstance(column, dict) or rebar.get("version") != 4 or column.get("custom_tables") != BLANK_CUSTOM_TABLES:
        return None
    rebar["version"] = 3
    rebar["柱"] = {("table_overrides" if key == "custom_tables" else key): (
        {"線路": [], "直角": []} if key == "custom_tables" else value) for key, value in column.items()}
    return _text(document, data)


def before_vehicles(data: bytes) -> bytes | None:
    """The input as it was before decision 101 (P-16's car, axles and seismic train load after 車両名), or None when the
    vehicle is not P-16 or the input already has them."""
    document = json.loads(data.decode("utf-8"))
    train = document.get("上部構造", {}).get("列車") if isinstance(document, dict) else None
    if not isinstance(train, dict) or train.get("車両名") != "P-16" or "1両の長さ" in train:
        return None
    document["上部構造"]["列車"] = _old_train(train)
    return _text(document, data)


def before_anchorage(data: bytes) -> bytes | None:
    """The input as it was before decision 98 (the blank 杭頭定着長 after the hoops of the cut-off, and the blank stirrup
    for it last), or None when it has no 鉄筋.杭.cutoff or already has them."""
    document = json.loads(data.decode("utf-8"))
    rebar = document.get("鉄筋") if isinstance(document, dict) else None
    cutoff = rebar.get("杭", {}).get("cutoff") if isinstance(rebar, dict) else None
    if not isinstance(cutoff, dict) or any(key in cutoff for key in _ANCHORAGE_KEYS):
        return None
    old: dict = {}
    for key, value in cutoff.items():
        old[key] = value
        if key == "hoops":
            old["head_anchorage_mm"] = None
    old["anchorage_stirrup"] = None
    rebar["杭"]["cutoff"] = old
    return _text(document, data)


def _blank_rebar(rebar: dict) -> bool:
    """Whether 鉄筋.杭 of an input of before decision 98 is the empty one."""
    pile = rebar.get("杭")
    if not isinstance(pile, dict) or not isinstance(pile.get("cutoff"), dict):
        return False
    cutoff = {key: value for key, value in pile["cutoff"].items() if key not in _ANCHORAGE_KEYS}
    return ({**pile, "cutoff": cutoff} == BLANK_PILE_REBAR
            and all(pile["cutoff"].get(key) is None for key in _ANCHORAGE_KEYS))


def with_bars_in_piles(data: bytes) -> bytes | None:
    """The input as it was under decision 91 (the blank 軸方向鉄筋 and 帯鉄筋 in the 杭基礎, no 鉄筋.杭), or None when
    something is entered in 鉄筋.杭."""
    document = json.loads(data.decode("utf-8"))
    rebar = document.get("鉄筋") if isinstance(document, dict) else None
    cast = document.get("杭基礎", {}).get("場所打ち杭") if isinstance(document, dict) else None
    if not isinstance(rebar, dict) or not isinstance(cast, dict) or not _blank_rebar(rebar):
        return None
    del rebar["杭"]
    cast.update(BLANK_BARS)
    return _text(document, data)


def before_rebar(data: bytes) -> bytes | None:
    """The input as it was before decision 91 (no bars of 場所打ち杭 anywhere), or None when something is entered in
    鉄筋.杭."""
    document = json.loads(data.decode("utf-8"))
    rebar = document.get("鉄筋") if isinstance(document, dict) else None
    if not isinstance(rebar, dict) or not _blank_rebar(rebar):
        return None
    del rebar["杭"]
    return _text(document, data)


def before_joint(data: bytes) -> bytes | None:
    """The input as it was before decision 90 (the 結合部 of 鋼管ソイルセメント杭), or None when something is entered in it."""
    document = json.loads(data.decode("utf-8"))
    joint = document.get("杭基礎", {}).get("鋼管ソイルセメント杭", {}).get("結合部") if isinstance(document, dict) else None
    if joint != {"軸方向鉄筋": {"径": None, "本数": None, "材質": None, "重心位置": None}, "中詰めコンクリート_f'ck": None}:
        return None
    del document["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    return (text.replace("\n", "\r\n") if b"\r\n" in data else text).encode("utf-8")


def before_piles(data: bytes) -> bytes | None:
    """The input as it was before decision 80 (杭種 and the reserved pile items, qu), or None when it is not one that
    could have been: a pile foundation, anything entered under 杭基礎 or as a De."""
    document = json.loads(data.decode("utf-8"))
    if not isinstance(document, dict) or "杭基礎" not in document:
        return None
    substructure = document["下部構造"]
    layers = document["地盤データ"]["層"]
    if (substructure["基礎形式"] != "直接基礎" or not _blank_piles(document["杭基礎"])
            or any(layer["De"] is not None for layer in layers)):
        return None
    old: dict = {}
    for key, value in document.items():
        if key == "杭基礎":
            continue
        if key == "下部構造":
            sub: dict = {}
            for name, item in value.items():
                if name == "基礎形式":
                    sub |= {"杭種": item, "場所打ち杭の施工条件": None, "杭の配置": [_BLANK_PILE_ROW] * _OLD_PILE_ROWS}
                elif name == "単位体積重量":
                    sub[name] = {"梁・躯体": item["梁・躯体"], "フーチング": item["フーチング"],
                                 "杭": {"鉛直重量": None, "慣性力": None}, "上載土": item["上載土"]}
                else:
                    sub[name] = item
            old[key] = sub
        elif key == "地盤データ":
            old[key] = {**value, "層": [{("一軸圧縮強度_qu" if name == "粘着力_c" else name): item
                                         for name, item in layer.items() if name != "De"} for layer in layers]}
        else:
            old[key] = value
    text = json.dumps(old, indent=2, ensure_ascii=False) + "\n"
    return (text.replace("\n", "\r\n") if b"\r\n" in data else text).encode("utf-8")


def with_blank_rebar(document: dict) -> dict:
    """An input recorded before decision 91 in the form of today: the blank 鉄筋.杭 added (for a test that parses the
    recorded file)."""
    if "杭" in document["鉄筋"]:
        return document
    return {**document, "鉄筋": {**document["鉄筋"], "杭": json.loads(json.dumps(BLANK_PILE_REBAR))}}


def upgrade_to_piles(document: dict) -> dict:
    """An input recorded before decision 80 in the form of today (for a test that parses the recorded file): 基礎形式
    for 杭種 (the reserved pile items dropped), the empty 杭基礎 after 下部構造, c for qu and a blank De in each layer."""
    new: dict = {}
    for key, value in document.items():
        if key == "下部構造":
            new[key] = {("基礎形式" if name == "杭種" else name): (
                {part: item for part, item in item.items() if part != "杭"} if name == "単位体積重量" else item)
                for name, item in value.items() if name not in ("場所打ち杭の施工条件", "杭の配置")}
            new["杭基礎"] = {
                "杭長": None, "杭の単位体積重量": None,
                "場所打ち杭": {"杭径": None, "f'ck": None, "施工条件": None},
                "鋼管ソイルセメント杭": {"ソイルセメント径": None, "鋼管外径": None, "鋼管厚": None, "腐食代": None,
                              "鋼管材質": None, "結合部": {"軸方向鉄筋": {"径": None, "本数": None, "材質": None, "重心位置": None}, "中詰めコンクリート_f'ck": None}},
                "配置": {"形式": None, "線路方向の列の位置": [], "線路直角方向の列の位置": [], "抜く杭": []}}
        elif key == "地盤データ":
            new[key] = {**value, "層": [{**{("粘着力_c" if name == "一軸圧縮強度_qu" else name): item
                                             for name, item in layer.items()}, "De": None} for layer in value["層"]]}
        else:
            new[key] = value
    return new


def _before_outputs(data: bytes) -> set[str]:
    stripped, count = _OUTPUTS.subn(b"", data)
    return {sha256(data), *((sha256(stripped),) if count == 1 else ())}


def input_sha256s(data: bytes) -> set[str]:
    """The SHA256 an acceptance of the input *data* may record: of it as it is, as it was before the 出力項目, as it was with
    the bars of the cast-in-place pile in the 杭基礎, before them, before the joint and before the pile foundation (each
    with and without the 出力項目), each also as it was before decision 98, all also as before decision 101, all also as
    before decision 111, and all also as before decision 125."""
    found: set[str] = set()
    for current in (data, before_bearing_devices(data)):
        if current is None:
            continue
        for latest in (current, before_custom_tables(current)):
            if latest is None:
                continue
            for form in (latest, before_vehicles(latest)):
                if form is None:
                    continue
                found |= _chain(form)
                if (older := before_anchorage(form)) is not None:
                    found |= _chain(older)
    return found


def _chain(data: bytes) -> set[str]:
    found = _before_outputs(data)
    if (newest := with_bars_in_piles(data)) is not None:
        found |= _before_outputs(newest)
    if (newer := before_rebar(data)) is not None:
        found |= _before_outputs(newer)
        data = newer
    if (older := before_joint(data)) is not None:
        found |= _before_outputs(older)
        data = older
    if (old := before_piles(data)) is not None:
        found |= _before_outputs(old)
    return found
