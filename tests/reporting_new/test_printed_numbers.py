"""The single number formatter prints a Printed at exactly its digits (ADR-0003)."""

import pytest

from webpier.core.printed import Precision, Printed


def test_prints_exactly_the_carried_digits():
    from webpier.reporting.numbers import printed

    assert printed(Printed(7.937, 3, "m")) == "7.937"
    assert printed(Printed(7.0, 3, "m")) == "7.000"
    assert printed(Printed(257.25, 6, "m4")) == "257.250000"
    assert printed(Printed(202988.0, 0, "kN/m3")) == "202988"
    assert printed(Printed(150.0, 2, "")) == "150.00"
    assert printed(Printed(-1.5, 2, "kN")) == "-1.50"
    assert printed(Printed(-0.0, 2, "kN")) == "0.00"


def test_thousand_separators_are_presentation_only():
    from webpier.reporting.numbers import printed

    assert printed(Printed(4262769.0, 0, "kN/m"), thousands=True) == "4,262,769"
    assert printed(Printed(165760.0, 0, "kN/m2"), thousands=True) == "165,760"
    assert printed(Printed(1234.5, 1, "kN"), thousands=True) == "1,234.5"
    assert printed(Printed(-1234567.25, 2, "kN"), thousands=True) == "-1,234,567.25"
    assert printed(Printed(999.0, 0, ""), thousands=True) == "999"


def test_decimal_text_is_the_written_value_not_the_binary_expansion():
    """10000000.1 to 10 places reads 10000000.1000000000, not ...0999999996."""
    from webpier.reporting.numbers import printed

    assert printed(Precision(10, "").exact(10000000.1)) == "10000000.1000000000"
    assert printed(Precision(3, "").exact(1e16)) == "10000000000000000.000"


def test_rejects_anything_but_a_printed_value():
    from webpier.reporting.numbers import printed

    for value in (7.937, "7.937", None, 7):
        with pytest.raises(TypeError):
            printed(value)


def test_constant_prints_a_table_constant_as_written():
    from webpier.reporting.numbers import constant

    assert constant(6.9) == "6.9"
    assert constant(0.5) == "0.5"
    assert constant(1.0) == "1.0"
    assert constant(-0.75) == "-0.75"
    for value in (True, "6.9", float("nan"), float("inf"), 1):
        with pytest.raises((TypeError, ValueError)):
            constant(value)


def test_unit_presentation_is_fixed_per_unit_text():
    from gridlayoutpdf import Script
    from webpier.reporting.numbers import unit

    assert unit("m") == "m"
    assert unit("kN/m") == "kN/m"
    assert unit("kN m/rad") == "kN・m/rad"
    for text, base, exponent in (("m2", "m", "2"), ("m4", "m", "4"), ("kN/m2", "kN/m", "2"),
                                 ("kN/m3", "kN/m", "3")):
        node = unit(text)
        assert isinstance(node, Script)
        assert (node.base.text, node.superscript.text, node.subscript) == (base, exponent, None)
    with pytest.raises(ValueError, match="単位"):
        unit("furlong")
