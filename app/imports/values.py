"""Reading catalog text as Trove values.

Each reader returns None for text it cannot read with confidence. Callers keep that
text in a note, so an import never guesses at a value and never loses one.
"""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENTS = Decimal("0.01")
GRAMS = Decimal("0.001")

# Column limits: Numeric(12, 2) for money, Numeric(10, 2) and Numeric(10, 3) for
# measurements.
_MAX_MONEY = Decimal("9999999999.99")
_MAX_MEASURE = Decimal("99999999.99")

_MONEY = re.compile(r"^(?:US\$|\$|USD\s*)?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(?:USD)?$", re.I)


def parse_money(text: str) -> Decimal | None:
    """Dollars from "$1,234.56", "1234" or "USD 12.50". Other currencies are not read."""
    match = _MONEY.match(text.strip())
    if not match:
        return None
    value = _decimal(match[1].replace(",", "") + (match[2] or ""), CENTS)
    return value if value is not None and value <= _MAX_MONEY else None


# Centimetres per unit.
_LENGTH_UNITS = {
    "in": Decimal("2.54"),
    "inch": Decimal("2.54"),
    "inches": Decimal("2.54"),
    '"': Decimal("2.54"),
    "″": Decimal("2.54"),
    "ft": Decimal("30.48"),
    "foot": Decimal("30.48"),
    "feet": Decimal("30.48"),
    "'": Decimal("30.48"),
    "mm": Decimal("0.1"),
    "cm": Decimal("1"),
    "m": Decimal("100"),
}
# Kilograms per unit.
_WEIGHT_UNITS = {
    "oz": Decimal("0.028349523125"),
    "lb": Decimal("0.45359237"),
    "lbs": Decimal("0.45359237"),
    "g": Decimal("0.001"),
    "kg": Decimal("1"),
}
IMPERIAL_UNITS = {"in", "inch", "inches", '"', "″", "ft", "foot", "feet", "'", "oz", "lb", "lbs"}

# "12 in", "3-1/2 in", "3 1/2 in", "1/2 in", "12.5cm", '12"'
_MEASURE = re.compile(
    r"""^(?:(?P<whole>\d+(?:\.\d+)?)(?:\s*-\s*|\s+)?)?
    (?:(?P<num>\d+)\s*/\s*(?P<den>\d+))?
    \s*(?P<unit>[a-z]+|"|″|')\.?$""",
    re.I | re.X,
)


def parse_length(text: str) -> tuple[Decimal, str] | None:
    """Centimetres, and the unit they were written in, from a measurement with its unit."""
    return _measure(text, _LENGTH_UNITS, CENTS)


def parse_weight(text: str) -> tuple[Decimal, str] | None:
    """Kilograms, and the unit they were written in, from a weight with its unit."""
    return _measure(text, _WEIGHT_UNITS, GRAMS)


def _measure(text: str, units: dict[str, Decimal], step: Decimal) -> tuple[Decimal, str] | None:
    match = _MEASURE.match(text.strip())
    if not match or not (match["whole"] or match["num"]):
        return None
    unit = match["unit"].lower()
    if unit not in units:
        return None
    amount = Decimal(match["whole"] or 0)
    if match["num"]:
        if int(match["den"]) == 0:
            return None
        amount += Decimal(match["num"]) / Decimal(match["den"])
    value = (amount * units[unit]).quantize(step, rounding=ROUND_HALF_UP)
    return (value, unit) if value <= _MAX_MEASURE else None


_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}


def parse_partial_date(text: str) -> str | None:
    """An ISO date at the precision given: "1998", "1998-06" or "1998-06-15".

    Reads ISO forms, month names ("March 5, 2021", "5 March 2021", "March 2021") and
    US numeric dates ("3/5/2021", "3/2021"). "circa 1998" or "1990s" are not dates.
    """
    t = text.strip()
    if m := re.fullmatch(r"(\d{4})", t):
        return _iso(int(m[1]))
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", t):
        return _iso(int(m[1]), int(m[2]), int(m[3]) if m[3] else None)
    if m := re.fullmatch(r"([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", t, re.I):
        return _named(m[1], int(m[3]), int(m[2]))
    if m := re.fullmatch(r"(\d{1,2})\s+([a-z]+)\.?,?\s+(\d{4})", t, re.I):
        return _named(m[2], int(m[3]), int(m[1]))
    if m := re.fullmatch(r"([a-z]+)\.?,?\s+(\d{4})", t, re.I):
        return _named(m[1], int(m[2]))
    if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t):
        return _iso(int(m[3]), int(m[1]), int(m[2]))
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", t):
        return _iso(int(m[2]), int(m[1]))
    return None


def _named(month: str, year: int, day: int | None = None) -> str | None:
    number = _MONTHS.get(month.lower())
    return _iso(year, number, day) if number else None


def _iso(year: int, month: int | None = None, day: int | None = None) -> str | None:
    try:
        date(year, month or 1, day or 1)
    except ValueError:
        return None
    if month is None:
        return f"{year:04d}"
    return f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day else "")


def clip(text: str, limit: int) -> tuple[str, bool]:
    """Text cut to fit a column, at a word boundary where one is near, and whether it was cut."""
    if len(text) <= limit:
        return text, False
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip() + "…", True


def texts(value: Any) -> list[str]:
    """The non-empty strings in a value that may be a string, a number or a list of them."""
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list):
        return [text for element in value for text in texts(element)]
    return []


def records(value: Any) -> list[dict]:
    """The objects in a value that may be one object or a list of them."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [element for element in value if isinstance(element, dict)]
    return []


def _decimal(text: str, step: Decimal) -> Decimal | None:
    try:
        return Decimal(text).quantize(step, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
