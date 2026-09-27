from decimal import Decimal

import pytest

from app.imports.values import (
    clip,
    parse_length,
    parse_money,
    parse_partial_date,
    parse_weight,
    records,
    texts,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$1,234.56", "1234.56"),
        ("$12.5", "12.50"),
        ("1234", "1234.00"),
        ("USD 12.50", "12.50"),
        ("$ 1,000", "1000.00"),
    ],
)
def test_reads_dollars(text, expected):
    assert parse_money(text) == Decimal(expected)


@pytest.mark.parametrize(
    "text", ["€12", "£5", "EGP 500", "1.234,56", "$1,23", "about $50", "", "$99999999999"]
)
def test_leaves_what_is_not_plainly_dollars(text):
    assert parse_money(text) is None


@pytest.mark.parametrize(
    ("text", "centimetres", "unit"),
    [
        ("12 in", "30.48", "in"),
        ("3-1/2 in", "8.89", "in"),
        ("3 1/2 inches", "8.89", "inches"),
        ("1/2 in", "1.27", "in"),
        ('12"', "30.48", '"'),
        ("12.5 cm", "12.50", "cm"),
        ("25mm", "2.50", "mm"),
        ("2 ft", "60.96", "ft"),
    ],
)
def test_reads_lengths_into_centimetres(text, centimetres, unit):
    assert parse_length(text) == (Decimal(centimetres), unit)


@pytest.mark.parametrize("text", ["12", "12 x 4 in", "about 5 in", "3/0 in", "12 hands", ""])
def test_leaves_lengths_it_cannot_read(text):
    assert parse_length(text) is None


@pytest.mark.parametrize(
    ("text", "kilograms"),
    [("2 lb", "0.907"), ("8 oz", "0.227"), ("1.5 kg", "1.500"), ("250 g", "0.250")],
)
def test_reads_weights_into_kilograms(text, kilograms):
    assert parse_weight(text)[0] == Decimal(kilograms)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1998", "1998"),
        ("1998-6", "1998-06"),
        ("1998-06-15", "1998-06-15"),
        ("March 5, 2021", "2021-03-05"),
        ("Mar 5 2021", "2021-03-05"),
        ("5 March 2021", "2021-03-05"),
        ("Sept. 2021", "2021-09"),
        ("March 2021", "2021-03"),
        ("3/5/2021", "2021-03-05"),
        ("3/2021", "2021-03"),
    ],
)
def test_reads_dates_at_the_precision_given(text, expected):
    assert parse_partial_date(text) == expected


@pytest.mark.parametrize(
    "text",
    ["circa 1998", "1990s", "Spring 2020", "2021-02-30", "13/5/2021", "0000", "Smarch 2021", ""],
)
def test_does_not_invent_dates(text):
    assert parse_partial_date(text) is None


def test_clip_cuts_at_a_word_and_says_so():
    text = "A long description of a small silver box with a hinged lid"

    shortened, cut = clip(text, 30)

    assert cut
    assert len(shortened) <= 30
    assert shortened.endswith("…")
    assert not shortened.removesuffix("…").endswith(" ")
    assert clip("short", 30) == ("short", False)


def test_texts_and_records_accept_every_shape_catalogit_uses():
    assert texts(["a", " ", 3, None, ["b"]]) == ["a", "3", "b"]
    assert texts({"nested": "object"}) == []
    assert records({"a": 1}) == [{"a": 1}]
    assert records([{"a": 1}, "loose text"]) == [{"a": 1}]
    assert records("text") == []
