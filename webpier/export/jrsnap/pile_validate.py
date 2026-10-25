"""Check of the NDU of a pile foundation: the model that is written and the bytes it gives (decision 93).

The record order and the values are those of the sample (``test_jrsnap_pile_records``); this checks what makes a model
one JRSNAP can read: joints, members, elements and supports that refer to each other, the elements of a member counted by its
divisions, the nonlinear models and the sections they name, and the framing of the file (CP932, CRLF, unique keys, text).
"""

from __future__ import annotations

from decimal import Decimal

from .pile_model import PILE, PileNduModel
from .validate import _error, _File

SUPPORT_KINDS = (1, 2, 3)  # the horizontal, vertical and rotational spring of a node; a pile row has the vertical one
SUPPORT_VALUES = 10
MEMBER_TOLERANCE = Decimal("0.0005")


def check_model(model: PileNduModel) -> None:
    joints = {joint.number for joint in model.joints}
    if sorted(joints) != list(range(1, len(model.joints) + 1)):
        raise _error("節点の番号は 1 から順に重複なく付ける必要があります")
    if len({(joint.x, joint.y) for joint in model.joints}) != len(model.joints):
        raise _error("同じ位置の節点があります")
    if model.origin not in joints or model.control not in joints:
        raise _error("原点または制御点の節点がありません")
    if [m.number for m in model.members] != list(range(1, len(model.members) + 1)):
        raise _error("部材の番号は 1 から順に付ける必要があります")
    if [e.number for e in model.elements] != list(range(1, len(model.elements) + 1)):
        raise _error("要素の番号は 1 から順に付ける必要があります")
    for m in model.members:
        if m.i not in joints or m.j not in joints:
            raise _error(f"部材 {m.number} の節点がありません")
        total = sum((Decimal(repr(length.value)) * count for length, count in m.divisions), Decimal(0))
        if abs(total - Decimal(repr(m.length.value))) > MEMBER_TOLERANCE:
            raise _error(f"部材 {m.number} の分割の長さの合計（{total}）が部材の長さと違います")
    if sum(count for m in model.members for _, count in m.divisions) != len(model.elements):
        raise _error("部材の分割の要素数の合計が要素の数と違います")
    for e in model.elements:
        if e.i not in joints or e.j not in joints:
            raise _error(f"要素 {e.number} の節点がありません")
    marked = [e.nonlinear for e in model.elements if e.nonlinear]
    if marked != list(range(1, len(model.nonlinear) + 1)):
        raise _error("非線形のある要素の番号は 1 から順に、NonLinInfo の行と同じ数が必要です")
    for row in model.nonlinear:
        if not 1 <= row.section <= len(model.sections):
            raise _error(f"NonLinInfo の断面番号 {row.section} の断面がありません")
    start = 1
    starts = {}
    for m in model.members:
        starts[m.number] = (start, start + sum(count for _, count in m.divisions) - 1)
        start = starts[m.number][1] + 1
    for pile in model.piles:
        member = next((m for m in model.members if m.number == pile.member), None)
        if member is None or not member.pile:
            raise _error(f"KGInfo の部材 {pile.member} は杭の部材ではありません")
        first, last = starts[pile.member]
        if (pile.first, pile.last) != (first + 1, last):
            raise _error(f"KGInfo の要素（{pile.first}〜{pile.last}）が部材 {pile.member} の杭の要素（{first + 1}〜{last}）と違います")
    for e in model.elements:
        in_pile = any(p.first <= e.number <= p.last for p in model.piles)
        if (e.kind == PILE) != in_pile or (e.ground is not None) != in_pile:
            raise _error(f"要素 {e.number} の種類と地盤ばねが杭の要素の範囲と合いません")
    nodes = [support.node for support in model.supports]
    if nodes != sorted(set(nodes)) or not set(nodes) <= joints:
        raise _error("支点の節点は、節点の中から昇順に重複なく並べる必要があります")
    for support in model.supports:
        if support.kind not in SUPPORT_KINDS or len(support.values) != SUPPORT_VALUES:
            raise _error(f"節点 {support.node} の支点の種類または値の数が違います")
    if not model.cases or any(len(c.coefficients) != len(model.cases) for c in model.combinations):
        raise _error("荷重の組合せの係数の数が基本ケースの数と違います")


def validate_pile_ndu(data: bytes, model: PileNduModel) -> None:
    check_model(model)
    _File(data)  # framing: CP932, CRLF, no control characters, unique keys
