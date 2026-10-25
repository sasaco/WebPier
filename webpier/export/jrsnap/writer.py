"""NDU bytes: CP932, CRLF after every record (including the last), no BOM, then the strict validator.

A number is written as the decimal it is printed with, without exponent or trailing zeros (8299.53, 4500, −0.3,
0); nothing is rounded again and there is no Single precision. Text must be CP932, at most 40 bytes, without
control characters, ``,`` or ``=``; an unencodable character is an error, never replaced.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.printed import Printed
from . import pile_records
from .model import NduModel
from .pile_model import PileNduModel
from .pile_validate import validate_pile_ndu
from .records import Field, Record, Token, records
from .validate import TEXT_BYTES, check_text, validate_ndu

ENCODING = "cp932"
NEWLINE = "\r\n"


def number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def field(value: Field) -> str:
    if isinstance(value, Token):
        return str(value)
    if isinstance(value, str):
        return check_text(value, TEXT_BYTES)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    return number(Decimal(repr(value.value)) if isinstance(value, Printed) else value)


def line(record: Record) -> str:
    key, values = record
    return key if values is None else key + "=" + ",".join(field(value) for value in values)


def write_ndu(model: NduModel) -> bytes:
    """The NDU of *model*, validated against its profile before it is returned."""
    # check_text has rejected unencodable text; the tokens and numbers are ASCII.
    data = "".join(line(record) + NEWLINE for record in records(model)).encode(ENCODING, errors="strict")
    validate_ndu(data, model.profile)
    return data


def write_pile_ndu(model: PileNduModel) -> bytes:
    """The NDU of a pile foundation (decision 93), checked as ``validate_pile_ndu`` does before it is returned."""
    data = "".join(line(record) + NEWLINE for record in pile_records.records(model)).encode(ENCODING, errors="strict")
    validate_pile_ndu(data, model)
    return data
