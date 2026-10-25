"""Packaged ESR reference lists and the argument checks built on them (conventions §3).

The four small, stable lists ESR publishes, commodities, countries, regions and units of
measure, ship inside the package under ``reference/`` so argument checks and lookups need
no network call. ``scripts/refresh_reference.py`` writes them through the ``api/``
wrappers, never by hand, and regenerates the ``UnitId`` enum in ``enums.py``;
``reference/README.md`` carries the provenance of every file. Each file keeps upstream's
records verbatim, under upstream's field names.

Codes are integers, as the snapshot types the path parameters (``int32``) and as every
recorded record carries them (Johannes, 2026-10-25; ADR-0003): a check takes an ``int``
and refuses anything else, ``True`` included.

Refresh policy: ``/refresh-reference-data`` runs inside ``/release-prep``, and whenever
a validation failure names a code the package lacks.
"""

import difflib
import functools
from datetime import UTC, date, datetime
from typing import Any

from xippios.core import InvalidRequestError, UpstreamModel, load_json

from xippios.usda.esr._client import SOURCE
from xippios.usda.esr.errors import UnknownCode

__all__ = [
    "PACKAGED_LISTS",
    "PackagedList",
    "latest_market_year",
    "packaged_values",
    "validate_commodity_code",
    "validate_country_code",
    "validate_market_year",
]

PACKAGE = "xippios.usda.esr"

PACKAGED_LISTS: tuple[str, ...] = ("commodities", "countries", "regions", "unitsOfMeasure")
"""Lists that ship inside the package, named as the upstream path names them.

Keep in step with ``ID_LISTS`` and ``TABLES`` in ``scripts/refresh_reference.py``, which
checks it before a refresh.
"""

EARLIEST_MARKET_YEAR = 1000
"""The lowest market year the package sends: a four-digit year, a shape check only.

The snapshot types ``marketYear`` as ``int32`` and names no range. ESR answers a market
year it holds no data for with HTTP 404 and an empty body (recorded for 1900), which
``classify`` maps to ``errors.NoDataForYear``, so an early year needs no refusal of its
own; market years 1998 and 1999 answered HTTP 200 with ``[]`` for wheat white to Canada
(probed 2026-10-25, not kept), the same as a pair without exports, so where ESR's data
begins is not established and no later bound is set.
"""


class PackagedList(UpstreamModel):
    """One packaged list: ``reference/<name>.json``.

    Attributes:
        param: The list, as the upstream path names it, e.g. ``"commodities"``.
        endpoint: The upstream operation it was fetched from, e.g.
            ``"ESRData_GetCommodities"``.
        fetched: Day the list was fetched (UTC).
        records: Upstream's records verbatim, under upstream's field names, in upstream
            order, e.g. ``{"commodityCode": 104, "commodityName": "Wheat - White",
            "unitId": 1}``.
    """

    param: str
    endpoint: str
    fetched: date
    records: list[dict[str, Any]]


def packaged_values(name: str) -> PackagedList | None:
    """The packaged list ``name``, or ``None`` when it is not packaged."""
    if name not in PACKAGED_LISTS:
        return None
    return PackagedList.model_validate(load_json(PACKAGE, f"{name}.json"))


@functools.cache
def _codes(name: str, code_field: str, name_field: str) -> tuple[str, dict[int, str]]:
    """Fetch date and ``{code: upstream name}`` of a packaged list, in upstream order.

    The name is stripped of upstream's padding for messages and name matching
    (``"CANADA                         "`` reads ``"CANADA"``); the packaged records keep it.
    """
    packaged = packaged_values(name)
    if packaged is None:  # pragma: no cover - only the lists above are asked for
        raise KeyError(name)
    codes = {
        int(record[code_field]): " ".join(str(record[name_field]).split())
        for record in packaged.records
    }
    return packaged.fetched.isoformat(), codes


def _closest(value: int, codes: dict[int, str]) -> list[tuple[int, str]]:
    """Up to three known codes close to ``value``: the nearest two by number, then by digits.

    The commodity ``999`` leads to ``1001`` (Flaxseed) and ``902`` (Soybean Oil), the
    nearest by number; ``1040``, a stray digit, also to ``104`` (Wheat - White), found by
    ``difflib`` on the digit strings; the country ``1202``, two digits swapped, to
    ``1220`` (Canada).
    """
    nearest = sorted(codes, key=lambda code: (abs(code - value), code))[:2]
    by_digits = [
        int(text)
        for text in difflib.get_close_matches(str(value), [str(code) for code in codes], n=3)
    ]
    matches = list(dict.fromkeys([*nearest, *by_digits]))[:3]
    return [(code, codes[code]) for code in matches]


def _by_name(text: str, codes: dict[int, str]) -> list[tuple[int, str]]:
    """Up to three known codes whose upstream name contains or resembles ``text``."""
    wanted = " ".join(text.split()).lower()
    names = {name.lower(): code for code, name in codes.items()}
    matches = [code for name, code in names.items() if wanted and wanted in name]
    matches += [
        names[name]
        for name in difflib.get_close_matches(wanted, list(names), n=3)
        if names[name] not in matches
    ]
    return [(code, codes[code]) for code in matches[:3]]


def _validate_code(
    param: str, value: object, list_name: str, code_field: str, name_field: str, example: str
) -> int:
    fetched, codes = _codes(list_name, code_field, name_field)
    if isinstance(value, bool) or not isinstance(value, int):
        named = _by_name(value, codes) if isinstance(value, str) else []
        hint = (
            " By name: " + ", ".join(f"{code} ({name})" for code, name in named) + "."
            if named
            else ""
        )
        if isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
            hint = f" Pass it as the integer {int(value)}."
        raise InvalidRequestError(
            f"{param} must be an integer code such as {example}, got {value!r}.{hint} ESR's "
            f"codes are integers; the packaged {list_name} list (fetched {fetched}) names them.",
            source=SOURCE,
        )
    if value in codes:
        return value
    raise UnknownCode(
        param, value, list_name=list_name, fetched=fetched, closest=_closest(value, codes)
    )


def validate_commodity_code(commodity_code: int) -> int:
    """Check a commodity code against the packaged ``commodities`` list.

    ESR answers an unknown code with HTTP 200 and ``[]``, the same as a query without
    exports, so the check runs before any upstream call.

    Args:
        commodity_code: An integer, as ``ESRData_GetCommodities`` lists it, e.g. ``104``
            (Wheat - White), ``401`` (Corn), ``801`` (Soybeans), ``1404`` (All Upland
            Cotton).

    Returns:
        The code, unchanged.

    Raises:
        InvalidRequestError: When the code is not an integer, naming codes whose upstream
            name matches a string given.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names.
    """
    return _validate_code(
        "commodity_code",
        commodity_code,
        "commodities",
        "commodityCode",
        "commodityName",
        "104 (Wheat - White)",
    )


def validate_country_code(country_code: int) -> int:
    """Check a country code against the packaged ``countries`` list.

    ESR answers an unknown code with HTTP 200 and ``[]``, the same as a query without
    exports, so the check runs before any upstream call.

    Args:
        country_code: ESR's integer code (not ISO), as ``ESRData_GetCountries`` lists it,
            e.g. ``1220`` (Canada), ``2010`` (Mexico), ``5880`` (Japan).

    Returns:
        The code, unchanged.

    Raises:
        InvalidRequestError: When the code is not an integer, naming codes whose upstream
            name matches a string given.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names.
    """
    return _validate_code(
        "country_code", country_code, "countries", "countryCode", "countryDescription", "1220"
    )


def latest_market_year() -> int:
    """The latest market year the package sends: the current UTC calendar year plus two.

    A market year is named by the year it ends in, so the current one of any commodity
    ends at most a year from now: on 2026-10-25 ``ESRData_GetDataReleaseInfo`` names 2027
    as the latest (wheat, June 2026 to May 2027), the current year plus one. One more year
    leaves room for the next market year, which ESR's next-market-year sales point to.
    ESR answers a market year in the future with HTTP 200 and ``[]`` (recorded for 2099),
    indistinguishable from a year without exports, so a later year is refused before any
    call, as an unknown code is.
    """
    return datetime.now(UTC).year + 2


def validate_market_year(market_year: int) -> int:
    """Check that a market year is a four-digit integer no later than ``latest_market_year()``.

    Args:
        market_year: ESR's market year, named by its end year, e.g. ``2024`` (for wheat
            June 2023 to May 2024).

    Returns:
        The year, unchanged.

    Raises:
        InvalidRequestError: When the year is not an integer from 1000 to the current
            calendar year plus two.
    """
    latest = latest_market_year()
    if (
        isinstance(market_year, bool)
        or not isinstance(market_year, int)
        or not EARLIEST_MARKET_YEAR <= market_year <= latest
    ):
        raise InvalidRequestError(
            f"market_year must be a four-digit year no later than {latest}, such as 2024, "
            f"got {market_year!r}. ESR names a market year by the year it ends in and answers "
            "a future one with an empty result, so the package refuses it.",
            source=SOURCE,
        )
    return market_year
