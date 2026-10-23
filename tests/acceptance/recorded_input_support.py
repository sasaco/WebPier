"""The input an acceptance may have been recorded from (decisions 72 and 84).

The real-runner acceptances recorded so far were made before the input had ``outputs``, and before it had the pile
foundation (``基礎形式``, ``杭基礎``, ``粘着力_c``, ``De``). Neither is a condition of the calculation of a direct
foundation: the 出力項目 only choose which reports a generation makes (ADR-0011), and the pile items are not read for a
direct foundation, whose layers keep their values (c replaced qu, which was 0 or blank). So such an acceptance still
belongs to current.json when everything but them is the recorded bytes. ``input_sha256s`` gives the SHA256 of the input
as it is (an acceptance recorded from now on), without its last item ``outputs`` (one recorded before decision 72), and
as it was before the pile foundation (one recorded before decision 84), also without ``outputs``; the tests still compare
the files the engines are given.
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
        "鋼管ソイルセメント杭": {"ソイルセメント径": None, "鋼管外径": None, "鋼管厚": None, "腐食代": None},
        "配置": {"形式": None, "線路方向の列の位置": [], "線路直角方向の列の位置": [], "抜く杭": []}}


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
                "杭長": None, "杭の単位体積重量": None, "場所打ち杭": {"杭径": None, "f'ck": None, "施工条件": None},
                "鋼管ソイルセメント杭": {"ソイルセメント径": None, "鋼管外径": None, "鋼管厚": None, "腐食代": None},
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
    """The SHA256 an acceptance of the input *data* may record: of it as it is, as it was before the 出力項目, and as it
    was before the pile foundation (with and without the 出力項目)."""
    found = _before_outputs(data)
    if (old := before_piles(data)) is not None:
        found |= _before_outputs(old)
    return found
