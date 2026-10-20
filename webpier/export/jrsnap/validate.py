"""Strict check of the NDU bytes WebPier writes: framing, record order, field counts and values, references.

This validates the dialect of ``records`` for one profile, not an arbitrary NDU or one JRSNAP has edited and
saved; reading an NDU back for acceptance is a separate, independent parser. Checked:

- CP932, CRLF after every record, no other line break, no control character, unique keys;
- the complete record order the native reader consumes, from the counts in the file;
- every field: the fixed and inactive values, numbers within the native input ranges, integers where IDs or
  counts are, blanks where JRSNAP keeps "not set", text of at most 40 bytes (20 for the M-θ title);
- the model: joints at distinct positions, one element per member with matching ends and lengths, vertical or
  horizontal elements from their upper or left end, all joints connected, exactly one 0.010 m M-θ element and
  rigid regions elsewhere, the section table in order inside the section, the springs and FootInfo at one
  joint, the load cases of the profile with one load kind each, the combinations over those cases.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from ...core.errors import InputError
from .profile import (
    CONVERGENCE, LOAD_DIVISIONS, MIN_SHEAR_SPAN_RATIO, NATIVE_VERSION, RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS,
    ROTATION_KR2, ROTATION_KR3, SAFETY_BEFORE, SAFETY_GBS, SAFETY_GBVO, SAFETY_K, SHEAR_SPAN_RATIO_BENDING, SOIL_TYPE,
    STEEL_MODULUS, TRIALS, Profile,
)
from .records import COMBINATION_SLOTS, CONSTANT_RECORDS, RESISTANCE, TITLES

TEXT_BYTES = 40
NONLINEAR_TITLE_BYTES = 20
UNSET = "-3.402823E+38"
MAX_JOINTS, MAX_MEMBERS, MAX_ROWS, MAX_LOADS, MAX_COMBINATIONS = 2500, 400, 100, 9999, 99
MAX_STEPS = 100_000
COORDINATE = Decimal(20000)
SIZE = (Decimal("0.1"), Decimal(999999))
LOAD_LIMIT = Decimal(10) ** 10
MICRO = Decimal("0.01")
STEEL_GRADES = (295, 345, 390)
FACTOR_MAX = Decimal("99.99")
LOAD_KINDS = (0, 1, 4)
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")
_KEY = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:-[0-9]+)?")
BARE = "SHABUZAI_INFO"


def _error(message: str) -> InputError:
    return InputError(f"JRSNAP: {message}")


def check_text(value: str, limit: int) -> str:
    if any(ord(char) < 32 or ord(char) == 127 or char in ",=" for char in value):
        raise _error(f"文字列に制御文字または区切り文字（, =）があります: {value!r}")
    try:
        size = len(value.encode("cp932", errors="strict"))
    except UnicodeEncodeError:
        raise _error(f"CP932 で表せない文字があります: {value!r}") from None
    if size > limit:
        raise _error(f"文字列は CP932 で{limit}バイト以内が必要です（{size}バイト）: {value!r}")
    return value


@dataclass(frozen=True)
class Num:
    """A number field: within [low, high] (open at an end when asked), an integer when asked."""

    low: Decimal | int | None = None
    high: Decimal | int | None = None
    open_low: bool = False
    open_high: bool = False
    integer: bool = False


POSITIVE = Num(0, open_low=True)
SIZE_MM = Num(*SIZE)
FACTOR = Num(0, FACTOR_MAX, open_low=True)
LOAD = Num(-LOAD_LIMIT, LOAD_LIMIT, open_low=True, open_high=True)


@dataclass(frozen=True)
class Text:
    limit: int = TEXT_BYTES


@dataclass(frozen=True)
class Optional_:
    """A blank or a number."""

    number: Num


Spec = Num | Text | Optional_ | str | int | Decimal


@dataclass(frozen=True)
class NduSummary:
    joints: int
    elements: int
    rebar_rows: int
    cases: int
    member_loads: int
    joint_loads: int
    combinations: int


def _decimal(text: str, where: str) -> Decimal:
    if _NUMBER.fullmatch(text) is None:
        raise _error(f"{where}: 数値が必要です（{text!r}）")
    return Decimal(text)


def _number(text: str, spec: Num, where: str) -> Decimal:
    value = _decimal(text, where)
    if spec.integer and value != value.to_integral_value():
        raise _error(f"{where}: 整数が必要です（{text}）")
    low_ok = spec.low is None or (value > spec.low if spec.open_low else value >= spec.low)
    high_ok = spec.high is None or (value < spec.high if spec.open_high else value <= spec.high)
    if not (low_ok and high_ok):
        raise _error(f"{where}: 範囲外です（{text}）")
    return value


class _File:
    def __init__(self, data: bytes) -> None:
        if not isinstance(data, bytes) or not data.endswith(b"\r\n"):
            raise _error("NDU は末尾が CRLF の bytes が必要です")
        if b"\r" in data.replace(b"\r\n", b"") or b"\n" in data.replace(b"\r\n", b""):
            raise _error("NDU の改行は CRLF だけが必要です")
        try:
            text = data.decode("cp932", errors="strict")
        except UnicodeDecodeError:
            raise _error("NDU の CP932 が不正です") from None
        self.records: dict[str, list[str]] = {}
        self.order: list[str] = []
        for line in text.split("\r\n")[:-1]:
            if any(ord(char) < 32 or ord(char) == 127 for char in line):
                raise _error(f"制御文字のある行です: {line!r}")
            key, separator, body = line.partition("=")
            if _KEY.fullmatch(key) is None or key in self.records or (not separator) != (key == BARE):
                raise _error(f"レコードのキーが不正または重複しています: {line!r}")
            self.records[key] = body.split(",") if separator else []
            self.order.append(key)

    def row(self, key: str, size: int) -> list[str]:
        if key not in self.records:
            raise _error(f"{key} がありません")
        fields = self.records[key]
        if len(fields) != size:
            raise _error(f"{key} の欄数が{size}ではありません（{len(fields)}）")
        return fields

    def fields(self, key: str, *spec: Spec) -> list:
        values = []
        for index, (text, item) in enumerate(zip(self.row(key, len(spec)), spec), 1):
            where = f"{key} 第{index}欄"
            if isinstance(item, Num):
                values.append(_number(text, item, where))
            elif isinstance(item, Optional_):
                values.append(None if text == " " else _number(text, item.number, where))
            elif isinstance(item, Text):
                values.append(check_text(text, item.limit))
            elif isinstance(item, str):
                if text != item:
                    raise _error(f"{where}: {item!r} が必要です（{text!r}）")
                values.append(text)
            else:
                if _decimal(text, where) != Decimal(item):
                    raise _error(f"{where}: {item} が必要です（{text}）")
                values.append(Decimal(item))
        return values

    def count(self, key: str, low: int, high: int) -> int:
        (value,) = self.fields(key, Num(low, high, integer=True))
        return int(value)


def _ints(values: Iterable) -> list[int]:
    return [int(value) for value in values]


class _Validator:
    def __init__(self, data: bytes, profile: Profile) -> None:
        self.file, self.profile = _File(data), profile

    def run(self) -> NduSummary:
        f = self.file
        self.nn = f.count("JointNum", 1, MAX_JOINTS)
        self.ne = f.count("ElementNum", 1, MAX_MEMBERS)
        if f.count("MemberNum", 1, MAX_MEMBERS) != self.ne:
            raise _error("MemberNum と ElementNum は同じ数（1部材1要素）が必要です")
        self.node = Num(1, self.nn, integer=True)
        self.nr = int(_number(f.row("SectJikuNum1", 6)[0], Num(1, MAX_ROWS, integer=True), "SectJikuNum1 第1欄"))
        self.nc = f.count("LoadNum", 1, COMBINATION_SLOTS)
        # Without snow there is no 雪荷重 case and the cases after it move up (decision 69). With a load model the
        # cases are those it declares, by their names in its order (decision 70; generic_profile): none is SNOW.
        titles = list(self.profile.case_titles.values())
        snowless = [title for case, title in self.profile.case_titles.items() if getattr(case, "name", None) != "SNOW"]
        if self.nc not in (len(titles), len(snowless)):
            raise _error(f"{self.profile.data_name}の基本ケースは{len(titles)}件（雪荷重がなければ{len(snowless)}件）"
                         f"が必要です（{self.nc}件）")
        self.titles = titles if self.nc == len(titles) else snowless
        self.rows = {family: [f.count(f"{family}LoadRow{case}", 0, MAX_LOADS) for case in range(1, self.nc + 1)]
                     for family in ("M", "J")}
        self.nk = f.count("SNAPConbNum", 1, MAX_COMBINATIONS)
        self._order()
        self._head()
        self._frame()
        self._section()
        self._supports()
        loads = self._loads()
        self._tail()
        return NduSummary(joints=self.nn, elements=self.ne, rebar_rows=self.nr, cases=self.nc,
                          member_loads=loads[0], joint_loads=loads[1], combinations=self.nk)

    def _order(self) -> None:
        nn, ne = range(1, self.nn + 1), range(1, self.ne + 1)
        expected = ["Virsion", "DataName", *(f"DataTitle{i}" for i in range(1, TITLES + 1)), "DataInfo",
                    "ExOptLoad", "ExOptDisp", "JointOrg", "JointNum", *(f"JointXY{i}" for i in nn), "MemberNum"]
        for i in ne:
            expected += [f"MemberTitle{i}", f"MemberInfo{i}", f"MemberLeng{i}", f"MemberOkuyuki{i}",
                         f"MemberDvid{i}-1", f"MemberShogen{i}"]
        expected += [*(f"MemberKUI{i}" for i in ne), "KGNum", "ElementNum", *(f"ElementInfo{i}" for i in ne),
                     "HendoCaseInfo", "JibanCaseNum", *(f"JibanShogenInfo{i}" for i in ne), "TyakumokuNum",
                     *(f"ElementTyakumokuNum{i}" for i in ne), BARE, *(f"SHABUZAI_JointXY{i}" for i in nn),
                     *(f"ShabuzaiMeInfo{i}" for i in ne), "NonLinNum", "NonLinInfo1", "SectNum", "SectTitle1",
                     "SectInfo1", "TanbuShiji1", "SectConc1", "SectJikuNum1", "SectJiku1",
                     *(f"SectRein1-{i}" for i in range(1, self.nr + 1)), "SectSher1", "SectSafe1", "SuppotNum",
                     "SuppotRow", "SuppotAlf", "ShitenCaseNum", "SuppotInfo1", "SuppotInfo2", "FootRow", "FootInfo1",
                     "ChokuKisoNum", "G_intCHOKU_KISO_Link_Num", "Suppot_ChokuKisoCaseNo1", "Suppot_ChokuKisoCaseNo2",
                     "Foot_ChokuKisoCaseNo1", *(f"Member_BunpuBane{i}" for i in ne),
                     *(f"JibanTeikouKeisuu{i}" for i in range(1, len(RESISTANCE) + 1)), "LoadNum", "MLoadNum",
                     "JLoadNum"]
        member = joint = 0
        for case in range(1, self.nc + 1):
            expected += [f"LoadTitle{case}", f"LoadCase{case}", f"LoadAlph{case}", f"MLoadRow{case}"]
            expected += [f"MLoadInfo{i}" for i in range(member + 1, member + self.rows["M"][case - 1] + 1)]
            expected.append(f"JLoadRow{case}")
            expected += [f"JLoadInfo{i}" for i in range(joint + 1, joint + self.rows["J"][case - 1] + 1)]
            member += self.rows["M"][case - 1]
            joint += self.rows["J"][case - 1]
        nk = range(1, self.nk + 1)
        expected += ["ELoadNum", "ELoadRow", "DLoadNum", "DLoadRow", "SNAPConbNum", *(f"SNAPConb{i}" for i in nk),
                     "ConbNum", *(f"ConbAlpf{i}" for i in nk), "PickNum", "Conb2Num", "Pick2Num", "TishouNum", "Tisou",
                     "SesfNum", *(f"SesfPiIJ{i}" for i in ne), "SesfKihonNum", "SesfPiM", "SesfPiS", "SesfPiBuzai",
                     "GanmaA", "FontColor", "FontSize", "FontName", "LineColor", "LineWidth", "Sunpo", "JointCircle",
                     "Grid", "ErrInfo"]
        if self.file.order != expected:
            first = next(i for i, (a, b) in enumerate(zip(self.file.order + [""], expected + [""])) if a != b)
            found = self.file.order[first] if first < len(self.file.order) else "（終わり）"
            raise _error(f"レコードの順序・件数が不正です（{first + 1}行目: {found}、必要: "
                         f"{expected[first] if first < len(expected) else '（終わり）'}）")

    def _constant(self, key: str, values: tuple) -> None:
        self.file.fields(key, *(value if isinstance(value, (int, Decimal)) else str(value) for value in values))

    def _head(self) -> None:
        f = self.file
        f.fields("Virsion", NATIVE_VERSION)
        f.fields("DataName", self.profile.data_name)
        for index in range(1, TITLES + 1):
            f.fields(f"DataTitle{index}", "")
        steps = Num(1, MAX_STEPS, integer=True)
        # The target displacement is not 0 and has the sign of the earthquake of the profile.
        target = Num(0, open_low=True) if self.profile.earthquake > 0 else Num(high=0, open_high=True)
        info = f.fields("DataInfo", 1, 1, steps, self.node, LOAD_DIVISIONS, steps, " ", " ", " ", TRIALS, TRIALS,
                        1, 1, 1, 1, 1, POSITIVE, POSITIVE, target, CONVERGENCE, 0, 1, 0, 0, 0, 0)
        if info[5] > info[2]:
            raise _error("DataInfo: 限定増分の最終ステップは分割数以下が必要です")
        self.rho_alpha = info[16:18]
        for key in ("ExOptLoad", "ExOptDisp"):
            self._constant(key, CONSTANT_RECORDS[key])
        (self.origin,) = _ints(f.fields("JointOrg", self.node))

    def _frame(self) -> None:
        f = self.file
        joints = {}
        for index in range(1, self.nn + 1):
            x, y, _ = f.fields(f"JointXY{index}", Num(-COORDINATE, COORDINATE), Num(-COORDINATE, COORDINATE), index)
            joints[index] = (x, y)
        if len(set(joints.values())) != self.nn:
            raise _error("同じ位置の節点があります")
        # 操作説明書 2.1.6: numbered from the upper left, so a vertical element has the smaller number at its top
        if sorted(joints, key=lambda n: (joints[n][1], joints[n][0])) != list(joints):
            raise _error("節点番号は上から、同じ高さでは左から順に付ける必要があります（操作説明書 2.1.6）")
        edges, nonlinear = set(), []
        for index in range(1, self.ne + 1):
            f.fields(f"MemberTitle{index}", Text())
            i, j, _ = _ints(f.fields(f"MemberInfo{index}", self.node, self.node, 1))
            (length,) = f.fields(f"MemberLeng{index}", POSITIVE)
            f.fields(f"MemberOkuyuki{index}", 1)
            f.fields(f"MemberDvid{index}-1", length, 1)
            f.fields(f"MemberShogen{index}", 1)
            f.fields(f"MemberKUI{index}", 0)
            kind = int(_number(f.row(f"ElementInfo{index}", 14)[0], Num(1, 2, integer=True),
                               f"ElementInfo{index} 第1欄"))
            stiffness = (" ", " ", " ") if kind == 2 else (RIGID_AREA, RIGID_INERTIA, RIGID_MODULUS)
            f.fields(f"ElementInfo{index}", kind, 0, 0, 0, i, j, int(kind == 2), 0, *stiffness, 0, 0, index)
            (xi, yi), (xj, yj) = joints[i], joints[j]
            if i == j or (xi != xj and yi != yj) or (yi, xi) >= (yj, xj):
                raise _error(f"ElementInfo{index}: 鉛直・水平の要素で、i 端が上（または左）の端が必要です")
            if abs(xj - xi) + abs(yj - yi) != length:
                raise _error(f"MemberLeng{index}: 節点座標からの長さと一致しません（{length}）")
            if frozenset((i, j)) in edges:
                raise _error(f"ElementInfo{index}: 同じ節点を結ぶ要素が重複しています")
            edges.add(frozenset((i, j)))
            if kind == 2:
                nonlinear.append(length)
        if nonlinear != [MICRO]:
            raise _error("M-θ 要素は 0.010 m の1要素だけが必要です")
        reached, pending = set(), [self.origin]
        while pending:
            joint = pending.pop()
            reached.add(joint)
            pending += [other for edge in edges if joint in edge for other in edge if other not in reached]
        if reached != set(joints):
            raise _error("要素でつながっていない節点があります")
        f.count("KGNum", 0, 0)
        self._constant("HendoCaseInfo", CONSTANT_RECORDS["HendoCaseInfo"])
        f.count("JibanCaseNum", 1, 1)
        f.count("TyakumokuNum", 0, 0)
        f.fields(BARE)
        for index in range(1, self.ne + 1):
            f.fields(f"JibanShogenInfo{index}", *(" ",) * 7)
            f.fields(f"ElementTyakumokuNum{index}", 0, 0)
            f.fields(f"ShabuzaiMeInfo{index}", *(0,) * 9, "False", "False")
        for index in range(1, self.nn + 1):
            f.fields(f"SHABUZAI_JointXY{index}", 0, 0, "False")
        f.fields("NonLinNum", 1, 1, 0)
        # the 破壊形態: 1 曲げ or 2 せん断, checked against La/d with the section (decision 66)
        self.failure = int(f.fields("NonLinInfo1", 1, 1, 1, Num(1, 2, integer=True), 1, 1, 1, 1, 0,
                                    Text(NONLINEAR_TITLE_BYTES))[3])

    def _section(self) -> None:
        f = self.file
        f.count("SectNum", 1, 1)
        f.fields("SectTitle1", Text())
        info = f.fields("SectInfo1", 1, 1, 0, 1, SIZE_MM, SIZE_MM, 0, 0, 0, SIZE_MM, UNSET, 0, 0, 0)
        height = info[5]
        self._constant("TanbuShiji1", CONSTANT_RECORDS["TanbuShiji1"])
        f.fields("SectConc1", Num(18, 80), 0, POSITIVE, 0, SIZE_MM)
        layers = Num(1, self.nr, integer=True)
        counts = _ints(f.fields("SectJikuNum1", self.nr, layers, layers, layers, layers, 0)[1:5])
        if len(set(counts)) != 1 or 2 * counts[0] > self.nr:
            raise _error("SectJikuNum1: 上下面の主鉄筋の段数は同じで、全行数の半分以下が必要です")
        main = f.fields("SectJiku1", Num(min(STEEL_GRADES), max(STEEL_GRADES), integer=True), STEEL_MODULUS, 0, 0,
                        POSITIVE, POSITIVE, 0, 0, 0)
        if main[0] not in STEEL_GRADES or main[4] != main[5]:
            raise _error("SectJiku1: 主鉄筋の強度は295・345・390、上下面の間隔は同じ値が必要です")
        previous = Decimal(-1)
        for index in range(1, self.nr + 1):
            center, diameter, _ = f.fields(f"SectRein1-{index}", Num(0), POSITIVE, Num(1, integer=True))
            if center <= previous or not diameter / 2 <= center <= height - diameter / 2:
                raise _error(f"SectRein1-{index}: 芯位置は上面から増加し、鉄筋が断面内にあることが必要です")
            if index == 1:
                depth = height - center
            previous = center
        span = info[9]
        if span < MIN_SHEAR_SPAN_RATIO * depth or self.failure != (2 if span < SHEAR_SPAN_RATIO_BENDING * depth else 1):
            raise _error("NonLinInfo1・SectInfo1: 破壊形態は La/d ≧ 2 で曲げ（1）、1.25 ≦ La/d < 2 でせん断（2）が必要です")
        hoop = f.fields("SectSher1", Num(min(STEEL_GRADES), max(STEEL_GRADES), integer=True), POSITIVE,
                        Num(1, integer=True), POSITIVE, 0, 0, *(Num(),) * 4)
        if hoop[0] not in STEEL_GRADES or hoop[:4] != hoop[6:]:
            raise _error("SectSher1: 帯鉄筋とせん断補強鉄筋は同じ1組の値（強度295・345・390）が必要です")
        f.fields("SectSafe1", *SAFETY_BEFORE, FACTOR, FACTOR, SAFETY_GBS, SAFETY_K, FACTOR, SAFETY_GBVO)

    def _supports(self) -> None:
        f = self.file
        f.count("SuppotNum", 3, 3)
        f.count("SuppotRow", 2, 2)
        f.fields("SuppotAlf", 0, 0)
        f.count("ShitenCaseNum", 0, 0)
        nodes = {int(f.fields(f"SuppotInfo{index}", " ", self.node, index, POSITIVE, *(" ",) * 9)[1])
                 for index in (1, 2)}
        f.count("FootRow", 1, 1)
        foot = f.fields("FootInfo1", " ", self.node, SOIL_TYPE, POSITIVE, POSITIVE, POSITIVE, 0, POSITIVE, POSITIVE,
                        POSITIVE, Num(25, 90, open_high=True), ROTATION_KR2, ROTATION_KR3, UNSET)
        if nodes != {int(foot[1])}:
            raise _error("SuppotInfo と FootInfo は同じ1節点（基礎底面）が必要です")
        for key in ("ChokuKisoNum", "G_intCHOKU_KISO_Link_Num", "Suppot_ChokuKisoCaseNo1", "Suppot_ChokuKisoCaseNo2",
                    "Foot_ChokuKisoCaseNo1", *(f"Member_BunpuBane{i}" for i in range(1, self.ne + 1))):
            f.count(key, 0, 0)
        for index, coefficient in enumerate(RESISTANCE, 1):
            f.fields(f"JibanTeikouKeisuu{index}", *(coefficient,) * 5)

    def _loads(self) -> tuple[int, int]:
        f = self.file
        totals = [sum(self.rows["M"]), sum(self.rows["J"])]
        f.count("MLoadNum", totals[0], totals[0])
        f.count("JLoadNum", totals[1], totals[1])
        element, kinds = Num(1, self.ne, integer=True), Num(0, 4, integer=True)
        member = joint = 0
        for case in range(1, self.nc + 1):
            (title,) = f.fields(f"LoadTitle{case}", Text())
            if title != self.titles[case - 1]:
                raise _error(f"LoadTitle{case}: {self.profile.data_name}の基本ケース{case}は「{self.titles[case - 1]}」が"
                             f"必要です（{title}）")
            f.fields(f"LoadCase{case}", 1, 1, 0)
            f.fields(f"LoadAlph{case}", 1)
            increments = set()
            for _ in range(self.rows["M"][case - 1]):
                member += 1
                key = f"MLoadInfo{member}"
                kind = f.row(key, 12)[4]
                end = " " if kind == "4" else LOAD
                values = f.fields(key, case, " ", element, kinds, Num(1, 4, integer=True), " ", " ", LOAD, end, " ",
                                  " ", Text())
                if values[4] not in (1, 4):
                    raise _error(f"{key}: 要素荷重の種類は1（台形）か4（軸方向一様）が必要です")
                increments.add(values[3])
            for _ in range(self.rows["J"][case - 1]):
                joint += 1
                key = f"JLoadInfo{joint}"
                values = f.fields(key, case, " ", self.node, kinds, *(Optional_(LOAD),) * 3, Text())
                if values[4:7] == [None, None, None]:
                    raise _error(f"{key}: H・N・M のいずれかが必要です")
                increments.add(values[3])
            if not increments <= set(LOAD_KINDS) or len(increments) > 1:
                raise _error(f"LoadCase{case}: 荷重種別（0 固定・1 増分・4 限定増分）はケースで1種類が必要です")
        for key in ("ELoadNum", "ELoadRow", "DLoadNum", "DLoadRow"):
            f.count(key, 0, 0)
        f.count("ConbNum", self.nk, self.nk)
        coefficient = Num(0, 1, integer=True)
        for index in range(1, self.nk + 1):
            values = f.fields(f"SNAPConb{index}", *self.rho_alpha, 0, 0, *(coefficient,) * self.nc,
                              *(" ",) * (COMBINATION_SLOTS - self.nc), 0, 0)
            f.fields(f"ConbAlpf{index}", *values[4:4 + self.nc])
        return member, joint

    def _tail(self) -> None:
        f = self.file
        for key in ("PickNum", "Conb2Num", "Pick2Num", "TishouNum", "SesfNum", "SesfKihonNum", "SesfPiM", "SesfPiS"):
            f.count(key, 0, 0)
        f.fields("Tisou", "")
        for index in range(1, self.ne + 1):
            f.fields(f"SesfPiIJ{index}", 0, 0, 0, 0, "", "")
        f.fields("SesfPiBuzai", *(0,) * 5)
        for key in ("GanmaA", "FontColor", "FontSize", "FontName", "LineColor", "LineWidth", "Sunpo", "JointCircle",
                    "Grid", "ErrInfo"):
            self._constant(key, CONSTANT_RECORDS[key])


def validate_ndu(data: bytes, profile: Profile) -> NduSummary:
    """Reject anything outside the dialect WebPier writes for *profile*; return the counts."""
    return _Validator(data, profile).run()
