"""Dates known only as precisely as the owner knows them."""

from datetime import date
from typing import Annotated

from pydantic import AfterValidator, Field


def _real_date(value: str) -> str:
    year, month, day = (value.split("-") + ["01", "01"])[:3]
    try:
        date(int(year), int(month), int(day))
    except ValueError as exc:
        raise ValueError(f"{value!r} is not a real date") from exc
    return value


# ISO 8601 at the precision that is known: "1998", "1998-06" or "1998-06-15". Stored
# as text, it still sorts chronologically, and nothing is invented to fill a full date.
PartialDate = Annotated[
    str,
    Field(
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        examples=["1998", "1998-06", "1998-06-15"],
    ),
    AfterValidator(_real_date),
]
