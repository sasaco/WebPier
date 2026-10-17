"""NDU bytes: CP932 / CRLF, the native record layout, and the records equal to the Example2 NDU files.

The Example2 files are JRSNAP 5.1.10 saves; 5.2-L03 adds fields at the end of DataInfo, SectInfo, SectSafe and
FootInfo (recorded in README JRSNAP), so those are compared on the
5.1 fields. Records that differ on purpose: Virsion; MemberNum and the member blocks (one native member per
element here, two grouped members there); SectTitle / NonLinInfo1 titles; FootInfo Df and γ2 (derived); the
linked foundation check, soil link, ground layers and NDTPath (inactive here); the loads listed in
test_jrsnap_model.py; GanmaA written 1.2,1,1,1 for 1.20,1.00,1.00,1.00.
"""

import re
from decimal import Decimal

import pytest

from jrsnap_support import example2, model
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.export.jrsnap import write_ndu
from webpier.export.jrsnap.validate import check_text
from webpier.export.jrsnap.writer import field, number


def lines(data):
    return {line.split("=", 1)[0]: line.split("=", 1)[1] if "=" in line else None
            for line in data.decode("cp932").split("\r\n")[:-1]}


@pytest.fixture(scope="module", params=["longitudinal", "transverse"])
def written(request):
    return request.param, write_ndu(model(request.param))


def test_bytes_are_cp932_with_crlf(written):
    _, data = written
    assert data.startswith(b"Virsion=5.2.3.S.4\r\n") and data.endswith(b"\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"") and b"\r" not in data.replace(b"\r\n", b"")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert "固定死荷重".encode("cp932") in data


def test_the_bytes_are_deterministic(written):
    direction, data = written
    assert write_ndu(model(direction)) == data


SAME = ["DataName", *(f"DataTitle{i}" for i in range(1, 21)), "ExOptLoad", "ExOptDisp", "KGNum", "HendoCaseInfo",
        "JibanCaseNum", "TyakumokuNum", "SHABUZAI_INFO", "NonLinNum", "SectNum", "SectConc1", "SectJikuNum1",
        "SectJiku1", "SectSher1", "SuppotNum", "SuppotRow", "SuppotAlf", "ShitenCaseNum", "SuppotInfo1", "SuppotInfo2",
        "FootRow", "JibanTeikouKeisuu1", "JibanTeikouKeisuu2", "JibanTeikouKeisuu3", "PickNum", "Conb2Num",
        "Pick2Num", "SesfNum", "SesfKihonNum", "SesfPiM", "SesfPiS", "SesfPiBuzai", "FontColor", "FontSize",
        "FontName", "LineColor", "LineWidth", "Sunpo", "JointCircle", "Grid", "ErrInfo", "ELoadNum", "ELoadRow",
        "DLoadNum", "DLoadRow"]
PREFIX = {"DataInfo": 23, "SectInfo1": 12, "SectSafe1": 11, "FootInfo1": 7}


def test_records_equal_to_example2(written):
    direction, data = written
    built, sample = lines(data), {key: ",".join(fields) for key, fields in example2(direction).items()}
    sample["SHABUZAI_INFO"] = None
    count = {"longitudinal": (7, 6, 11), "transverse": (8, 7, 31)}[direction]
    keys = SAME + [f"ElementInfo{i}" for i in range(1, count[1] + 1)] + [
        f"JibanShogenInfo{i}" for i in range(1, count[1] + 1)] + [
        f"ElementTyakumokuNum{i}" for i in range(1, count[1] + 1)] + [
        f"SHABUZAI_JointXY{i}" for i in range(1, count[0] + 1)] + [
        f"SesfPiIJ{i}" for i in range(1, count[1] + 1)] + [f"SectRein1-{i}" for i in range(1, count[2] + 1)] + [
        f"{key}{case}" for key in ("LoadTitle", "LoadCase", "LoadAlph") for case in range(1, 5)]
    for key in keys:
        assert built[key] == sample[key], key
    for key, size in PREFIX.items():
        assert built[key].split(",")[:size] == sample[key].split(",")[:size], key


def test_longitudinal_records_equal_to_example2():
    built = lines(write_ndu(model("longitudinal")))
    sample = {key: ",".join(fields) for key, fields in example2("longitudinal").items()}
    for key in ["JointOrg", "JointNum", "ElementNum", "LoadNum", "SNAPConbNum", "SNAPConb1", "ConbNum", "ConbAlpf1",
                *(f"JointXY{i}" for i in range(2, 8)),
                *(f"{key}{case}" for key in ("LoadTitle", "LoadCase", "LoadAlph") for case in range(5, 9))]:
        assert built[key] == sample[key], key
    # Example2 writes the four column members as one range record "1,1,4,..."; WebPier one record per element.
    assert built["MLoadInfo1"] == "1, ,1,0,4, , ,297.68, , , ,柱自重"
    assert sample["MLoadInfo1"] == "1,1,4,0,4, , ,297.68, , , ,柱自重"
    assert built["JLoadInfo1"] == sample["JLoadInfo1"] == "1, ,1,0, ,8299.53,-610,上部工反力"
    assert built["JLoadInfo8"] == sample["JLoadInfo8"] == "6, ,1,1,-11530, , ,上部工慣性力"
    assert built["JLoadInfo9"] == sample["JLoadInfo9"] == "7, ,1,4,-128, , ,列車慣性力"


def test_transverse_records():
    built = lines(write_ndu(model("transverse")))
    assert built["DataName"] == "線路直角方向" and built["JointOrg"] == "6" and built["LoadNum"] == "9"
    assert built["JointXY1"] == "0,-10.35,1" and built["JointXY8"] == "0,2.7,8"
    assert built["DataInfo"].split(",")[2:7] == ["350", "1", "1000", "300", " "]
    assert built["SNAPConbNum"] == built["ConbNum"] == "2"
    assert built["SNAPConb1"] == "1,1,0,0,1,1,1,1,1,0,1,1,1, , , , , , ,0,0"
    assert built["SNAPConb2"] == "1,1,0,0,1,1,1,1,0,1,1,1,1, , , , , , ,0,0"
    assert built["ConbAlpf2"] == "1,1,1,1,0,1,1,1,1"
    assert built["JLoadInfo7"] == "5, ,2,0, ,480,1028.62,列車荷重"
    assert built["JLoadInfo8"] == "6, ,2,0, ,480,-1028.62,列車荷重"
    assert built["MLoadInfo5"] == "9, ,2,1,1, , ,-595.35,-595.35, , ,自重慣性力"


def test_layout_of_the_v52_fields():
    built = lines(write_ndu(model("longitudinal")))
    assert built["DataInfo"] == "1,1,300,1,1000,200, , , ,999,999,1,1,1,1,1,1,1,-0.3,0.001,0,1,0,0,0,0"
    assert built["SectInfo1"] == "1,1,0,1,4500,2700,0,0,0,7600,-3.402823E+38,0,0,0"
    assert built["TanbuShiji1"] == "0,0"
    assert built["SectSafe1"] == "1.3,1,1.05,1,1,1.15,2,1.3,0,0.9,1.8,1.3"
    assert built["FootInfo1"] == " ,7,1,7,9,405976,0,4.7,10,12.3,42.2,2,20,-3.402823E+38"
    assert built["NonLinInfo1"] == "1,1,1,1,1,1,1,1,0,柱下端Mθ"
    assert built["MemberTitle4"] == "柱下端" and built["MemberDvid4-1"] == "0.01,1"
    assert built["Tisou"] == "" and built["TishouNum"] == "0" and built["ChokuKisoNum"] == "0"
    assert "NDTPath" not in built and "SRenkeiNum" not in built


@pytest.mark.parametrize("value,text", [
    (Decimal("4500.0"), "4500"), (Decimal("-0.30"), "-0.3"), (Decimal("0.000"), "0"), (Decimal("-0"), "0"),
    (Decimal("25576488"), "25576488"), (Decimal("1E+3"), "1000"), (Decimal("0.001"), "0.001"),
])
def test_numbers_are_written_as_printed(value, text):
    assert number(value) == text


def test_fields():
    assert field(Printed(1028.62, 2, "kN m")) == "1028.62" and field(Printed(-0.0, 2, "kN")) == "0"
    assert (field(True), field(False), field(7)) == ("True", "False", "7")
    assert field("上載土") == "上載土"


@pytest.mark.parametrize("text,message", [
    ("固定,死荷重", "区切り文字"), ("a=b", "区切り文字"), ("改\t行", "制御文字"), ("é", "CP932 で表せない文字"),
    ("あ" * 21, "40バイト以内"),
])
def test_text_must_fit_the_native_field(text, message):
    with pytest.raises(InputError, match=re.escape(message)):
        field(text)


def test_the_m_theta_title_limit():
    assert check_text("あ" * 10, 20) == "あ" * 10
    with pytest.raises(InputError, match="20バイト以内"):
        check_text("あ" * 11, 20)
