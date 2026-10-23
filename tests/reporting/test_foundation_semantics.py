"""0500 semantics: every printed number is the FoundationResult value at its digits.

The expected records are written here from the result and the input, apart
from the fixed wording, which is the reviewed old report (semantic/0500.json).
That fixture was mapped from the old PDF; its values are also Example2 04
pp.4-1..4-3 (kv 202988, Ks 4,262,769, Kr 52,218,663, ...), and 0500 did not
change, so it stays valid as the wording/order reference. Deliberate
differences from it are listed in DIFFERENCES and checked explicitly.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from foundation_report_cases import CASES, case, text
from webpier.calc.embedment import surface_layer_thickness
from webpier.core.printed import Printed

REFERENCE = Path(__file__).parents[1] / "fixtures" / "reporting" / "semantic" / "0500.json"

# Old record → why the new text differs. New records are listed with None.
DIFFERENCES = {
    # 決定80: 地盤の表の「一軸圧縮強度 qu」の列は「粘着力 c」になった（地盤の層の qu を c に替えた）
    "0500/soil.header": "層番層厚(m)土質区分Ｎ値単位体積重量湿潤水中内部摩擦角φd(°)粘着力c(kN/m2)変形係数Ed(kN/m2)（旧: 一軸圧縮強度qu）",
    "0500/soil.surface": None,   # 表層厚を検算できるように値だけの代入式で印刷する（派生値。入力票の記号は書かない）
    # 見本どおり Av を「ここに、」の定義に加え、Bv と Av を値の列がそろう代入式で印刷する
    "0500/kv.definition.Av": None,
    "0500/kv.width": "Bv = √Av = √63.000 = 7.937 m（旧: Bv = √Av (=√63.000 = 7.937 m)）",
    "0500/kv.area": "Av = 7.000 × 9.000 = 63.000 m²（旧: 定義の行の括弧内）",
    "0500/kv.soil_type": None,   # 決定18: 土質区分と係数・指数を印刷する
    # 見本 p1 どおり全角括弧で囲む（旧: ・長期 ( ρgk=0.5)）
    "0500/kv.long_term.label": "・長期（ρgk = 0.5）（旧: 半角括弧）",
    "0500/kv.short_term.label": "・短期（ρgk = 1.0）（旧: 半角括弧）",
    # 決定40: JRSNAP の FootInfo に渡す Df・γ2 を検算できるように印刷する（対象の地盤のときだけ）
    "0500/embedment.heading": None,
    "0500/embedment.formula": None,
    "0500/embedment.gamma2": None,
    "0500/embedment.definition.Df": None,
    "0500/embedment.definition.hw2": None,
    "0500/embedment.definition.wet": None,
    "0500/embedment.definition.sub": None,
}


def squeeze(value: str) -> str:
    return re.sub(r"\s+", "", value)


def reference_records() -> dict[str, str]:
    records = {}
    for record in json.loads(REFERENCE.read_text(encoding="utf-8"))["records"]:
        value = record["source_text"]
        for atom in sorted(record.get("vector_atoms", []), key=lambda item: item["offset"], reverse=True):
            value = value[:atom["offset"]] + atom["text"] + value[atom["offset"]:]
        records[record["id"]] = squeeze(value)
    return records


LABELS = {"砂質土": "（砂質土）", "砂質土と粘性土の互層": "（砂質土，粘性土の互層）", "粘性土": "（粘性土）"}


def expected_records(result, pier, embedment) -> dict[str, str]:
    """Wording from the reviewed fixture, numbers from the result (never recomputed)."""
    reference = reference_records()
    out: dict[str, str] = {}

    def fixed(key: str) -> None:
        out["0500/" + key] = reference["0500/" + key]

    for key in ("title", "soil.heading", "soil.introduction", "soil.caption"):
        fixed(key)
    out["0500/soil.header"] = "層番層厚(m)土質区分Ｎ値単位体積重量湿潤水中内部摩擦角φd(°)粘着力c(kN/m2)変形係数Ed(kN/m2)"
    surface = surface_layer_thickness(pier, result.surface_thickness)  # decision 64: the rest of Df when blank
    for index, layer in enumerate(pier.soil.layers):
        thickness = surface if index == 0 else layer.thickness
        out[f"0500/soil.row.{index}"] = "".join((
            layer.name, text(thickness), layer.soil_type, text(layer.n_value), text(layer.unit_weight_wet),
            text(layer.unit_weight_submerged), text(layer.friction_angle), text(layer.cohesion),
            text(layer.deformation_modulus, thousands=True)))
    sub = pier.substructure
    label = "表層の層厚" if surface == result.surface_thickness else "Df"
    out["0500/soil.surface"] = (f"{label}={text(sub.h[6])}+{text(sub.h[5])}"
                                f"+min({text(sub.df1)},{text(sub.df2)})={text(result.surface_thickness)}m")
    if embedment is not None:
        e, single = embedment, embedment.single
        assert single is not None  # the variants have one layer within Df
        out["0500/embedment.heading"] = "有効根入れ深さと表層の平均有効単位重量"
        out["0500/embedment.formula"] = "γ2=((Df−hw2)×γwet+hw2×γsub)/Df"
        out["0500/embedment.gamma2"] = (f"γ2=(({text(e.depth)}−{text(e.water)})×{text(single.unit_weight_wet)}"
                                        f"+{text(e.water)}×{text(single.unit_weight_submerged)})/{text(e.depth)}"
                                        f"={text(e.unit_weight)}kN/m3")
        out["0500/embedment.definition.Df"] = f"ここに、Df：有効根入れ深さ（表層厚）(={text(e.depth)}m)"
        out["0500/embedment.definition.hw2"] = f"hw2：基礎底面からの平水位(={text(e.water)}m)"
        out["0500/embedment.definition.wet"] = f"γwet：表層の湿潤単位体積重量(={text(single.unit_weight_wet)}kN/m3)"
        out["0500/embedment.definition.sub"] = (f"γsub：表層の水中単位体積重量"
                                                f"(={text(single.unit_weight_submerged)}kN/m3)")
    fixed("bearing.heading")
    for key, label in (("normal", "地震時を除く"), ("seismic", "地震時")):
        out["0500/bearing." + key] = f"Nγ={text(result.n_gamma)},Nq={text(result.n_q)}{label}"
    for key in ("spring.heading", "vertical.heading", "kv.heading", "kv.sand", "kv.alternating", "kv.clay",
                "kv.definition.kv", "kv.definition.rho"):
        fixed(key)
    ed, width, area = text(result.deformation_modulus), text(result.width), text(result.area)
    out["0500/kv.definition.Ed"] = f"Ed：地盤の変形係数(={ed}kN/m2)"
    fixed("kv.definition.Bv")
    out["0500/kv.definition.Av"] = "Av：フーチング底面積(m2)"
    out["0500/kv.width"] = f"Bv=√Av=√{area}={width}m"
    out["0500/kv.area"] = f"Av={text(result.b)}×{text(result.l)}={area}m2"
    coefficient = text(result.coefficient)
    out["0500/kv.soil_type"] = (f"支持層の土質区分：{result.soil_type}（kv={coefficient}ρgkEdBv"
                                f"{result.exponent_text}を用いる）")
    terms = (("long_term", "長期", result.long_term), ("short_term", "短期", result.short_term))
    for term, label, springs in terms:
        out[f"0500/kv.{term}.label"] = f"・{label}（ρgk={text(springs.rho)}）"
        out[f"0500/kv.{term}"] = (f"kv={coefficient}×{text(springs.rho)}×{ed}×{width}{result.exponent_text}"
                                  f"={text(springs.kv)}kN/m3")
    for key in ("Kv.heading", "Kv.formula", "Kv.definition.Kv", "Kv.definition.kv", "Kv.definition.Av"):
        fixed(key)
    for term, label, springs in terms:
        out[f"0500/Kv.{term}.label"] = f"・{label}"
        out[f"0500/Kv.{term}"] = f"Kv={text(springs.kv)}×{area}={text(springs.Kv, thousands=True)}kN/m"
    for key in ("shear.heading", "ks.heading", "ks.formula", "ks.definition.ks", "ks.definition.lambda"):
        fixed(key)
    for term, label, springs in terms:
        out[f"0500/ks.{term}.label"] = f"・{label}"
        out[f"0500/ks.{term}"] = f"ks=1/3×{text(springs.kv)}={text(springs.ks)}kN/m3"
    for key in ("Ks.heading", "Ks.formula", "Ks.definition.Ks", "Ks.definition.ks", "Ks.definition.Av"):
        fixed(key)
    for term, label, springs in terms:
        out[f"0500/Ks.{term}.label"] = f"・{label}"
        out[f"0500/Ks.{term}"] = f"Ks={text(springs.ks)}×{area}={text(springs.Ks, thousands=True)}kN/m"
    for key in ("rotation.heading", "Kr.formula", "Kr.definition.Kr", "Kr.definition.kv", "Kr.definition.Iv"):
        fixed(key)
    for direction, first, cubed in (("longitudinal", result.l, result.b), ("transverse", result.b, result.l)):
        inertia = getattr(result, "inertia_" + direction)
        fixed(f"Kr.{direction}.heading")
        out[f"0500/Kr.{direction}.inertia"] = f"Iv={text(first)}×{text(cubed)}3/12={text(inertia)}m4"
        for term, label, springs in terms:
            out[f"0500/Kr.{direction}.{term}.label"] = f"・{label}"
            out[f"0500/Kr.{direction}.{term}"] = (f"Kr={text(springs.kv)}×{text(inertia)}="
                                                  f"{text(getattr(springs, 'Kr_' + direction), thousands=True)}kN・m/rad")
    return out


def actual_records(result, pier, embedment) -> dict[str, str]:
    from webpier.reporting.stages.foundation import semantic_records

    records = semantic_records(result, pier, embedment)
    ids = [record["id"] for record in records]
    assert len(ids) == len(set(ids))
    return {record["id"]: squeeze(record["text"]) for record in records}


def test_expectation_reproduces_the_reviewed_old_report_except_declared_differences():
    reference = reference_records()
    expected = expected_records(*case("current"))
    new = [key for key in expected if key not in reference]
    assert sorted(new) == sorted(key for key, why in DIFFERENCES.items() if why is None)
    assert [key for key in expected if key in reference] == list(reference)
    changed = {key for key in reference if expected[key] != reference[key]}
    assert changed == {key for key, why in DIFFERENCES.items() if why is not None}


@pytest.mark.parametrize("name", list(CASES))
def test_every_record_prints_the_result_values_at_their_digits(name: str):
    expected = expected_records(*case(name))
    actual = actual_records(*case(name))
    assert list(actual) == list(expected)
    for key in expected:
        assert actual[key] == expected[key], key


NUMERIC = ("soil.row.1", "soil.surface", "bearing.normal", "kv.definition.Ed", "kv.width", "kv.area", "kv.soil_type",
           "kv.long_term", "kv.short_term", "Kv.long_term", "Kv.short_term", "ks.long_term", "ks.short_term",
           "Ks.long_term", "Ks.short_term", "Kr.longitudinal.inertia", "Kr.longitudinal.long_term",
           "Kr.longitudinal.short_term", "Kr.transverse.inertia", "Kr.transverse.long_term", "Kr.transverse.short_term")


def test_variants_really_change_the_printed_values():
    current = expected_records(*case("current"))
    for name in ("clay", "alternating"):
        other = expected_records(*case(name))
        same = [key for key in NUMERIC if key != "soil.row.1" and current["0500/" + key] == other["0500/" + key]]
        assert same == [], name
    assert expected_records(*case("clay"))["0500/kv.soil_type"].startswith("支持層の土質区分：粘性土（kv=3.8")
    assert expected_records(*case("alternating"))["0500/soil.row.1"].startswith("第2層3.250粘性土12")


def test_gamma2_is_printed_where_the_procedure_applies():
    assert expected_records(*case("current"))["0500/embedment.gamma2"] == "γ2=((4.700−2.700)×18.0+2.700×8.0)/4.700=12.3kN/m3"
    assert expected_records(*case("level"))["0500/embedment.gamma2"] == "γ2=((4.000−1.250)×19.0+1.250×9.5)/4.000=16.0kN/m3"
    for name in ("clay", "alternating", "deep"):
        assert not any(key.startswith("0500/embedment.") for key in actual_records(*case(name))), name


def test_the_report_reads_the_result_not_the_input():
    """A result whose values differ from what the input would give is printed as is."""
    result, pier, embedment = case("current")
    sentinel = replace(result, width=Printed(1.234, 3, "m"), n_gamma=Printed(12.34, 2, ""),
                       surface_thickness=Printed(9.876, 3, "m"), soil_type="粘性土", coefficient=Printed(3.8, 1, ""),
                       exponent_text="-1",
                       long_term=replace(result.long_term, kv=Printed(111.0, 0, "kN/m3"),
                                         Kr_transverse=Printed(7654321.0, 0, "kN m/rad")))
    gamma = replace(embedment, normal=replace(embedment.normal, unit_weight=Printed(99.9, 1, "kN/m3")),
                    water=Printed(1.111, 3, "m"))
    actual = actual_records(sentinel, pier, gamma)
    assert actual["0500/kv.width"].endswith("=1.234m")
    assert actual["0500/bearing.normal"].startswith("Nγ=12.34,")
    assert actual["0500/soil.row.0"].startswith("表層9.876")
    assert actual["0500/kv.long_term"] == "kv=3.8×0.5×165760×1.234-1=111kN/m3"
    assert actual["0500/Kr.transverse.long_term"] == "Kr=111×425.250000=7,654,321kN・m/rad"
    assert actual["0500/embedment.gamma2"] == "γ2=((4.700−1.111)×18.0+1.111×8.0)/4.700=99.9kN/m3"
    assert actual == expected_records(sentinel, pier, gamma)


def test_manuscript_uses_structured_root_script_and_term_columns_without_stacked_fractions():
    """The reference prints fractions inline ("1/3", "7.000³ / 12", "(…) / 4.700"): no stacked Fraction."""
    from gridlayoutpdf import Fraction, Root, Script, TermStop
    from webpier.reporting.stages.foundation import content

    def classes(value: Any) -> set[type]:
        found = {type(value)}
        if is_dataclass(value):
            for field in fields(value):
                found |= classes(getattr(value, field.name))
        elif isinstance(value, (tuple, list)):
            for item in value:
                found |= classes(item)
        return found

    for name in CASES:
        found = classes(content(*case(name)))
        assert {Root, Script, TermStop} <= found and Fraction not in found, name


# A name of the input sheet (B1…, H6, W7, df1, df2) is not defined in the report and never printed.
INPUT_SHEET_NAME = re.compile(r"(?<![A-Za-z])[BHW][1-9](?!\d)|df[12]")


@pytest.mark.parametrize("name", list(CASES))
def test_no_record_prints_a_name_of_the_input_sheet(name: str):
    from webpier.reporting.stages.foundation import semantic_records

    for record in semantic_records(*case(name)):
        assert not INPUT_SHEET_NAME.search(record["text"]), record
    assert INPUT_SHEET_NAME.search("H6+H5+min(df1, df2)") and not INPUT_SHEET_NAME.search("Bv=√Av, Kr, Nγ")


def test_unit_text_follows_the_result_units():
    from webpier.reporting.stages.foundation import semantic_records

    result, pier, embedment = case("current")
    odd = replace(result, long_term=replace(result.long_term, Kv=Printed(1.0, 0, "furlong")))
    with pytest.raises(ValueError, match="単位"):
        semantic_records(odd, pier, embedment)


def test_semantic_text_rejects_an_unknown_node():
    from webpier.reporting.stages.foundation import plain, ratio

    with pytest.raises(TypeError, match="Unsupported"):
        plain(object())
    assert plain(ratio("2")) == "2" and plain(ratio("1/3")) == "1/3"
