"""The strict NDU validator: the written bytes pass, every malformed variant of them is rejected.

Each case edits the valid longitudinal NDU at the text level (one record changed, removed or added) and expects
an input error naming the problem. The validator is the product check of WebPier's dialect, not the
independent read-back used for acceptance.
"""

import re

import pytest

from jrsnap_support import model
from webpier.core.errors import InputError
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, validate_ndu, write_ndu


@pytest.fixture(scope="module")
def valid():
    return write_ndu(model("longitudinal"))


def text_lines(data):
    return data.decode("cp932").split("\r\n")[:-1]


def encode(lines):
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


def setting(key, value):
    def edit(lines):
        index = next(i for i, line in enumerate(lines) if line.split("=", 1)[0] == key)
        lines[index] = f"{key}={value}" if value is not None else key
        return lines
    return edit


def field(key, position, value):
    def edit(lines):
        index = next(i for i, line in enumerate(lines) if line.split("=", 1)[0] == key)
        name, body = lines[index].split("=", 1)
        fields = body.split(",")
        fields[position - 1] = value
        lines[index] = f"{name}={','.join(fields)}"
        return lines
    return edit


def remove(key):
    def edit(lines):
        return [line for line in lines if line.split("=", 1)[0] != key]
    return edit


def insert_after(key, line):
    def edit(lines):
        index = next(i for i, text in enumerate(lines) if text.split("=", 1)[0] == key)
        return lines[:index + 1] + [line] + lines[index + 1:]
    return edit


def both(*edits):
    def edit(lines):
        for change in edits:
            lines = change(lines)
        return lines
    return edit


def test_the_written_bytes_pass(valid):
    summary = validate_ndu(valid, LONGITUDINAL)
    assert (summary.joints, summary.elements, summary.rebar_rows, summary.cases) == (7, 6, 11, 8)
    assert (summary.member_loads, summary.joint_loads, summary.combinations) == (8, 10, 1)
    transverse = validate_ndu(write_ndu(model("transverse")), TRANSVERSE)
    assert (transverse.joints, transverse.cases, transverse.joint_loads, transverse.combinations) == (8, 9, 11, 2)


def test_bytes_of_the_other_direction_are_rejected(valid):
    with pytest.raises(InputError, match=re.escape("線路直角方向の基本ケースは9件が必要です（8件）")):
        validate_ndu(valid, TRANSVERSE)


@pytest.mark.parametrize("data,message", [
    ("Virsion=5.2.3.S.4\r\n", "末尾が CRLF の bytes"),
    (b"Virsion=5.2.3.S.4\n", "末尾が CRLF の bytes"),
    (b"Virsion=5.2.3.S.4\nDataName=x\r\n", "改行は CRLF だけ"),
    (b"Virsion=5.2\r3.S.4\r\n", "改行は CRLF だけ"),
    (b"DataName=\x81\x20\r\n", "CP932 が不正"),
])
def test_framing(data, message):
    with pytest.raises(InputError, match=re.escape(message)):
        validate_ndu(data, LONGITUDINAL)


CASES = {
    "control character": (setting("LoadTitle1", "固定\x01死荷重"), "制御文字のある行"),
    "duplicate key": (insert_after("KGNum", "KGNum=0"), "キーが不正または重複"),
    "bad key": (insert_after("KGNum", "Bad Key=0"), "キーが不正または重複"),
    "bare key": (setting("KGNum", None), "キーが不正または重複"),
    "SHABUZAI_INFO with a value": (setting("SHABUZAI_INFO", "1"), "キーが不正または重複"),
    "missing record": (remove("Tisou"), "レコードの順序・件数が不正です（"),
    "extra record": (insert_after("ErrInfo", "NDTPath=C:\\x.ndt"), "必要: （終わり）"),
    "missing count": (remove("JointNum"), "JointNum がありません"),
    "field count": (setting("ExOptLoad", "1,1"), "ExOptLoad の欄数が3ではありません"),
    "not a number": (field("JointXY2", 2, "-5.6m"), "JointXY2 第2欄: 数値が必要です"),
    "not an integer": (field("SectRein1-1", 3, "29.5"), "SectRein1-1 第3欄: 整数が必要です"),
    "out of range": (field("SectConc1", 1, "90"), "SectConc1 第1欄: 範囲外です"),
    "fixed value": (setting("ExOptDisp", "2,2,1,0,0,1,0,1"), "ExOptDisp 第8欄: 0 が必要です"),
    "header": (setting("Virsion", "5.1.10.S.4"), "Virsion 第1欄: '5.2.3.S.4' が必要です"),
    "title": (setting("DataTitle3", "x"), "DataTitle3 第1欄: '' が必要です"),
    "analysis steps": (field("DataInfo", 3, "0"), "DataInfo 第3欄: 範囲外です"),
    "limited step": (field("DataInfo", 6, "301"), "DataInfo: 限定増分の最終ステップは分割数以下が必要です"),
    "target": (field("DataInfo", 19, "0.3"), "DataInfo 第19欄: 範囲外です"),
    "zero target": (field("DataInfo", 19, "0"), "DataInfo 第19欄: 範囲外です"),
    "control node": (field("DataInfo", 4, "8"), "DataInfo 第4欄: 範囲外です"),
    "load count": (setting("LoadNum", "9"), "線路方向の基本ケースは8件が必要です（9件）"),
    "members and elements": (setting("MemberNum", "5"), "MemberNum と ElementNum は同じ数"),
    "same position": (field("JointXY2", 2, "-7.6"), "同じ位置の節点があります"),
    "element order": (both(field("ElementInfo1", 5, "2"), field("ElementInfo1", 6, "1"),
                           field("MemberInfo1", 1, "2"), field("MemberInfo1", 2, "1")),
                      "ElementInfo1: 鉛直・水平の要素で、i 端が上（または左）の端が必要です"),
    "member ends": (field("MemberInfo1", 2, "3"), "ElementInfo1 第6欄: 3 が必要です"),
    "inclined element": (field("JointXY2", 1, "0.5"), "ElementInfo1: 鉛直・水平の要素"),
    "length": (both(field("MemberLeng2", 1, "0.8"), field("MemberDvid2-1", 1, "0.8")),
               "MemberLeng2: 節点座標からの長さと一致しません"),
    "division length": (field("MemberDvid2-1", 1, "0.8"), "MemberDvid2-1 第1欄: 0.7 が必要です"),
    "duplicate element": (both(field("ElementInfo2", 5, "1"), field("ElementInfo2", 6, "2"),
                               field("MemberInfo2", 1, "1"), field("MemberInfo2", 2, "2"),
                               field("MemberLeng2", 1, "2"), field("MemberDvid2-1", 1, "2")),
                          "ElementInfo2: 同じ節点を結ぶ要素が重複しています"),
    "two M-θ elements": (setting("ElementInfo1", "2,0,0,0,1,2,1,0, , , ,0,0,1"), "M-θ 要素は 0.010 m の1要素だけ"),
    "rigid region": (field("ElementInfo1", 9, "999"), "ElementInfo1 第9欄: 1000 が必要です"),
    "element kind": (field("ElementInfo1", 1, "3"), "ElementInfo1 第1欄: 範囲外です"),
    "disconnected joint": (both(setting("JointNum", "8"), insert_after("JointXY7", "JointXY8=5,5,8"),
                                insert_after("SHABUZAI_JointXY7", "SHABUZAI_JointXY8=0,0,False")),
                           "要素でつながっていない節点があります"),
    "M-θ title": (field("NonLinInfo1", 10, "柱下端の非線形部材Mθ"), "20バイト以内"),
    # 操作説明書 2.1.6: the joints from the upper left (swapping the y of two joints breaks the order)
    "joint order": (both(field("JointXY1", 2, "-7.6"), field("JointXY2", 2, "-7.9")), "節点番号は上から"),
    # decision 66: Example2 La/d = 7600/2592 ≧ 2 needs 曲げ (1); a shorter La a せん断 (2), never below 1.25
    "failure mode": (field("NonLinInfo1", 4, "2"), "破壊形態は La/d ≧ 2 で曲げ（1）"),
    "failure mode code": (field("NonLinInfo1", 4, "3"), "NonLinInfo1 第4欄: 範囲外です"),
    "short shear span": (both(field("SectInfo1", 10, "3000"), field("NonLinInfo1", 4, "2")), "1.25 ≦ La/d < 2 でせん断（2）"),
    "unequal layers": (field("SectJikuNum1", 3, "2"), "SectJikuNum1: 上下面の主鉄筋の段数は同じ"),
    "too many layers": (setting("SectJikuNum1", "11,6,6,6,6,0"), "全行数の半分以下"),
    "rebar rows": (setting("SectJikuNum1", "12,1,1,1,1,0"), "レコードの順序・件数が不正です"),
    "steel grade": (field("SectJiku1", 1, "300"), "SectJiku1: 主鉄筋の強度は295・345・390"),
    "unequal spacing": (field("SectJiku1", 6, "140"), "上下面の間隔は同じ値"),
    "rebar order": (field("SectRein1-2", 1, "100"), "SectRein1-2: 芯位置は上面から増加し"),
    "rebar outside": (field("SectRein1-11", 1, "2690"), "SectRein1-11: 芯位置は上面から増加し"),
    "hoop halves": (field("SectSher1", 9, "6"), "SectSher1: 帯鉄筋とせん断補強鉄筋は同じ1組の値"),
    "hoop grade": (setting("SectSher1", "300,22,10,150,0,0,300,22,10,150"), "SectSher1: 帯鉄筋"),
    "safety factor": (field("SectSafe1", 7, "0"), "SectSafe1 第7欄: 範囲外です"),
    "safety constant": (field("SectSafe1", 12, "1.2"), "SectSafe1 第12欄: 1.3 が必要です"),
    "unset sentinel": (field("SectInfo1", 11, "0"), "SectInfo1 第11欄: '-3.402823E+38' が必要です"),
    "spring node": (field("SuppotInfo2", 2, "6"), "SuppotInfo と FootInfo は同じ1節点"),
    "friction angle": (field("FootInfo1", 11, "90"), "FootInfo1 第11欄: 範囲外です"),
    "linked check": (setting("ChokuKisoNum", "1"), "ChokuKisoNum 第1欄: 範囲外です"),
    "load kind": (field("MLoadInfo5", 5, "2"), "MLoadInfo5: 要素荷重の種類は1（台形）か4（軸方向一様）"),
    "axial end value": (field("MLoadInfo1", 9, "297.68"), "MLoadInfo1 第9欄: ' ' が必要です"),
    "empty joint load": (both(field("JLoadInfo5", 6, " ")), "JLoadInfo5: H・N・M のいずれかが必要です"),
    "mixed increments": (field("JLoadInfo10", 4, "0"), "LoadCase8: 荷重種別"),
    "unknown increment": (both(*(field(f"MLoadInfo{i}", 4, "2") for i in range(5, 9)), field("JLoadInfo10", 4, "2")),
                          "LoadCase8: 荷重種別"),
    "load case of a row": (field("JLoadInfo1", 1, "2"), "JLoadInfo1 第1欄: 1 が必要です"),
    "load total": (setting("MLoadNum", "7"), "MLoadNum 第1欄: 範囲外です"),
    "load value": (field("JLoadInfo1", 6, "1e10"), "JLoadInfo1 第6欄: 範囲外です"),
    "coefficient": (field("SNAPConb1", 5, "2"), "SNAPConb1 第5欄: 範囲外です"),
    "linear set": (field("ConbAlpf1", 2, "0"), "ConbAlpf1 第2欄: 1 が必要です"),
    "combination rho": (field("SNAPConb1", 1, "1.1"), "SNAPConb1 第1欄: 1 が必要です"),
    "combination count": (setting("ConbNum", "2"), "ConbNum 第1欄: 範囲外です"),
    "long title": (setting("LoadTitle1", "あ" * 21), "40バイト以内"),
    "title separator": (field("JLoadInfo1", 8, "上部工=反力"), "区切り文字"),
    "font": (setting("FontName", "MS Gothic"), "FontName 第1欄: 'ＭＳ Ｐゴシック' が必要です"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_malformed_records_are_rejected(valid, name):
    edit, message = CASES[name]
    with pytest.raises(InputError, match=re.escape(message)):
        validate_ndu(encode(edit(text_lines(valid))), LONGITUDINAL)
