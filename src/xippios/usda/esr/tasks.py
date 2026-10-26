"""Task-shaped functions for USDA FAS Export Sales Reporting.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

Codes and market years are integers, as the snapshot types the path parameters
(``int32``) and as the wire carries them (Johannes, 2026-10-25; ADR-0003); they are
checked against the packaged lists before any call, since ESR answers an unknown code
with an empty list. A market year is ESR's, named by the year it ends in and different
per commodity; nothing is re-based.

Release metadata (Johannes, 2026-10-25): ``get_exports`` makes one call and no second
one for the release time, so its ``meta.published_at`` stays ``None`` and its
``meta.vintage`` is the latest ``weekEndingDate`` among the records as an ISO date
(``"2024-06-06"``), a data-as-of label, ``None`` for an empty list.
``get_release_dates`` is the way to learn when ESR released the data. Its own
``meta.published_at`` stays ``None`` too, because the snapshot states no time zone for
``releaseTimeStamp`` (the program page that might say Eastern answers 403 to headless
clients, ``docs/upstream/FETCHED.md``) and an invented zone could shift the time by
hours in an as-of store. Its ``meta.vintage`` is the latest ``releaseTimeStamp``'s text,
upstream's release identifier (conventions §4), built as ``isoformat()`` of the parsed
naive datetime (Johannes, 2026-10-26, for every FAS package): upstream writes two
fractional digits (``2026-10-22T08:30:42.67``) and the vintage renders six
(``"2026-10-22T08:30:42.670000"``).
"""

from collections.abc import Mapping

from xippios.core import Result, ResultMeta, sync

from xippios.usda.esr import api
from xippios.usda.esr._client import SOURCE
from xippios.usda.esr.errors import NoDataForYear
from xippios.usda.esr.models import CommodityData, DataReleaseInfo
from xippios.usda.esr.params import (
    validate_commodity_code,
    validate_country_code,
    validate_market_year,
)

__all__ = ["get_exports", "get_release_dates"]

try:
    from xippios.core.mcp import ResultCap
except ImportError:  # pragma: no cover - a base install, without the mcp extra, has no server
    MCP_CAPS: "Mapping[str, ResultCap]" = {}
else:
    MCP_CAPS = {
        "get_exports": ResultCap(
            note="pass country_code, e.g. 1220 (Canada), for one destination's weeks, up to 54 rows"
        )
    }
"""MCP result caps of their own, by task function name (conventions §8, ADR-0016).

``get_exports`` keeps the family's bounds, 200 rows or 64 KB, with a note of its own: a
tool with filters names them in its cap's note (§8; Johannes, 2026-10-25). Every country
at once is one row per destination and week (cottonseed 2024: 498 rows for 11
destinations), and ``country_code`` narrows it to one destination's weeks, up to 54 rows
(wheat white to Canada 2024). ``get_release_dates``, 44 rows, keeps the default.
``ResultCap`` lives in ``xippios.core.mcp``, which needs the ``mcp`` extra, so a base
install, which serves no MCP tool, has no caps.
"""


def _vintage(records: list[CommodityData]) -> str | None:
    """The latest ``weekEndingDate`` across ``records`` as an ISO date; ``None`` if empty."""
    if not records:
        return None
    return max(record.week_ending_date for record in records).isoformat()


def _release_vintage(releases: list[DataReleaseInfo]) -> str | None:
    """The latest ``releaseTimeStamp`` across ``releases`` as its text; ``None`` if empty.

    The text is ``isoformat()`` of the naive datetime, the family's construction for FAS
    release timestamps: upstream writes two fractional digits (``2026-10-22T08:30:42.67``),
    the vintage renders six (``"2026-10-22T08:30:42.670000"``).
    """
    if not releases:
        return None
    return max(release.release_time_stamp for release in releases).isoformat()


def _absent(
    exc: NoDataForYear, commodity_code: int, country: str, market_year: int
) -> NoDataForYear:
    """ESR's empty 404 again, naming what was asked for.

    Only ``NoDataForYear`` means "no data for this market year"; any other
    ``NotFoundError`` (the gateway's ``NOT_FOUND``) is not caught and propagates as is.
    """
    return NoDataForYear(
        exc.path,
        f"ESR has no data for commodity {commodity_code}, {country}, market year "
        f"{market_year}: GET {exc.path} answered HTTP 404 with an empty body.",
    )


async def get_exports_async(
    commodity_code: int, market_year: int, country_code: int | None = None
) -> Result[list[CommodityData]]:
    """US weekly export sales of one commodity in one market year, to one country or to all.

    One record per destination country and week of ESR's market year: weekly exports,
    accumulated exports, outstanding sales, gross new sales, current and next market year
    net sales and commitments, in the unit ``unit_id`` names (``1`` metric tons, ``2``
    running bales for cotton; ``enums.UnitId``). A market year is named by the year it
    ends in and differs per commodity: for wheat 2024 runs June 2023 to May 2024, for corn
    and soybeans September to August, for cotton August to July (``get_release_dates``
    lists each commodity's current one). Codes and the year are checked before any call:
    an unknown code raises ``InvalidRequestError`` naming the closest known codes, and a
    market year that is not four digits or is after the current calendar year plus two
    raises ``InvalidRequestError`` with the reason. An empty list means ESR has no
    records for that combination; a market year ESR holds no data for (1900) raises
    ``NotFoundError``. ``meta.vintage`` is the latest week ending date among the records
    (``"2024-06-06"``); ``meta.published_at`` stays empty, ``get_release_dates`` tells
    when ESR released the data. The MCP server returns at most 200 rows per call, and
    every country at once is one row per destination and week (cottonseed 2024: 498 rows
    for 11 destinations; wheat HRW 2024: 1,136 rows for 28), so pass ``country_code``
    there to narrow; one country is up to 54 rows.

    Args:
        commodity_code: ESR commodity code, an integer, e.g. ``104`` (Wheat - White),
            ``101`` (Wheat - HRW), ``401`` (Corn), ``801`` (Soybeans), ``1404`` (All
            Upland Cotton).
        market_year: ESR market year, named by its end year, e.g. ``2024`` (for wheat
            June 2023 to May 2024).
        country_code: ESR destination country code (not ISO), an integer, e.g. ``1220``
            (Canada), ``2010`` (Mexico), ``5880`` (Japan). Omit it (``None``) for every
            country: one record per destination and week.
    """
    validate_commodity_code(commodity_code)
    validate_market_year(market_year)
    if country_code is not None:
        validate_country_code(country_code)
    request: dict[str, int | None] = {
        "commodity_code": commodity_code,
        "market_year": market_year,
        "country_code": country_code,
    }
    try:
        if country_code is None:
            endpoint = "ESRData_GetAllCountriesData"
            records = await api.ESRData_GetAllCountriesData(commodity_code, market_year)
        else:
            endpoint = "ESRData_GetCountryData"
            records = await api.ESRData_GetCountryData(commodity_code, country_code, market_year)
    except NoDataForYear as exc:
        country = "every country" if country_code is None else f"country {country_code}"
        raise _absent(exc, commodity_code, country, market_year) from exc
    meta = ResultMeta(source=SOURCE, endpoint=endpoint, vintage=_vintage(records), request=request)
    return Result(data=records, meta=meta)


async def get_release_dates_async() -> Result[list[DataReleaseInfo]]:
    """When ESR last released each commodity's export data, with its current market year.

    One record per commodity (44): ``release_time_stamp``, the last release of that
    commodity's export data, which can revise several market years; and the current
    market year, named by the year it ends in, with its first and last day (wheat 2027
    runs 2026-06-01 to 2027-05-31, corn and soybeans September to August, cotton August
    to July, beef and pork the calendar year). Compare ``release_time_stamp`` with the one
    seen last to fetch only what changed with ``get_exports``. The time stamp is as ESR
    sends it, without a time zone, since the documentation names none; so
    ``meta.published_at`` stays empty and ``meta.vintage`` is the latest release time
    stamp's text, ESR's release identifier: upstream writes two fractional digits
    (``2026-10-22T08:30:42.67``), the vintage renders six
    (``"2026-10-22T08:30:42.670000"``). Takes no parameters: the endpoint takes none.
    """
    releases = await api.ESRData_GetDataReleaseInfo()
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetDataReleaseInfo",
        vintage=_release_vintage(releases),
        request={},
    )
    return Result(data=releases, meta=meta)


get_exports = sync(get_exports_async)
get_release_dates = sync(get_release_dates_async)
