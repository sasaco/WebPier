"""What the application checks of a load model's result before it calculates with it (decision 70): every violation
is an input error that names the place in the load model."""

from dataclasses import replace
from decimal import Decimal
import re

import pytest

from loadmodel_support import B1, C1, CONTEXT, D, one, result, with_case
from webpier.core.errors import InputError
from webpier.loadmodel import (
    D1, EQ2, WP_HIGH, BasicCase, BearingAction, BearingRef, CantileverCombination, CantileverTerm, Candidate,
    Combination, ExtractionGroup, Increment, LoadModelInputError, Paragraph, Section, Seismic, SeismicCombination,
    SeismicDirection, Side, SpringTerm, Table, Term, pier_wind, validate,
)


def fails(value, message):
    with pytest.raises(InputError, match=re.escape(message)):
        validate(value, CONTEXT)


def test_a_valid_result_passes_as_it_is():
    value = result()
    assert validate(value, CONTEXT) is value


def test_the_load_model_input_error_names_its_path():
    error = LoadModelInputError("input.addin.json:車荷重[2]", "空欄です")
    assert isinstance(error, InputError)
    assert (error.path, error.message) == ("input.addin.json:車荷重[2]", "空欄です")
    assert str(error) == "input.addin.json:車荷重[2]: 空欄です"


@pytest.mark.parametrize("field,value,message", [
    ("id", "BR", "アドイン:BR: 基本ケースの id が重複しています"),
    ("id", D1, "アドイン:D1: アプリの基本ケースと同じ id は使えません"),
    ("id", pier_wind(3), "アドイン:PIER_WIND_3: アプリの基本ケースと同じ id は使えません"),
    ("id", "", "アドイン:cases[1]: id は空でない文字列が必要です"),
    ("id", 7, "アドイン:cases[1]: id は空でない文字列が必要です"),
    ("name", "", "アドイン:L: 名前は空でない文字列が必要です"),
    ("spring", "short", "アドイン:L: spring は SpringTerm が必要です"),
    ("seismic", Increment.FIXED, "アドイン:L: seismic は Seismic か None が必要です"),
    ("seismic", Seismic("fixed", SeismicDirection.DOWNWARD), "アドイン:L: seismic.increment は Increment が必要です"),
    ("seismic", Seismic(Increment.FIXED, "down"), "アドイン:L: seismic.direction は SeismicDirection が必要です"),
    ("actions", [], "アドイン:L: actions は BearingAction のタプルが必要です"),
    ("actions", ("x",), "アドイン:L: actions は BearingAction のタプルが必要です"),
])
def test_a_basic_case_needs_a_unique_id_a_name_and_its_kinds(field, value, message):
    fails(with_case(result(), 0, **{field: value}), message)


def test_the_cases_must_be_a_tuple_of_basic_cases():
    fails(result(cases=["x"]), "アドイン:cases: BasicCase のタプルが必要です")


@pytest.mark.parametrize("bearing,message", [
    (BearingRef(Side.ORIGIN, 3), "アドイン:L.起点側3: 空き支承枠です（入力の上部工反力に支承がありません）"),
    (BearingRef(Side.END, 11), "アドイン:L.終点側11: 空き支承枠です（入力の上部工反力に支承がありません）"),
    (BearingRef("origin", 1), "アドイン:L.actions[1]: bearing は BearingRef が必要です"),
])
def test_a_bearing_must_be_one_of_the_input(bearing, message):
    fails(with_case(result(), 0, actions=(BearingAction(bearing, vertical=D("1.00")),)), message)


def test_a_bearing_appears_once_in_a_case():
    fails(with_case(result(), 0, actions=(BearingAction(B1, vertical=D("1.00")), BearingAction(B1))),
          "アドイン:L.起点側1: 同じ支承の支承作用が2つあります")


@pytest.mark.parametrize("field,value,message", [
    ("vertical", D("100.001"), "アドイン:L.起点側1.鉛直力: 小数2桁までの Decimal が必要です（100.001）"),
    ("longitudinal", 1.5, "アドイン:L.起点側1.線路方向の水平力: 小数2桁までの Decimal が必要です（1.5）"),
    ("longitudinal_height", D("1.2345"), "アドイン:L.起点側1.線路方向の作用高さ: 小数3桁までの Decimal が必要です（1.2345）"),
    ("transverse", D("NaN"), "アドイン:L.起点側1.直角方向の水平力: 小数2桁までの Decimal が必要です（NaN）"),
    ("transverse_height", D("Infinity"), "アドイン:L.起点側1.直角方向の作用高さ: 小数3桁までの Decimal が必要です（Infinity）"),
])
def test_the_values_must_be_at_their_printed_digits(field, value, message):
    fails(with_case(result(), 0, actions=(BearingAction(B1, **{field: value}),)), message)


def test_trailing_zeros_beyond_the_digits_are_the_same_value():
    # 100.000 is 100.00: the digits are those of the value, not of how the Decimal was written.
    value = with_case(result(), 0, actions=(BearingAction(B1, vertical=D("100.000")),))
    assert validate(value, CONTEXT) is value


@pytest.mark.parametrize("stage,terms,message", [
    ("longitudinal", (one("X"),), "アドイン:0610.安全性: 基本ケース X がありません"),
    ("longitudinal", (one(pier_wind(1)),), "アドイン:0610.安全性: 基本ケース PIER_WIND_1 がありません"),
    ("longitudinal", (one(EQ2),), "アドイン:0610.安全性: 基本ケース EQ2 がありません"),
    ("transverse", (one(pier_wind(2)),), "アドイン:0620.安全性: 基本ケース PIER_WIND_2 がありません"),
    ("longitudinal", (one("L", -1),), "アドイン:0610.安全性.L: 符号 −1 は鉛直力が0のケースだけに使えます"),
    ("longitudinal", (one(D1, -1),), "アドイン:0610.安全性.D1: 符号 −1 は鉛直力が0のケースだけに使えます"),
    ("longitudinal", (one(WP_HIGH, -1),), "アドイン:0610.安全性.WP_HIGH: 符号 −1 は鉛直力が0のケースだけに使えます"),
    ("longitudinal", (one("BR", 2),), "アドイン:0610.安全性.BR: 符号は 1 か −1 が必要です"),
    ("longitudinal", (Term(D("1.0"), ()),), "アドイン:0610.安全性: 項には基本ケースが1つ以上必要です"),
    ("longitudinal", (Term(D("1.0"), ("L",)),), "アドイン:0610.安全性: 項の候補は Candidate が必要です"),
    ("longitudinal", (Term(D("1.0"), (Candidate("L"), Candidate("L"))),),
     "アドイン:0610.安全性.L: 同じ項に同じ基本ケースと符号が2つあります"),
    ("longitudinal", (one("BR"), Term(D("1.0"), (Candidate("L"), Candidate("BR", -1)))),
     "アドイン:0610.安全性.BR: 同じ基本ケースが2つの項にあります"),
    ("longitudinal", (Term(D("1.2345"), (Candidate("L"),)),),
     "アドイン:0610.安全性: 係数は小数3桁までの Decimal が必要です（1.2345）"),
    ("longitudinal", ("x",), "アドイン:0610.安全性: 項は Term が必要です"),
    ("longitudinal", (), "アドイン:0610.安全性: 項が1つ以上必要です"),
])
def test_a_frame_combination_refers_to_the_cases_of_its_stage(stage, terms, message):
    base = result()
    combinations = list(getattr(base, stage))
    combinations[0] = replace(combinations[0], name="安全性", terms=terms)
    fails(replace(base, **{stage: tuple(combinations)}), message)


def test_a_reversed_case_without_vertical_forces_passes():
    base = result()
    value = replace(base, longitudinal=(replace(base.longitudinal[0], terms=(one("BR", -1),)),))
    assert validate(value, CONTEXT) is value


@pytest.mark.parametrize("change,message", [
    (dict(name=""), "アドイン:0610[1]: 名前は空でない文字列が必要です"),
    (dict(name="永久"), "アドイン:0610.永久: 組合せの名前が重複しています"),
    (dict(groups={ExtractionGroup.FAILURE}), "アドイン:0610.安全性: groups は ExtractionGroup の frozenset が必要です"),
    (dict(groups=frozenset({1})), "アドイン:0610.安全性: groups は ExtractionGroup の frozenset が必要です"),
])
def test_a_frame_combination_has_a_unique_name_and_its_groups(change, message):
    base = result()
    fails(replace(base, longitudinal=(replace(base.longitudinal[0], **change), base.longitudinal[1])), message)


def test_the_combinations_must_be_a_tuple():
    fails(result(longitudinal=["x"]), "アドイン:0610: Combination のタプルが必要です")
    fails(result(seismic_transverse=("x",)), "アドイン:0720: SeismicCombination のタプルが必要です")
    fails(result(cantilever=None), "アドイン:0900: CantileverCombination のタプルが必要です")


@pytest.mark.parametrize("cases,message", [
    ((D1, "L"), "アドイン:0710.L-EQ.L: 地震時の基本ケースではありません（seismic がありません）"),
    ((D1, WP_HIGH), "アドイン:0710.L-EQ: 基本ケース WP_HIGH がありません"),
    ((D1, D1), "アドイン:0710.L-EQ.D1: 同じ基本ケースが2つあります"),
    ((), "アドイン:0710.L-EQ: 基本ケースが1つ以上必要です"),
    ([D1], "アドイン:0710.L-EQ: cases は id のタプルが必要です"),
])
def test_a_seismic_combination_loads_seismic_cases(cases, message):
    fails(result(seismic_longitudinal=(SeismicCombination("L-EQ", cases),)), message)


@pytest.mark.parametrize("reverse", [1, None, "True"])
def test_a_seismic_combination_is_reversed_by_a_bool(reverse):
    # Decision 76: reverse (逆向) is True or False, not a number or a text.
    fails(result(seismic_transverse=(SeismicCombination("T-EQ", (D1, EQ2), reverse=reverse),)),
          "アドイン:0720.T-EQ: reverse は True か False が必要です")


def test_an_ndu_has_at_most_15_basic_cases():
    base = result()
    extra = tuple(BasicCase(f"S{n}", f"地震時{n}", SpringTerm.SHORT, (),
                            Seismic(Increment.FIXED, SeismicDirection.DOWNWARD)) for n in range(1, 12))
    within = replace(base, cases=base.cases + extra,  # D1, D2, WP_NORMAL, EQ2 and 11 of the load model: 15
                     seismic_longitudinal=(SeismicCombination("a", (D1, *[c.id for c in extra[:6]])),
                                           SeismicCombination("b", ("D2", "WP_NORMAL", EQ2, *[c.id for c in extra[6:]]))))
    assert validate(within, CONTEXT) is within
    over = replace(within, seismic_longitudinal=within.seismic_longitudinal + (SeismicCombination("c", ("LE",)),))
    fails(over, "アドイン:0710: 地震時の基本ケースが16あります（NDU は15まで）")


@pytest.mark.parametrize("terms,message", [
    ((CantileverTerm("X", D("1.0")),), "アドイン:0900.破壊: 基本ケース X がありません"),
    ((CantileverTerm(WP_HIGH, D("1.0")),), "アドイン:0900.破壊: 基本ケース WP_HIGH がありません"),
    ((CantileverTerm(EQ2, D("1.0")),), "アドイン:0900.破壊: 基本ケース EQ2 がありません"),
    ((CantileverTerm(D1, 1.1),), "アドイン:0900.破壊.D1: 係数は小数3桁までの Decimal か MaxResponse が必要です（1.1）"),
    ((CantileverTerm(D1, D("1.0")), CantileverTerm(D1, D("1.1"))), "アドイン:0900.破壊.D1: 同じ基本ケースが2つあります"),
    (("x",), "アドイン:0900.破壊: 項は CantileverTerm が必要です"),
    ((), "アドイン:0900.破壊: 項が1つ以上必要です"),
])
def test_a_cantilever_combination_refers_to_the_cases(terms, message):
    base = result()
    fails(replace(base, cantilever=(replace(base.cantilever[0], terms=terms), base.cantilever[1])), message)


def test_a_cantilever_combination_needs_its_rows():
    base = result()
    fails(replace(base, cantilever=(replace(base.cantilever[0], rows={1}), base.cantilever[1])),
          "アドイン:0900.破壊: rows は CantileverRow の frozenset が必要です")
    fails(replace(base, cantilever=(base.cantilever[0], replace(base.cantilever[1], name="破壊"))),
          "アドイン:0900.破壊: 組合せの名前が重複しています")


def test_a_max_response_needs_a_direction():
    base = result()
    term = CantileverTerm("EQ1", type(base.cantilever[1].terms[1].factor)("transverse"))
    fails(replace(base, cantilever=(base.cantilever[0], CantileverCombination("地震時", (term,), frozenset()))),
          "アドイン:0900.地震時.EQ1: MaxResponse.direction は FrameDirection が必要です")


@pytest.mark.parametrize("pressures,message", [
    ((D("3.05"),), "アドイン:躯体の風[1]: 小数1桁までの Decimal が必要です（3.05）"),
    ((D("-1.0"),), "アドイン:躯体の風[1]: 風圧は正の値が必要です"),
    ([D("3.0")], "アドイン:躯体の風: Decimal のタプルが必要です"),
])
def test_the_wind_pressures_on_the_pier(pressures, message):
    fails(result(pier_wind_pressures=pressures), message)


@pytest.mark.parametrize("sections,message", [
    ({"0611": ()}, "アドイン:sections.0611: 根拠の節を差し込む段階は 0610・0620・0710・0720・0900 です"),
    ({"0610": ("x",)}, "アドイン:sections.0610: Section のタプルが必要です"),
    ({"0610": []}, "アドイン:sections.0610: Section のタプルが必要です"),
    (["0610"], "アドイン:sections: 段階ごとの辞書が必要です"),
])
def test_the_sections_go_to_the_stages_that_print_them(sections, message):
    fails(result(sections=sections), message)


def test_the_provenance_must_be_json():
    fails(result(provenance={"when": object()}), "アドイン:provenance: JSON にできる辞書が必要です")
    fails(result(provenance=["x"]), "アドイン:provenance: JSON にできる辞書が必要です")
    fails(result(provenance={1: "x"}), "アドイン:provenance: JSON にできる辞書が必要です")


def test_a_result_must_be_a_load_model_result():
    fails("x", "アドイン: 荷重モデルの結果は LoadModelResult が必要です（str）")


def test_seismic_cases_of_the_load_model_carry_their_seismic_kind():
    seismic = result().cases[2].seismic
    assert seismic == Seismic(Increment.INCREMENTAL, SeismicDirection.EARTHQUAKE)
    assert result().cases[3].actions == (BearingAction(C1, vertical=Decimal("30.00")),)


def test_a_value_beyond_any_digits_is_not_printed():
    fails(with_case(result(), 0, actions=(BearingAction(B1, vertical=D("1E+500")),)),
          "アドイン:L.起点側1.鉛直力: 小数2桁までの Decimal が必要です（1E+500）")


def test_a_case_in_several_seismic_combinations_is_one_case_of_the_ndu():
    base = result()
    value = replace(base, seismic_longitudinal=tuple(SeismicCombination(name, (D1, "LE")) for name in "ab"))
    assert validate(value, CONTEXT) is value


@pytest.mark.parametrize("section", [
    Section("", ()),
    Section("根拠", [Paragraph("x")]),
    Section("根拠", (Paragraph(1),)),
    Section("根拠", (Table(("a", "b"), (("1",),)),)),
    Section("根拠", (Table(("a",), ((1,),)),)),
    Section("根拠", (Table(["a"], ()),)),
    Section("根拠", ("x",)),
])
def test_a_section_has_a_title_and_paragraphs_or_tables_of_text(section):
    fails(result(sections={"0720": (section,)}),
          "アドイン:sections.0720: 節は題名と、段落（Paragraph）か列の数がそろった文字列の表（Table）のタプルが必要です")


def test_the_provenance_may_nest_json_values():
    value = result(provenance={"files": [{"name": "a", "size": 1.5, "ok": True, "note": None}], "pair": ("a", 1)})
    assert validate(value, CONTEXT) is value
    fails(result(provenance={"size": float("nan")}), "アドイン:provenance: JSON にできる辞書が必要です")


@pytest.mark.parametrize("name", ["上部工の慣性力" * 3, "慣性力 "])
def test_a_seismic_case_name_is_an_ndu_title(name):
    # 21 full-width characters are 42 bytes; U+2028 has no Shift-JIS code.
    fails(with_case(result(), 2, name=name),
          "アドイン:EQ1: 地震時のケースの名前は NDU の題名なので、Shift-JIS で40バイトまでです")
    assert validate(with_case(result(), 0, name=name), CONTEXT)  # a frame case is not written to the NDU
