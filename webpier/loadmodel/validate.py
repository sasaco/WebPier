"""What the application checks of a load model's result before it calculates with it (decision 70).

A load model is code of another repository, so its result is read like an input: every violation is an input error
whose path starts with ``アドイン:`` and names the case, the bearing or the combination. The checks are those the
calculation and the files for the other programs need:

- the ids of the basic cases are unique and not the application's, and every combination refers to a case it can use
  (the frames: D1, D2 and the buoyancy, 0620 also the wind on the pier body; the seismic analyses: D1, D2, the
  buoyancy at the normal water level and EQ2; the cantilever beam: D1 with the self weight of the beam, and D2),
  each case in one term of a combination at most;
- a bearing is one of the input, not an empty slot;
- every value is at its printed digits (forces 2 decimals, heights 3, factors up to 3, wind pressures 1);
- the sign −1 reverses a whole case in FrameWeb (Define −n), so it is only for a case without vertical forces;
- a seismic combination loads seismic cases only, and the cases of one direction are at most 15 (the NDU);
- the sections go to the stages that print them, and the provenance can be written as JSON.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Context as DecimalContext, Decimal, InvalidOperation
from typing import Any

from ..core.errors import InputError
from .contract import (
    D1, D2, EQ2, PIER_WIND, SECTION_STAGES, WP_HIGH, WP_LOW, WP_NORMAL, BasicCase, BearingAction, BearingRef,
    CantileverCombination, CantileverRow, CantileverTerm, Candidate, Combination, Context, ExtractionGroup,
    FrameDirection, Increment, LoadModelResult, MaxResponse, Paragraph, Section, Seismic, SeismicCombination,
    SeismicDirection, Side, SpringTerm, Table, Term, pier_wind,
)

FORCE_DIGITS = 2
HEIGHT_DIGITS = 3
FACTOR_DIGITS = 3
PRESSURE_DIGITS = 1
NDU_CASES = 15  # the basic cases an NDU can hold (export.jrsnap.validate)

FRAME_CASES = frozenset({D1, D2, WP_HIGH, WP_NORMAL, WP_LOW})
SEISMIC_CASES = frozenset({D1, D2, WP_NORMAL, EQ2})
CANTILEVER_CASES = frozenset({D1, D2})  # D1 carries the self weight of the beam
_VERTICAL = frozenset({D1, D2, WP_HIGH, WP_NORMAL, WP_LOW})  # the application cases with vertical forces
_RESERVED = FRAME_CASES | SEISMIC_CASES
_FIELDS = (("vertical", "鉛直力", FORCE_DIGITS), ("longitudinal", "線路方向の水平力", FORCE_DIGITS),
           ("longitudinal_height", "線路方向の作用高さ", HEIGHT_DIGITS), ("transverse", "直角方向の水平力", FORCE_DIGITS),
           ("transverse_height", "直角方向の作用高さ", HEIGHT_DIGITS))
_EXACT = DecimalContext(prec=400)


def _error(where: str, message: str) -> InputError:
    return InputError(f"アドイン:{where}: {message}" if where else f"アドイン: {message}")


def _printed(value: object, digits: int) -> bool:
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    try:
        return value.quantize(Decimal(1).scaleb(-digits), context=_EXACT) == value
    except InvalidOperation:
        return False


def _digits(where: str, value: object, digits: int) -> None:
    if not _printed(value, digits):
        raise _error(where, f"小数{digits}桁までの Decimal が必要です（{value}）")


def _tuple_of(value: object, kind: type | tuple[type, ...]) -> bool:
    return isinstance(value, tuple) and all(isinstance(item, kind) for item in value)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def bearing_label(ref: BearingRef) -> str:
    """起点側1, 終点側2 …: a bearing as the input and the reports name it."""
    return f"{'起点側' if ref.side is Side.ORIGIN else '終点側'}{ref.slot}"


def _case(index: int, case: BasicCase, ids: set[str], bearings: frozenset[BearingRef]) -> None:
    if not _text(case.id):
        raise _error(f"cases[{index}]", "id は空でない文字列が必要です")
    where = case.id
    if case.id in _RESERVED or case.id.startswith(PIER_WIND):
        raise _error(where, "アプリの基本ケースと同じ id は使えません")
    if case.id in ids:
        raise _error(where, "基本ケースの id が重複しています")
    ids.add(case.id)
    if not _text(case.name):
        raise _error(where, "名前は空でない文字列が必要です")
    if not isinstance(case.spring, SpringTerm):
        raise _error(where, "spring は SpringTerm が必要です")
    if case.seismic is not None:
        if not isinstance(case.seismic, Seismic):
            raise _error(where, "seismic は Seismic か None が必要です")
        if not isinstance(case.seismic.increment, Increment):
            raise _error(where, "seismic.increment は Increment が必要です")
        if not isinstance(case.seismic.direction, SeismicDirection):
            raise _error(where, "seismic.direction は SeismicDirection が必要です")
    if not _tuple_of(case.actions, BearingAction):
        raise _error(where, "actions は BearingAction のタプルが必要です")
    seen: set[BearingRef] = set()
    for number, action in enumerate(case.actions, 1):
        ref = action.bearing
        if not isinstance(ref, BearingRef) or not isinstance(ref.side, Side):
            raise _error(f"{where}.actions[{number}]", "bearing は BearingRef が必要です")
        at = f"{where}.{bearing_label(ref)}"
        if ref not in bearings:
            raise _error(at, "空き支承枠です（入力の上部工反力に支承がありません）")
        if ref in seen:
            raise _error(at, "同じ支承の支承作用が2つあります")
        seen.add(ref)
        for field, name, digits in _FIELDS:
            _digits(f"{at}.{name}", getattr(action, field), digits)


def _vertical(case: BasicCase) -> bool:
    return any(action.vertical for action in case.actions)


def _names(stage: str, combinations: Iterable[Any]) -> None:
    names: set[str] = set()
    for index, combination in enumerate(combinations, 1):
        if not _text(combination.name):
            raise _error(f"{stage}[{index}]", "名前は空でない文字列が必要です")
        if combination.name in names:
            raise _error(f"{stage}.{combination.name}", "組合せの名前が重複しています")
        names.add(combination.name)


def _frame(stage: str, combinations: object, available: frozenset[str], cases: Mapping[str, BasicCase]) -> None:
    if not _tuple_of(combinations, Combination):
        raise _error(stage, "Combination のタプルが必要です")
    assert isinstance(combinations, tuple)
    _names(stage, combinations)
    for combination in combinations:
        where = f"{stage}.{combination.name}"
        if not _tuple_of(combination.terms, Term) or not combination.terms:
            raise _error(where, "項は Term が必要です" if combination.terms else "項が1つ以上必要です")
        terms: set[str] = set()  # the cases of the terms before
        for term in combination.terms:
            if not _printed(term.factor, FACTOR_DIGITS):
                raise _error(where, f"係数は小数{FACTOR_DIGITS}桁までの Decimal が必要です（{term.factor}）")
            if not isinstance(term.candidates, tuple) or not term.candidates:
                raise _error(where, "項には基本ケースが1つ以上必要です")
            seen: set[tuple[str, int]] = set()
            for candidate in term.candidates:
                if not isinstance(candidate, Candidate):
                    raise _error(where, "項の候補は Candidate が必要です")
                if candidate.case not in available and candidate.case not in cases:
                    raise _error(where, f"基本ケース {candidate.case} がありません")
                at = f"{where}.{candidate.case}"
                if candidate.sign not in (1, -1) or isinstance(candidate.sign, bool):
                    raise _error(at, "符号は 1 か −1 が必要です")
                if candidate.sign == -1 and (candidate.case in _VERTICAL or (
                        candidate.case in cases and _vertical(cases[candidate.case]))):
                    raise _error(at, "符号 −1 は鉛直力が0のケースだけに使えます")
                if (candidate.case, candidate.sign) in seen:
                    raise _error(at, "同じ項に同じ基本ケースと符号が2つあります")
                if candidate.case in terms:
                    raise _error(at, "同じ基本ケースが2つの項にあります")
                seen.add((candidate.case, candidate.sign))
            terms |= {case for case, _ in seen}
        if not isinstance(combination.groups, frozenset) or not all(
                isinstance(group, ExtractionGroup) for group in combination.groups):
            raise _error(where, "groups は ExtractionGroup の frozenset が必要です")


def _seismic(stage: str, combinations: object, cases: Mapping[str, BasicCase]) -> None:
    if not _tuple_of(combinations, SeismicCombination):
        raise _error(stage, "SeismicCombination のタプルが必要です")
    assert isinstance(combinations, tuple)
    _names(stage, combinations)
    used: list[str] = []
    for combination in combinations:
        where = f"{stage}.{combination.name}"
        if not _tuple_of(combination.cases, str):
            raise _error(where, "cases は id のタプルが必要です")
        if not combination.cases:
            raise _error(where, "基本ケースが1つ以上必要です")
        seen: set[str] = set()
        for case in combination.cases:
            if case not in SEISMIC_CASES and case not in cases:
                raise _error(where, f"基本ケース {case} がありません")
            if case in cases and cases[case].seismic is None:
                raise _error(f"{where}.{case}", "地震時の基本ケースではありません（seismic がありません）")
            if case in seen:
                raise _error(f"{where}.{case}", "同じ基本ケースが2つあります")
            seen.add(case)
            if case not in used:
                used.append(case)
    if len(used) > NDU_CASES:
        raise _error(stage, f"地震時の基本ケースが{len(used)}あります（NDU は{NDU_CASES}まで）")


def _cantilever(combinations: object, cases: Mapping[str, BasicCase]) -> None:
    stage = "0900"
    if not _tuple_of(combinations, CantileverCombination):
        raise _error(stage, "CantileverCombination のタプルが必要です")
    assert isinstance(combinations, tuple)
    _names(stage, combinations)
    for combination in combinations:
        where = f"{stage}.{combination.name}"
        if not _tuple_of(combination.terms, CantileverTerm) or not combination.terms:
            raise _error(where, "項は CantileverTerm が必要です" if combination.terms else "項が1つ以上必要です")
        seen: set[str] = set()
        for term in combination.terms:
            if term.case not in CANTILEVER_CASES and term.case not in cases:
                raise _error(where, f"基本ケース {term.case} がありません")
            at = f"{where}.{term.case}"
            if isinstance(term.factor, MaxResponse):
                if not isinstance(term.factor.direction, FrameDirection):
                    raise _error(at, "MaxResponse.direction は FrameDirection が必要です")
            elif not _printed(term.factor, FACTOR_DIGITS):
                raise _error(at, f"係数は小数{FACTOR_DIGITS}桁までの Decimal か MaxResponse が必要です（{term.factor}）")
            if term.case in seen:
                raise _error(at, "同じ基本ケースが2つあります")
            seen.add(term.case)
        if not isinstance(combination.rows, frozenset) or not all(
                isinstance(row, CantileverRow) for row in combination.rows):
            raise _error(where, "rows は CantileverRow の frozenset が必要です")


def _pressures(pressures: object) -> None:
    if not _tuple_of(pressures, Decimal):
        raise _error("躯体の風", "Decimal のタプルが必要です")
    assert isinstance(pressures, tuple)
    for number, pressure in enumerate(pressures, 1):
        _digits(f"躯体の風[{number}]", pressure, PRESSURE_DIGITS)
        if pressure <= 0:
            raise _error(f"躯体の風[{number}]", "風圧は正の値が必要です")


def _block(block: object) -> bool:
    if isinstance(block, Paragraph):
        return isinstance(block.text, str)
    return (isinstance(block, Table) and _tuple_of(block.columns, str)
            and _tuple_of(block.rows, tuple)
            and all(_tuple_of(row, str) and len(row) == len(block.columns) for row in block.rows))


def _sections(sections: object) -> None:
    if not isinstance(sections, Mapping):
        raise _error("sections", "段階ごとの辞書が必要です")
    for stage, items in sections.items():
        where = f"sections.{stage}"
        if stage not in SECTION_STAGES:
            raise _error(where, f"根拠の節を差し込む段階は {'・'.join(SECTION_STAGES)} です")
        if not _tuple_of(items, Section):
            raise _error(where, "Section のタプルが必要です")
        for section in items:
            if not _text(section.title) or not isinstance(section.blocks, tuple) or not all(
                    _block(block) for block in section.blocks):
                raise _error(where, "節は題名と、段落（Paragraph）か列の数がそろった文字列の表（Table）のタプルが必要です")


def _json(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, (list, tuple)):
        return all(_json(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _json(item) for key, item in value.items())
    return False


def validate(result: LoadModelResult, context: Context) -> LoadModelResult:
    """*result* as it is, if the application can calculate with it; otherwise an input error naming the place."""
    if not isinstance(result, LoadModelResult):
        raise _error("", f"荷重モデルの結果は LoadModelResult が必要です（{type(result).__name__}）")
    if not _tuple_of(result.cases, BasicCase):
        raise _error("cases", "BasicCase のタプルが必要です")
    bearings = frozenset(slot.ref for slot in context.bearings)
    ids: set[str] = set()
    for index, case in enumerate(result.cases, 1):
        _case(index, case, ids, bearings)
    cases = {case.id: case for case in result.cases}
    _pressures(result.pier_wind_pressures)
    winds = frozenset(pier_wind(number) for number in range(1, len(result.pier_wind_pressures) + 1))
    _frame("0610", result.longitudinal, FRAME_CASES, cases)
    _frame("0620", result.transverse, FRAME_CASES | winds, cases)
    _seismic("0710", result.seismic_longitudinal, cases)
    _seismic("0720", result.seismic_transverse, cases)
    _cantilever(result.cantilever, cases)
    _sections(result.sections)
    if not isinstance(result.provenance, Mapping) or not _json(result.provenance):
        raise _error("provenance", "JSON にできる辞書が必要です")
    return result


__all__ = ["bearing_label", "validate"]
