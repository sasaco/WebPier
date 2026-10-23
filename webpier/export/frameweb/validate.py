"""The native rules of the FrameWeb input that WebPier writes (2D frame, static load cases).

The rules are those of the format of the Example2 FrameWeb file and of FrameWeb's behaviour (README FrameWeb): a spring value 1 means a fixed support and 0 a free one, so springs are positive and not 1;
member rows without a load are rejected (unsupported mark), and a node row of zeros too but for the one row ty = 0
of a load model's zero case, which FEMPython keeps (decision 70); member load intensities are projected to 0.01; a
load case without rows is skipped, so a Combine with only such cases is dropped and its Pickup fails, and a
Define that has both empty and loaded candidates changes its envelope; the Combine grid shows 50 Define
columns; the symbol "LL" makes a case a moving load.

A distributed member load (mark 2) runs from L1 after the member start to L2 before the member end, P1 at its
start and P2 at its end, linear between (FrameWebforCS calculation/CalculationRequest.cs, FrameWeb
fem/legacy_beam.py); FrameWeb projects L1 / L2 to 0.001 m and drops a load whose length is not positive. A row
over a range of members repeats L1 / L2 on each and carries P1 on, so only a uniform load over whole members is
written that way.

On top of the format, the subset WebPier writes: tables numbered 1, 2, ... in order, one section type, member
loads in global axes, and every node connected to the support.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, NoReturn

from ...core.errors import InputError

TOP_LEVEL = ("node", "fix_node", "member", "element", "load", "define", "combine", "pickup", "dimension")
SECTION_KEYS = ("E", "G", "Xp", "A", "J", "Iy", "Iz", "n")
SUPPORT_KEYS = ("row", "n", "tx", "ty", "tz", "rx", "ry", "rz")
LOAD_KEYS = ("fix_node", "element", "symbol", "LL_pitch", "rate", "name")
MEMBER_SPRING_KEYS = ("m", "tx", "ty", "tz", "tr", "length", "row")  # a pile row's distributed springs (decision 88)
NODE_LOAD_KEYS = ("n", "tx", "ty", "tz", "rx", "ry", "rz", "row")
MEMBER_LOAD_KEYS = ("m1", "m2", "direction", "mark", "L1", "L2", "P1", "P2", "row")
MAX_DEFINES = 50  # FrameWebforCS shows C1-C50 in the Combine grid (tests/InputCombineColumnsTests.cs)


def _fail(path: str, message: str) -> NoReturn:
    raise InputError(f"FrameWeb入力: {path or '全体'}: {message}")


def _record(value: object, path: str, required: Iterable[str], optional: Iterable[str] = ()) -> dict[str, Any]:
    required, optional = set(required), set(optional)
    if not isinstance(value, dict) or not required <= value.keys() <= required | optional:
        _fail(path, f"項目 {sorted(required)}（任意 {sorted(optional)}）の表が必要です")
    return value


def _numbered(value: object, path: str) -> list[tuple[int, Any]]:
    if not isinstance(value, dict) or not value or list(value) != [str(n) for n in range(1, len(value) + 1)]:
        _fail(path, "番号 1, 2, … を順に並べた表が必要です")
    return [(int(key), item) for key, item in value.items()]


def _rows(value: object, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        _fail(path, "空でない行の配列が必要です")
    return value


def _number(value: object, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (
            positive and value <= 0):
        _fail(path, f"{'正の' if positive else ''}有限の数値が必要です（{value!r}）")
    return float(value)


def _reference(value: object, known: Mapping[int, Any] | set[int], path: str) -> int:
    if type(value) is not int or value not in known:
        _fail(path, f"存在する番号（整数）が必要です（{value!r}）")
    return value


def _named(value: object, known: Mapping[int, Any] | set[int], path: str) -> int:
    if not isinstance(value, str) or not value.isdecimal() or int(value) not in known or str(int(value)) != value:
        _fail(path, f"存在する番号（文字列）が必要です（{value!r}）")
    return int(value)


def _null(row: Mapping[str, Any], keys: Iterable[str], path: str) -> None:
    for key in keys:
        if row[key] is not None:
            _fail(f"{path}.{key}", "2次元のモデルでは null です")


def _text(value: object, path: str) -> None:
    if not isinstance(value, str):
        _fail(path, "文字列が必要です")


def _row_number(row: Mapping[str, Any], number: int, path: str) -> None:
    if type(row["row"]) is not int or row["row"] != number:
        _fail(f"{path}.row", f"行番号 {number} が必要です")


def _open(value: object, path: str, required: Iterable[str]) -> dict[str, Any]:
    """A table with at least the *required* keys; the other keys are columns."""
    if not isinstance(value, dict) or not set(required) <= value.keys():
        _fail(path, f"項目 {sorted(required)} と列の表が必要です")
    return value


def _columns(value: object, path: str, fixed: tuple[str, ...]) -> list[Any]:
    """The values of C1, C2, ... in order, next to the *fixed* keys."""
    row = _open(value, path, fixed)
    columns = [key for key in row if key not in fixed]
    if not columns or columns != [f"C{i}" for i in range(1, len(columns) + 1)]:
        _fail(path, "列 C1, C2, … が順に必要です")
    return [row[key] for key in columns]


def _connected(nodes: Iterable[int], edges: Mapping[int, set[int]], start: set[int], path: str) -> None:
    reached, pending = set(), list(start)
    while pending:
        node = pending.pop()
        if node not in reached:
            reached.add(node)
            pending.extend(edges[node])
    if reached != set(nodes):
        _fail(path, f"支点につながらない節点があります: {sorted(set(nodes) - reached)}")


def _model(root: Mapping[str, Any]) -> tuple[dict[int, tuple[float, float]], dict[int, float], set[int], set[int]]:
    piles = "fix_member" in root  # springs at the tips and along the members: a pile foundation (decision 88)
    nodes = {}
    for number, node in _numbered(root["node"], "node"):
        path = f"node.{number}"
        _record(node, path, ("x", "y", "z"))
        _null(node, ("z",), path)
        nodes[number] = (_number(node["x"], f"{path}.x"), _number(node["y"], f"{path}.y"))

    types = _numbered(root["element"], "element")
    if len(types) != 1:
        _fail("element", "断面のTYPEは1つです")
    sections = set()
    for number, section in _numbered(types[0][1], "element.1"):
        path = f"element.1.{number}"
        _record(section, path, SECTION_KEYS)
        _null(section, ("G", "J", "Iy"), path)
        for key in ("E", "Xp", "A", "Iz"):
            _number(section[key], f"{path}.{key}", positive=True)
        _text(section["n"], f"{path}.n")
        sections.add(number)

    edges: dict[int, set[int]] = {number: set() for number in nodes}
    members = {}  # number -> length
    for number, member in _numbered(root["member"], "member"):
        path = f"member.{number}"
        _record(member, path, ("ni", "nj", "e", "cg"))
        _null(member, ("cg",), path)
        ni, nj = (_reference(member[key], nodes, f"{path}.{key}") for key in ("ni", "nj"))
        _reference(member["e"], sections, f"{path}.e")
        length = math.dist(nodes[ni], nodes[nj])
        if not length > 0:
            _fail(path, "長さ0の部材です")
        edges[ni].add(nj)
        edges[nj].add(ni)
        members[number] = length

    supports = set()
    for number, rows in _numbered(root["fix_node"], "fix_node"):
        path = f"fix_node.{number}"
        start = set()
        for index, row in enumerate(_rows(rows, path), 1):
            where = f"{path}[{index}]"
            _record(row, where, SUPPORT_KEYS)
            _row_number(row, index, where)
            start.add(_named(row["n"], nodes, f"{where}.n"))
            _null(row, ("tz", "rx", "ry"), where)
            for key in ("tx", "ty", "rz"):
                if piles and key != "ty" and row[key] is None:  # SOIL-JR leaves the spring out of a long pile's tip
                    continue
                if _number(row[key], f"{where}.{key}", positive=True) == 1:
                    _fail(f"{where}.{key}", "ばね値 1 は FrameWeb では固定支点を意味します")
        _connected(nodes, edges, start, path)
        supports.add(number)
    if piles:
        _member_springs(root["fix_member"], members, supports)
    return nodes, members, supports, {types[0][0]}


def _member_springs(value: object, members: Mapping[int, float], sets: set[int]) -> None:
    """The distributed springs: a set for each spring set of ``fix_node``, in rows of intervals from the I end."""
    found = _numbered(value, "fix_member")
    if {number for number, _ in found} != sets:
        _fail("fix_member", "fix_node と同じ番号のばねの組が必要です")
    for number, rows in found:
        path = f"fix_member.{number}"
        used: dict[int, float] = {}
        for index, row in enumerate(_rows(rows, path), 1):
            where = f"{path}[{index}]"
            _record(row, where, MEMBER_SPRING_KEYS)
            _row_number(row, index, where)
            member = _named(row["m"], members, f"{where}.m")
            _null(row, ("tz", "tr"), where)
            values = [_number(row[key], f"{where}.{key}") for key in ("tx", "ty") if row[key] is not None]
            if not values or any(v < 0 for v in values) or all(v == 0 for v in values):
                _fail(where, "ばね値は 0 以上で、成分のない行は書きません（0 の成分は null）")
            used[member] = used.get(member, 0.0) + _number(row["length"], f"{where}.length", positive=True)
            if used[member] > members[member] + 1e-6:
                _fail(where, f"区間の長さの合計（{used[member]!r}）が部材長（{members[member]!r}）を超えます")


def _node_rows(rows: object, nodes: Mapping[int, Any], path: str) -> None:
    for index, row in enumerate(_rows(rows, path), 1):
        where = f"{path}[{index}]"
        _record(row, where, NODE_LOAD_KEYS)
        _row_number(row, index, where)
        _named(row["n"], nodes, f"{where}.n")
        _null(row, ("tz", "rx", "ry"), where)
        values = [_number(row[key], f"{where}.{key}") for key in ("tx", "ty", "rz") if row[key] is not None]
        zero = len(rows) == 1 and row["ty"] == 0 and row["tx"] is None and row["rz"] is None  # type: ignore[arg-type]
        if not zero and (not values or 0 in values):  # the one row ty = 0 is a load model's zero case (decision 70)
            _fail(where, "0 の成分は null、成分のない行は書きません")


def _units(value: float, digits: int) -> int:
    """*value* in units of 10^−digits as FrameWeb projects it (half up)."""
    return math.floor(value * 10 ** digits + 0.5)


def _projected(value: float, digits: int) -> bool:
    """Whether FrameWeb's projection to *digits* decimals keeps *value*."""
    return _units(value, digits) / 10 ** digits == value


def _member_rows(rows: object, members: Mapping[int, float], path: str) -> None:
    for index, row in enumerate(_rows(rows, path), 1):
        where = f"{path}[{index}]"
        _record(row, where, MEMBER_LOAD_KEYS)
        _row_number(row, index, where)
        first, last = (_named(row[key], members, f"{where}.{key}") for key in ("m1", "m2"))
        if type(row["mark"]) is not int or row["mark"] != 2 or row["direction"] not in ("gx", "gy"):
            _fail(where, "全体座標 gx / gy の分布荷重（mark 2）が必要です")
        start, margin = (_number(row[key], f"{where}.{key}") for key in ("L1", "L2"))
        for key, distance in (("L1", start), ("L2", margin)):
            if distance < 0 or not _projected(distance, 3):
                _fail(f"{where}.{key}", f"0 以上で小数3桁までの距離が必要です（FrameWeb は 0.001 m に丸めます: {distance!r}）")
        p1, p2 = (_number(row[key], f"{where}.{key}") for key in ("P1", "P2"))
        for key, intensity in (("P1", p1), ("P2", p2)):
            if not _projected(intensity, 2):
                _fail(f"{where}.{key}", f"小数2桁までの強度が必要です（FrameWeb は 0.01 に丸めて解析します: {intensity!r}）")
        if not (p1 or p2):
            _fail(where, "強度が 0 の行は書きません")
        if first != last:
            if start or margin or p1 != p2:
                _fail(where, "部材の範囲には全長の等分布荷重だけを書きます（部分・変化する荷重は部材ごとの行）")
        elif _units(members[first], 3) - _units(start, 3) - _units(margin, 3) <= 0:
            _fail(where, f"載荷長が 0 以下です（部材長 {members[first]!r}、L1 {start!r}、L2 {margin!r}）")


def validate_frameweb(document: object) -> None:
    """Raise InputError naming the first rule the document breaks."""
    root = _record(document, "", TOP_LEVEL, ("fix_member",))
    if type(root["dimension"]) is not int or root["dimension"] != 2:
        _fail("dimension", "2次元（2）が必要です")
    nodes, members, supports, types = _model(root)

    loaded = {}
    for number, case in _numbered(root["load"], "load"):
        path = f"load.{number}"
        _record(case, path, LOAD_KEYS, ("fix_member", "load_node", "load_member"))
        _reference(case["fix_node"], supports, f"{path}.fix_node")
        if ("fix_member" in root) != ("fix_member" in case):
            _fail(f"{path}.fix_member", "杭基礎の骨組は、荷重ケースごとに分布ばねの組を指します（直接基礎は書きません）")
        if "fix_member" in case:
            _reference(case["fix_member"], supports, f"{path}.fix_member")
        _reference(case["element"], types, f"{path}.element")
        for key in ("symbol", "name"):
            _text(case[key], f"{path}.{key}")
        if case["symbol"] == "LL":
            _fail(f"{path}.symbol", "LL は移動荷重のケースになります")
        for key in ("LL_pitch", "rate"):
            _number(case[key], f"{path}.{key}", positive=True)
        if "load_node" in case:
            _node_rows(case["load_node"], nodes, f"{path}.load_node")
        if "load_member" in case:
            _member_rows(case["load_member"], members, f"{path}.load_member")
        loaded[number] = "load_node" in case or "load_member" in case

    defines = {}
    for number, row in _numbered(root["define"], "define"):
        path = f"define.{number}"
        references = _columns(row, path, ("row",))
        _row_number(row, number, path)
        for reference in references:
            if type(reference) is not int or abs(reference) not in loaded or references.count(reference) > 1:
                _fail(path, f"荷重ケースの番号（負は逆向き）を重複なく指します（{reference!r}）")
        candidates = {loaded[abs(reference)] for reference in references}
        if len(candidates) > 1:
            _fail(path, "候補の一部だけが荷重のないケースです（FrameWeb はそれを除いて包絡します）")
        defines[number] = candidates.pop()
    if len(defines) > MAX_DEFINES:
        _fail("define", f"Define は {MAX_DEFINES} までです（Combine の表の列数）")

    combines = set()
    for number, row in _numbered(root["combine"], "combine"):
        path = f"combine.{number}"
        _open(row, path, ("row", "name"))
        _row_number(row, number, path)
        _text(row["name"], f"{path}.name")
        terms = [(key, factor) for key, factor in row.items() if key not in ("row", "name")]
        for key, factor in terms:
            if not key.startswith("C") or not key[1:].isdecimal() or int(key[1:]) not in defines:
                _fail(f"{path}.{key}", "Define の番号を指す列 C<n> が必要です")
            _number(factor, f"{path}.{key}", positive=True)
        if not any(defines[int(key[1:])] for key, _ in terms):
            _fail(path, "荷重のある項がありません（FrameWeb は空の Combine を除くので Pickup が成り立ちません）")
        combines.add(number)

    for number, row in _numbered(root["pickup"], "pickup"):
        path = f"pickup.{number}"
        references = _columns(row, path, ("row", "name"))
        _row_number(row, number, path)
        _text(row["name"], f"{path}.name")
        for reference in references:
            if type(reference) is not int or reference not in combines or references.count(reference) > 1:
                _fail(path, f"Combine の番号を重複なく指します（{reference!r}）")
