"""Packaged ESR reference lists and the argument checks built on them (conventions §3).

The four small, stable lists ESR publishes, commodities, countries, regions and units of
measure, ship inside the package under ``reference/`` so argument checks and lookups need no
network call. ``scripts/refresh_reference.py`` writes them through the ``api/`` wrappers,
never by hand, and regenerates the ``UnitId`` enum in ``enums.py``; ``reference/README.md``
carries the provenance of every file. Each file keeps upstream's records verbatim, under
upstream's field names, and ``PackagedList.load(PACKAGE, name)`` from ``xippios.core`` reads
one (sdk-core ADR-0041, decision 5). Each list a check or a name reads is declared once,
``PackagedList.codes`` (sdk-core ADR-0045): ``COMMODITIES``, ``COUNTRIES`` and ``REGIONS``,
whose ``check`` refuses a code the list lacks with core's ``UnknownCode``, naming the nearest
codes, ``_closest``: by number through core's ``nearest``, then by ESR's own pass on the
digits (https://github.com/xippios/sdk-usda-esr/issues/27); ``COUNTRIES`` and ``UNITS`` name the
codes of an exports record, the ``NamedBy`` of ``models.CommodityData`` (sdk-core ADR-0067).
Each refusal before a request says that nothing was sent, core's and the package's own
(conventions §5).

Codes are integers, as the snapshot types the path parameters (``int32``) and as every
recorded record carries them (https://github.com/xippios/sdk-usda-esr/pull/3; sdk-core
ADR-0028): a check takes an ``int`` and refuses anything else, ``True`` included, in core's
wording, which names the integer to pass for a text of digits and the codes whose name holds
another text.

Refresh policy: ``/refresh-reference-data`` runs inside ``/release-prep``, and whenever
a validation failure names a code the package lacks.
"""

import difflib
from collections.abc import Mapping
from datetime import UTC, datetime

from xippios.core import InvalidRequestError, PackagedCodes, PackagedList, nearest

from xippios.usda.esr._client import SOURCE

__all__ = [
    "COMMODITIES",
    "COUNTRIES",
    "PACKAGED_LISTS",
    "REGIONS",
    "UNITS",
    "latest_market_year",
    "validate_commodity_code",
    "validate_country_code",
    "validate_market_year",
    "validate_region_id",
]

PACKAGE = "xippios.usda.esr"

PACKAGED_LISTS: tuple[str, ...] = ("commodities", "countries", "regions", "unitsOfMeasure")
"""Lists that ship inside the package, named as the upstream path names them.

Keep in step with the ``LISTS`` of ``scripts/refresh_reference.py``, one ``Listed`` each,
which core's frame checks against it before a refresh (conventions §3).
"""

EARLIEST_MARKET_YEAR = 1000
"""The lowest market year the package sends: a four-digit year, a shape check only.

The snapshot types ``marketYear`` as ``int32`` and names no range. ``classify`` maps
ESR's answer for a market year it holds no data for to the shared package's ``NoDataForYear``
through the gateway, so an early year needs no refusal of its own. Where ESR's data begins is not
established, so no later bound is set. What ESR answered for market years 1900, 1998 and
1999 is noted in ``docs/upstream/OBSERVED.md``, each answer with the probe that showed
it, a recording or a request.
"""


COMMODITIES: PackagedCodes = PackagedList.load(PACKAGE, "commodities").codes(
    "commodityCode", "commodityName", source=SOURCE
)
"""The packaged commodities by ``commodityCode``, each named by its ``commodityName``."""

COUNTRIES: PackagedCodes = PackagedList.load(PACKAGE, "countries").codes(
    "countryCode", "countryDescription", source=SOURCE
)
"""The packaged destination countries by ``countryCode``, each named by its
``countryDescription``, padded upstream: a refusal and ``meta.names`` show it with its runs of
white space collapsed, ``"CANADA"`` (sdk-core ADR-0056)."""

REGIONS: PackagedCodes = PackagedList.load(PACKAGE, "regions").codes(
    "regionId", "regionName", source=SOURCE
)
"""The packaged regions by ``regionId``, each named by its ``regionName``."""

UNITS: PackagedCodes = PackagedList.load(PACKAGE, "unitsOfMeasure").codes(
    "unitId", "unitNames", source=SOURCE
)
"""The packaged units by ``unitId``, each named by its ``unitNames``, plural upstream: the
names of ``unit_id`` in an answer's ``meta.names`` (sdk-core ADR-0067)."""

_REASON = "ESR answers unknown codes with an empty result, so the package refuses them."
"""Why a code the packaged list lacks is refused before the call, for ``UnknownCode``."""

_REGION_REASON = (
    "Every region of the packaged list holds a country, so a region it lacks would answer an "
    "empty list, and the package refuses it."
)
"""Why ``list_countries`` refuses a region id the packaged list lacks."""


def _closest(value: int | str, codes: Mapping[int, str]) -> list[tuple[int, str]]:
    """Up to three known codes close to ``value``: the nearest two by number, then by digits.

    The pass by number is core's ``nearest``, the strategy this package carried until
    sdk-core 0.4.0 took it in (https://github.com/xippios/sdk-core/issues/107); the pass by
    digits stays ESR's own, which neither ``nearest`` nor ``closest`` (for string codes)
    covers (sdk-core ADR-0023, decision 4).

    The commodity ``999`` leads to ``1001`` (Flaxseed) and ``902`` (Soybean Oil), the
    nearest by number; ``1040``, a stray digit, also to ``104`` (Wheat - White), found by
    ``difflib`` on the digit strings; the country ``1202``, two digits swapped, to
    ``1220`` (Canada). Core's ``check`` calls it with the list's codes and their names, the
    names' runs of white space collapsed, for an integer the list lacks and for a text that is
    no number (sdk-core ADR-0045, decision 4, amended 2026-11-22): a text names no code here,
    so that core names the codes whose name holds it, ``"wheat"`` naming ``101`` to ``103``.
    """
    if not isinstance(value, int):
        return []
    by_number = [code for code, _ in nearest(value, codes, n=2)]
    by_digits = [
        int(text)
        for text in difflib.get_close_matches(str(value), [str(code) for code in codes], n=3)
    ]
    matches = list(dict.fromkeys([*by_number, *by_digits]))[:3]
    return [(code, codes[code]) for code in matches]


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
        InvalidRequestError: When the code is not an integer, naming the integer to pass for
            a text of digits and codes whose upstream name matches another text.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names.
    """
    return COMMODITIES.check("commodity_code", commodity_code, closest=_closest, reason=_REASON)


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
        InvalidRequestError: When the code is not an integer, naming the integer to pass for
            a text of digits and codes whose upstream name matches another text.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names.
    """
    return COUNTRIES.check("country_code", country_code, closest=_closest, reason=_REASON)


def validate_region_id(region_id: int) -> int:
    """Check a region id against the packaged ``regions`` list, for ``list_countries``.

    The filter answers from the packaged countries and sends no request, and every region
    of the packaged list holds a country, so a region the list lacks would answer an empty
    list: it is refused instead (https://github.com/xippios/sdk-usda-esr/issues/27).

    Args:
        region_id: ESR's integer region id, as ``ESRData_GetRegions`` lists it, e.g. ``11``
            (WESTERN HEMISPHERE), ``10`` (AFRICA).

    Returns:
        The id, unchanged.

    Raises:
        InvalidRequestError: When the id is not an integer, naming the integer to pass for a
            text of digits.
        UnknownCode: When the list lacks the id, naming up to three close ids with their
            upstream names.
    """
    return REGIONS.check("region_id", region_id, reason=_REGION_REASON)


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


def validate_market_year(market_year: int, *, name: str = "market_year") -> int:
    """Check that a market year is a four-digit integer no later than ``latest_market_year()``.

    Args:
        market_year: ESR's market year, named by its end year, e.g. ``2024`` (for wheat
            June 2023 to May 2024).
        name: The caller's parameter the year came in, which a refusal names, as
            ``UnknownCode`` names its ``param``: e.g. ``"start_year"`` or ``"end_year"``
            for ``get_weekly_series``; ``"market_year"`` by default, the parameter of
            every other task.

    Returns:
        The year, unchanged.

    Raises:
        InvalidRequestError: When the year is not a four-digit integer (``24``, ``999``,
            ``10000``, ``-2024``), or when it is later than the current calendar year plus
            two (``2099``); the message names ``name`` and gives the reason that applies.
    """
    latest = latest_market_year()
    if (
        isinstance(market_year, bool)
        or not isinstance(market_year, int)
        or not EARLIEST_MARKET_YEAR <= market_year <= 9999
    ):
        raise InvalidRequestError(
            f"{name} must be a four-digit year no later than {latest}, such as 2024, "
            f"got {market_year!r}. Nothing was sent. ESR names a market year by the full year "
            "it ends in: for wheat, 2024 runs June 2023 to May 2024.",
            source=SOURCE,
        )
    if market_year > latest:
        raise InvalidRequestError(
            f"{name} must be no later than {latest}, the current year plus two, got "
            f"{market_year}. Nothing was sent. ESR names a market year by the year it ends in "
            "and answers a future one with an empty result, so the package refuses it.",
            source=SOURCE,
        )
    return market_year
