"""The contract a load model is written against (decision 70, ADR-0010)."""

from webpier import loadmodel
from webpier.calc import load_nature
from webpier.calc.longitudinal import ExtractionGroup as LongitudinalGroup, SpringTerm as LongitudinalSpring
from webpier.calc.longitudinal import combinations


def test_the_version_of_the_contract():
    assert loadmodel.CONTRACT_VERSION == 1


def test_the_spring_terms_and_extraction_groups_are_the_contract_s():
    # Moved to the contract; the calc modules export the same classes, so the train path is unchanged.
    assert load_nature.SpringTerm is loadmodel.SpringTerm is LongitudinalSpring
    assert combinations.ExtractionGroup is loadmodel.ExtractionGroup is LongitudinalGroup
    assert [group.value for group in loadmodel.ExtractionGroup] == list(range(1, 9))


def test_the_application_cases():
    assert (loadmodel.D1, loadmodel.D2, loadmodel.WP_HIGH, loadmodel.WP_NORMAL, loadmodel.WP_LOW, loadmodel.EQ2) == (
        "D1", "D2", "WP_HIGH", "WP_NORMAL", "WP_LOW", "EQ2")
    assert loadmodel.pier_wind(2) == "PIER_WIND_2"


def test_the_cantilever_rows_are_capacita_s_force_table():
    """All but 最小鉄筋量, which takes the combinations of 耐久性（永久荷重） (decision 73)."""
    from webpier.calc.cantilever.combinations import FORCE_ROWS
    from webpier.calc.generic.cantilever import POOLED_AS
    assert POOLED_AS == {8: 1}
    assert [row.value for row in loadmodel.CantileverRow] == [row.id for row in FORCE_ROWS if row.id not in POOLED_AS]


def test_every_name_of_the_package_is_exported():
    assert set(loadmodel.__all__) == {name for name in dir(loadmodel) if not name.startswith("_")} - {
        "contract"}
