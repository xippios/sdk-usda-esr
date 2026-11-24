"""Task-shaped functions for USDA FAS Export Sales Reporting.

The public API (sdk-core ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register what
is named there minus ``BULK_TASKS``.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

Codes and market years are integers, as the snapshot types the path parameters (``int32``) and
as the wire carries them (https://github.com/xippios/sdk-usda-esr/pull/3; sdk-core ADR-0028);
they are checked against the packaged lists before any call, since ESR answers an unknown code
with an empty list. A market year is ESR's, named by the year it ends in and different per
commodity; nothing is re-based.

Release metadata (https://github.com/xippios/sdk-usda-esr/pull/3): an exports answer states
no release of its own, so ``get_exports`` and ``get_weekly_series`` leave ``meta.vintage`` and
``meta.published_at`` ``None``: ``vintage`` is set only from a release identifier that upstream
states for the data answered, and a week computed from the records is none (conventions §4;
https://github.com/xippios/sdk-usda-esr/issues/67). ``get_release_dates`` is the way to learn
when ESR released the data (https://github.com/xippios/sdk-usda-esr/pull/7; sdk-core ADR-0041,
decision 2). Its ``meta.published_at`` is the newest ``releaseTimeStamp`` as upstream gives it,
naive, with ``meta.published_at_naive`` set: the snapshot states no time zone for it (the
program page that might say Eastern answers 403 to headless clients,
``docs/upstream/FETCHED.md``), and none is invented, since an invented zone could shift
the time by hours in an as-of store. Its ``meta.vintage`` is that time in the form upstream
prints it (``"2026-10-22T08:30:42.67"``), upstream's release identifier: where the identifier
is the timestamp text, ``vintage`` holds the text and ``published_at`` its parsed value with
the flag (conventions §4). The record keeps no text beside the parsed time, which keeps every
digit upstream sends (https://github.com/xippios/sdk-usda-esr/issues/69), so ``_as_printed``
writes the text from it. Both are ``None`` for an empty answer.

Change detection is ``get_release_dates``' parameter ``since``
(https://github.com/xippios/sdk-usda-esr/pull/9): the ``meta.vintage`` text of an earlier call,
read by the package's own ``_since`` with ``datetime.fromisoformat`` to a naive time, since
upstream's text carries no zone; a text that does not parse, or parses to an aware time, is
refused before the call (``InvalidRequestError``, conventions §5, sdk-core ADR-0007). Core's
``newer_than``, handed that reader, keeps the commodities released strictly after it, an equal
time being no newer, and only selects (sdk-core ADR-0028, ADR-0052;
https://github.com/xippios/sdk-usda-esr/issues/31).
``meta.vintage`` and ``meta.published_at`` stay the newest release of upstream's whole answer,
filtered or not, so an empty filtered answer still hands the caller the marker to store for the
next call. It is one request either way, and core's cache answers a second within its
lifetime, with the time its entry was stored as ``retrieved_at``. The lookup of one
commodity's current market year is the argument ``commodity_code``, upstream's
``commodityCode``, which keeps that commodity's record after the same one request, as the
boundary of a source package has a lookup by a key that the caller names (conventions §14),
where ``get_market_year`` was a task of its own (https://github.com/xippios/sdk-usda-esr/pull/9);
a commodity the packaged list names and the release list lacks answers the empty list.

A ranking, a selection of the newest week and the other slices are no task of a source package
(conventions §14): a caller reads those records from ``get_exports``. ``get_weekly_series``
(https://github.com/xippios/sdk-usda-esr/pull/5) puts together and orders the records of the
request ``get_exports`` makes for one country (sdk-core ADR-0028): no record is changed,
nothing is derived, converted, filled or excluded, and nothing is compared with another source.
It makes its one-country request once per market year from ``start_year`` to ``end_year``, at
most ``SERIES.value`` of them, core's ``Ceiling`` and ``fetch_periods``
(https://github.com/xippios/sdk-usda-esr/pull/10, https://github.com/xippios/sdk-usda-esr/issues/29;
conventions §4's period series, as sdk-usda-psd's ``get_time_series``), and, for a range
ending in the current calendar year or later, reads the release list first and refuses a range
past the commodity's current market year with ``NotFoundError``, since ESR answers an
unreleased market year with ``[]`` as it answers a year without exports
(https://github.com/xippios/sdk-usda-esr/pull/10; sdk-core ADR-0041, decisions 6 and 7).
``get_exports`` reads the release list likewise for a market year from the current calendar
year on and refuses one past the commodity's current market year, so that no data has one
answer, the empty list, and an unreleased year another (conventions §5;
https://github.com/xippios/sdk-usda-esr/issues/21). The series' ``meta.endpoint`` is the
operation the records come from, ``meta.request`` carries every parameter, ``meta.vintage``
and ``meta.published_at`` stay ``None``, as for ``get_exports``, and ``meta.notes`` names
each market year answered with its count of rows, in the order of the rows, and each passed
over, since no record states its market year (https://github.com/xippios/sdk-usda-esr/issues/23).

The ``list_*`` tasks answer from the four lists packaged under ``reference/`` and make no
upstream call (https://github.com/xippios/sdk-usda-esr/pull/4). Core's ``PackagedList`` reads
the file and builds ``meta`` (sdk-core ADR-0041, decision 1): ``meta.endpoint`` is the operation
the list was fetched from (``"ESRData_GetCountries"``), ``meta.retrieved_at`` is when the
package fetched the list, the file's ``fetched``, a UTC time to the second
(``2026-10-28T19:19:52Z`` for the countries), and ``meta.vintage`` is ``None``: upstream gives
these lists no release identifier, and a fetch date is not one. ``meta.published_at`` stays
``None``, and so does ``meta.total``, since upstream reports no count (sdk-core ADR-0034). The
records keep upstream's order, field names (snake_cased) and values, padding included. Their
filters only select records of the packaged list (sdk-core ADR-0028), and ``meta.request``
carries those given: ``region_id`` is named after upstream's ``regionId``, checked against the
packaged regions list and matched exactly (https://github.com/xippios/sdk-usda-esr/issues/27),
``search`` is the package's own (the four operations take no parameters), a
case-insensitive substring match on codes, as digits, on names and, for countries, on GENC codes
(``xippios.core.matches``).
"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from xippios.core import (
    Answer,
    Ceiling,
    InvalidRequestError,
    NotFoundError,
    PackagedList,
    Result,
    ResultCap,
    ResultMeta,
    fetch_periods,
    matches,
    names_codes,
    newer_than,
    sync,
)
from xippios.usda.fas import NoDataForYear

from xippios.usda.esr import api
from xippios.usda.esr._client import SOURCE
from xippios.usda.esr.models import (
    Commodity,
    CommodityData,
    Country,
    DataReleaseInfo,
    Region,
    UnitOfMeasure,
)
from xippios.usda.esr.params import (
    COUNTRIES,
    PACKAGE,
    validate_commodity_code,
    validate_country_code,
    validate_market_year,
    validate_region_id,
)

__all__ = [
    "get_exports",
    "get_release_dates",
    "get_weekly_series",
    "list_commodities",
    "list_countries",
    "list_regions",
    "list_units_of_measure",
]

MCP_INSTRUCTIONS = (
    "USDA FAS Export Sales Reporting via xippios. "
    "Tools are read-only. "
    "Where list tools (usda_esr_list_*) exist, call them first to find valid values, "
    "then query."
)
"""The read server's instructions for agents, which core's tool set reads from this module
(conventions §8; sdk-core ADR-0063, decision 7)."""

# A task named here is Python-only: no tool, no route; the adapters skip it
# (sdk-core ADR-0040, decision 4).
BULK_TASKS: frozenset[str] = frozenset()

MCP_CAPS: Mapping[str, ResultCap] = {
    "get_exports": ResultCap(
        note=(
            "pass country_code, e.g. 1220 (Canada), for one destination's weeks, up to 54 rows; "
            "one call sends at most 2 requests, 8 attempts with retries"
        ),
        paged=True,
        keep="last",
    ),
    "get_release_dates": ResultCap(
        note=(
            'pass since, e.g. "2026-10-22T08:30:42.67" (an earlier call\'s meta.vintage), to '
            "keep the commodities released after it, or commodity_code, e.g. 104, for one"
        )
    ),
    "get_weekly_series": ResultCap(
        note=(
            "narrow start_year and end_year, e.g. 2023 and 2024: each market year is up to "
            "54 rows, so three fit, and the newest weeks are shown; one call sends at most 11 "
            "requests, 44 attempts with retries"
        ),
        keep="last",
    ),
    "list_commodities": ResultCap(
        note='pass search, e.g. "wheat" or "104", to narrow by code or name'
    ),
    "list_countries": ResultCap(
        max_rows=250,
        note=(
            'pass region_id, e.g. 11 (WESTERN HEMISPHERE), or search, e.g. "korea" or '
            '"1220", to narrow by region or by code, name, description or GENC code'
        ),
    ),
}
"""MCP result caps of their own, by task function name (conventions §8, sdk-core ADR-0038).

``get_exports`` keeps the family's bounds, 200 rows or 64 KB, with a note of its own: a tool
with filters names them in its cap's note (§8; https://github.com/xippios/sdk-usda-esr/pull/3).
Every country at once is one row per destination and week (cottonseed 2024: 498 rows for 11
destinations), and ``country_code`` narrows it to one destination's weeks, up to 54 rows (wheat
white to Canada 2024). Its cap is paged and keeps the last rows (sdk-core ADR-0047;
https://github.com/xippios/sdk-usda-esr/issues/28): the answer runs oldest week first, so a cut
answer shows the newest weeks, and the tool's ``offset`` continues to older ones, each
continuation running the task again, which the cache answers within its lifetime, so a
continuation costs upstream nothing (conventions §8; sdk-core ADR-0061, decision 9). The cache
holds an answer under the client's ``cache_max_bytes``, 8 MiB, and one call fetches at most the
211 packaged countries by 55 week endings at some 300 bytes a row, about 3.5 MB, so the cap
stays paged (https://github.com/xippios/sdk-core/issues/608). Its note states the most that one
call sends, the release list and the exports, each with core's four attempts (conventions §8;
sdk-core ADR-0061, decision 8).
``get_release_dates``, 44 rows, fits the default and keeps the family's bounds, but it has
filters, so its entry carries a note naming ``since`` and ``commodity_code``, as
``list_commodities``' names ``search``.

``get_weekly_series`` keeps the family's bounds too, with a note of its own that names
``start_year`` and ``end_year`` (https://github.com/xippios/sdk-usda-esr/pull/10; §8, sdk-core
ADR-0038), as ``get_exports``' names ``country_code``: one destination's market year is up to 54
rows (wheat white to Canada: 53 in 2023, 54 in 2024), so three market years fit 200 rows and the
ceiling of ``SERIES``, ten, can reach some 540; the cut keeps the last rows, the newest weeks
(sdk-core ADR-0047; https://github.com/xippios/sdk-usda-esr/issues/28), and narrowing the range
shows the rest. It is not paged: with the cache a continuation would cost upstream nothing, so
the rule allows a paged cap, and nothing asks for one. One call sends up to 11 requests with
the release list, and its note states them with core's four attempts for each, 44. No ceiling
of the process's own and no option: the ceiling is the task's, the same in Python, over HTTP
and over MCP.

``list_countries`` is a reference list an agent needs whole to find codes (sdk-core ADR-0038;
https://github.com/xippios/sdk-usda-esr/pull/4): 211 countries when packaged, past the default
of 200 rows, so its cap is 250 rows; the whole list is 28,936 bytes of compact JSON over MCP as
packaged, within the default 64 KB, which it keeps. Its note names its filters, ``region_id``
and ``search`` (§8). ``list_commodities``, 44 rows, fits the default and keeps the family's
bounds, but it has a filter, so its entry carries a note naming ``search`` and nothing else.
``list_regions`` (12 rows) and ``list_units_of_measure`` (5) have no filter and no entry.
"""


SERIES = Ceiling(10, unit="market years", source=SOURCE)
"""Most market years one ``get_weekly_series`` call spans, ends included, core's ``Ceiling``
(https://github.com/xippios/sdk-usda-esr/pull/10, https://github.com/xippios/sdk-usda-esr/issues/29;
conventions §4): one request per market year, so ten years are ten requests, about ten seconds
at ``RATE_LIMIT``'s pace of one a second, of the 1,000 an hour the api.data.gov key shares with
every package that uses it, and one more for the release list when the range ends in the
current calendar year or later: 11 requests at most, 44 attempts with core's four for each. The
same in Python, over HTTP and over MCP, with no option; a longer range is refused before the
first request."""


def _calendar_year() -> int:
    """The current UTC calendar year.

    Market years start between the June before the year they are named for and that year's
    January: in the recorded release list 13 commodities start in June (wheat), 13 in August
    (cotton), 3 in September (corn, soybeans), 5 in October and 10 in January (beef, pork,
    hides, the calendar year). A market year named by the current year may have begun without
    ESR having released a week of it, and one named by a later year may not have begun, so
    ``get_exports`` and ``get_weekly_series`` read the release list for a market year from the
    current year on (https://github.com/xippios/sdk-usda-esr/pull/10,
    https://github.com/xippios/sdk-usda-esr/issues/21).
    """
    return datetime.now(UTC).year


def _as_printed(time: datetime) -> str:
    """A naive release time in the form ESR prints ``releaseTimeStamp``, ``meta.vintage``'s text.

    The ISO date and time with the fraction of a second, its trailing zeros dropped:
    ``datetime(2026, 10, 22, 8, 30, 42, 670000)`` is ``"2026-10-22T08:30:42.67"``, as every
    record of the recorded release list prints it. A whole second, which no recording shows,
    is written without a fraction. ``_since`` reads the text back to the same time.
    """
    return time.isoformat(timespec="microseconds").rstrip("0").rstrip(".")


def _newest_release(releases: list[DataReleaseInfo]) -> DataReleaseInfo | None:
    """The record with the latest ``releaseTimeStamp``, the first of equals; ``None`` if empty."""
    return max(releases, key=lambda release: release.release_time_stamp, default=None)


def _absent(
    exc: NoDataForYear, commodity_code: int, country: str, market_year: int
) -> NoDataForYear:
    """ESR's empty 404 again, naming what was asked for, in the source's name.

    Only ``NoDataForYear``, the shared package's class that the gateway returns on an exports
    path, means "no data for this market year"; any other ``NotFoundError`` (the gateway's
    ``NOT_FOUND``) is not caught and propagates as is.
    """
    return NoDataForYear(
        exc.path,
        f"ESR has no data for commodity {commodity_code}, {country}, market year "
        f"{market_year}: GET {exc.path} answered HTTP 404 with an empty body.",
        source=exc.source,
    )


@names_codes(country_code=COUNTRIES)
async def get_exports_async(
    commodity_code: int, market_year: int, *, country_code: int | None = None
) -> Result[list[CommodityData]]:
    """US weekly export sales of one commodity in one market year, to one country or to all.

    One record per destination and week: weekly and accumulated exports, outstanding and
    gross new sales, current and next market year net sales and commitments, in the unit
    ``unit_id`` names (``list_units_of_measure``). Codes and the year are checked before any
    request. From the current calendar year on, the release list is read first, and a market
    year ESR has not released raises ``NotFoundError`` naming the commodity's current one,
    since ESR answers it as a year without exports; an empty list means no exports. A market
    year ESR holds no data for (1900) raises ``NotFoundError``. One call sends at most 2
    requests, 8 attempts with retries. ``meta.vintage`` and ``meta.published_at`` stay empty,
    since the records state no release: ``get_release_dates`` gives it. Every country at once
    is one row per destination and week, over a thousand for some commodities; one country is
    up to 54 rows.

    Args:
        commodity_code: ESR commodity code, an integer, e.g. ``104`` (Wheat - White),
            ``101`` (Wheat - HRW), ``401`` (Corn), ``801`` (Soybeans), ``1404`` (All
            Upland Cotton); one the packaged list lacks is refused naming the closest codes.
        market_year: ESR market year, named by its end year, e.g. ``2024`` (for wheat
            June 2023 to May 2024, for corn and soybeans September to August, for cotton
            August to July); four digits and no later than the current year plus two, and
            no later than the commodity's current market year, which ``get_release_dates``
            names: in October 2026 wheat's is 2027, and 2028 is refused after one request.
        country_code: ESR destination country code (not ISO), an integer, e.g. ``1220``
            (Canada), ``2010`` (Mexico), ``5880`` (Japan); ``9990`` (UNKNOWN) is a
            destination like any other. Omit it (``None``) for every country: one record per
            destination and week.
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
    await _check_released(
        commodity_code,
        market_year,
        refused=lambda latest: (
            f"market year {market_year} is refused rather than answered as a year without "
            f"exports; ask for market year {latest} or an earlier one"
        ),
    )
    try:
        if country_code is None:
            endpoint = "ESRData_GetAllCountriesData"
            answer = await api.get_all_countries_data(commodity_code, market_year)
        else:
            endpoint = "ESRData_GetCountryData"
            answer = await api.get_country_data(commodity_code, country_code, market_year)
    except NoDataForYear as exc:
        country = "every country" if country_code is None else f"country {country_code}"
        raise _absent(exc, commodity_code, country, market_year) from exc
    meta = ResultMeta(
        source=SOURCE, endpoint=endpoint, retrieved_at=answer.retrieved_at, request=request
    )
    return Result(data=answer.payload, meta=meta)


_SINCE_EXAMPLE = "2026-10-22T08:30:42.67"
"""``meta.vintage`` of ``get_release_dates`` as recorded, the example ``since`` refusals name."""


def _since(since: object) -> datetime:
    """``since`` as the naive time it names; ``InvalidRequestError`` naming the form otherwise.

    The package's own reader, which ``newer_than`` is handed, since core ships none (sdk-core
    ADR-0059, decision 4; https://github.com/xippios/sdk-core/issues/473). It is called before
    the request, so its refusal says that nothing was sent (conventions §5).

    Parsed with ``datetime.fromisoformat``, so a date alone (``"2026-10-01"``) is its
    midnight; a time with a zone is refused, since ESR's release times carry none and the
    two cannot be compared without inventing one (sdk-core ADR-0041, decision 2).
    """
    parsed = None
    if isinstance(since, str):
        try:
            parsed = datetime.fromisoformat(since)
        except ValueError:
            parsed = None
    if parsed is not None and parsed.tzinfo is None:
        return parsed
    reason = (
        "it carries a time zone, and ESR's release times carry none"
        if parsed is not None
        else "it is not an ISO date and time"
    )
    raise InvalidRequestError(
        "since must be the meta.vintage text of an earlier get_release_dates call, an ISO "
        f"date and time without a time zone such as {_SINCE_EXAMPLE!r}; got {since!r}, and "
        f"{reason}. Nothing was sent.",
        source=SOURCE,
    )


async def get_release_dates_async(
    *, commodity_code: int | None = None, since: str | None = None
) -> Result[list[DataReleaseInfo]]:
    """When ESR last released each commodity's export data, with its current market year.

    One request to ``ESRData_GetDataReleaseInfo``, one record per commodity:
    ``release_time_stamp``, the last release of the commodity's export data, which can revise
    several market years, and the current market year, named by the year it ends in, with its
    first and last day. The time stamp is as ESR sends it, without a time zone, since the
    documentation names none: ``meta.published_at`` is the newest of the whole answer, naive,
    with ``meta.published_at_naive`` true, and ``meta.vintage`` that time as ESR prints it,
    with or without a filter; both are empty only when ESR lists no commodity. To fetch only
    what changed, store ``meta.vintage``, pass it as ``since`` on the next call and call
    ``get_exports`` for the commodities returned; an empty list means nothing was released
    since.

    Args:
        commodity_code: Keep only this commodity's record, its current market year, an ESR
            commodity code as ``list_commodities`` gives it, e.g. ``104`` (Wheat - White, June
            to May), ``401`` (Corn, September to August), ``1701`` (beef muscle cuts, the
            calendar year). Compared by equality after the one request, since upstream filters
            nothing; an unknown code is refused before it, naming the closest codes, and a
            commodity the release list lacks answers the empty list. Omit (``None``) for every
            commodity.
        since: Keep only the commodities whose ``release_time_stamp`` is strictly later
            than this time, the ``meta.vintage`` text of an earlier call, e.g.
            ``"2026-10-22T08:30:42.67"``: an ISO date and time without a time zone, as ESR
            prints it, e.g. ``"2026-10-01T00:00:00"`` (a date alone, ``"2026-10-01"``, is
            its midnight). A release at exactly that time is not newer. A text with a zone
            (``"2026-10-22T08:30:42+00:00"``, ``"...Z"``) or one that is not a date and
            time is refused before the call. Omit (``None``) for every commodity.
    """
    if commodity_code is not None:
        validate_commodity_code(commodity_code)
    if since is not None:
        _since(since)  # refused before the request
    answer = await api.get_data_release_info()
    releases = answer.payload
    newest = _newest_release(releases)
    published_at = None if newest is None else newest.release_time_stamp
    selected = [
        release
        for release in newer_than(
            since, releases, released=lambda release: release.release_time_stamp, read=_since
        )
        if commodity_code is None or release.commodity_code == commodity_code
    ]
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetDataReleaseInfo",
        retrieved_at=answer.retrieved_at,
        published_at=published_at,
        published_at_naive=published_at is not None,
        vintage=None if newest is None else _as_printed(newest.release_time_stamp),
        request={"commodity_code": commodity_code, "since": since},
    )
    return Result(data=selected, meta=meta)


def _release_of(commodity_code: int, releases: list[DataReleaseInfo]) -> DataReleaseInfo:
    """The commodity's record of ESR's release list, unchanged; ``NotFoundError`` if absent.

    A commodity the packaged list names and the release list lacks is one upstream has
    dropped: ``get_exports`` and ``get_weekly_series`` refuse a market year from the current
    calendar year on, which they cannot tell released.
    """
    record = next((r for r in releases if r.commodity_code == commodity_code), None)
    if record is None:
        raise NotFoundError(
            f"ESR lists no market year for commodity {commodity_code}: GET "
            "/api/esr/datareleasedates (ESRData_GetDataReleaseInfo) answered without a record "
            "for it, although the packaged commodities list names it.",
            source=SOURCE,
        )
    return record


async def _check_released(
    commodity_code: int, market_year: int, *, refused: Callable[[int], str]
) -> None:
    """Refuse ``market_year`` past the commodity's current market year in ESR's release list.

    ESR answers a market year it has not released with ``[]``, as it answers a year without
    exports, so the task asks the release list first where the year may not be released, one
    from the current calendar year on (``_calendar_year``), and refuses with ``NotFoundError``
    naming the commodity's current market year (conventions §4, §5; sdk-core ADR-0041,
    decisions 6 and 7; https://github.com/xippios/sdk-usda-esr/issues/21). An earlier year
    reads no list. The read is one request, which core's cache answers within its lifetime.

    Args:
        commodity_code: The commodity whose record the release list holds, e.g. ``104``.
        market_year: The latest market year the call asks for, e.g. ``2028``.
        refused: The end of the refusal from the latest released market year, what is
            refused and what to ask for instead, e.g. ``lambda latest: f"... up to {latest}"``.
    """
    if market_year < _calendar_year():
        return
    releases = await api.get_data_release_info()
    latest = _release_of(commodity_code, releases.payload).market_year
    if market_year > latest:
        raise NotFoundError(
            f"ESR has not released market year {market_year} of commodity {commodity_code} "
            f"yet: its latest released market year is {latest}, the current one in ESR's "
            "release list (ESRData_GetDataReleaseInfo). ESR answers a market year it has not "
            "released with an empty list, the same answer as a year without exports, so "
            f"{refused(latest)}.",
            source=SOURCE,
        )


def _years_note(years: range, fetched: list[tuple[int, Answer[list[CommodityData]]]]) -> str:
    """The series' note on its market years, which no record states.

    Each market year answered with its count of rows, in the order of the rows, a released
    year without exports among them with 0, and each passed over for ESR's empty 404, e.g.
    ``"Market years in the order of the rows: 2024 with 54 rows; passed over, without data
    in ESR: 2023."`` The rows run oldest week first and a market year's weeks follow the
    previous year's, the week both hold the older year's row first, so the counts tell which
    rows are whose (https://github.com/xippios/sdk-usda-esr/issues/23; sdk-core ADR-0067,
    decision 1).
    """
    answered = [
        f"{year} with {len(answer.payload)} row{'' if len(answer.payload) == 1 else 's'}"
        for year, answer in fetched
    ]
    kept = {year for year, _ in fetched}
    passed = [str(year) for year in years if year not in kept]
    parts = []
    if answered:
        parts.append(f"in the order of the rows: {', '.join(answered)}")
    if passed:
        parts.append(f"passed over, without data in ESR: {', '.join(passed)}")
    return f"Market years {'; '.join(parts)}."


def _series_range(start_year: int, end_year: int) -> None:
    """Refuse a range that runs backwards or spans more market years than ``SERIES`` allows.

    Both years have passed ``validate_market_year``; the range is checked before the first
    request, as conventions §4 and §5 ask, with ``InvalidRequestError`` (sdk-core ADR-0007),
    each refusal saying that nothing was sent. The order of the range is the task's own, and
    the ceiling core's ``Ceiling.check``, its advice naming the range to ask for (sdk-core
    ADR-0054).
    """
    if start_year > end_year:
        raise InvalidRequestError(
            f"start_year {start_year} is after end_year {end_year}. Nothing was sent. Pass the "
            "earlier market year first, e.g. start_year=2022, end_year=2024.",
            source=SOURCE,
        )
    most = SERIES.value
    SERIES.check(
        end_year - start_year + 1,
        asked=f"{start_year} to {end_year}",
        advice=(
            f"Narrow the range, e.g. start_year={end_year - most + 1}, end_year={end_year}, or "
            f"split it into calls of at most {most}."
        ),
    )


@names_codes(country_code=COUNTRIES)
async def get_weekly_series_async(
    commodity_code: int, country_code: int, *, start_year: int, end_year: int
) -> Result[list[CommodityData]]:
    """One destination's weekly US export sales of a commodity over market years, oldest first.

    One request to ``ESRData_GetCountryData``, the one ``get_exports`` makes with a country,
    per market year from ``start_year`` to ``end_year``, both included, at most 10 market
    years. When ``end_year`` is the current calendar year or later, the release list comes
    first, one request more, and a range past the commodity's current market year raises
    ``NotFoundError`` naming the latest released one. One call sends at most 11 requests, 44
    attempts with retries. The records are ordered by ``week_ending_date`` and otherwise
    unchanged; a week that straddles two market years comes once for each, the older year's
    row first. ``meta.notes`` names each market year with its count of rows, in their order,
    and each passed over, one ESR holds no data for (1900). Any other error stops the call and
    returns nothing. ``meta.vintage`` and ``meta.published_at`` stay empty, as for
    ``get_exports``.

    Args:
        commodity_code: ESR commodity code, an integer, e.g. ``104`` (Wheat - White),
            ``101`` (Wheat - HRW), ``801`` (Soybeans), ``1404`` (All Upland Cotton).
        country_code: ESR destination country code (not ISO), an integer, e.g. ``1220``
            (Canada), ``2010`` (Mexico), ``5880`` (Japan); ``9990`` (UNKNOWN) is a
            destination like any other; ``list_countries`` lists them.
        start_year: First ESR market year, named by its end year, e.g. ``2022`` (for wheat
            June 2021 to May 2022); ``get_release_dates`` names a commodity's current one.
        end_year: Last ESR market year, included, e.g. ``2024``; not before
            ``start_year`` and at most nine years after it (``start_year`` itself for one
            market year), and no later than the commodity's current market year: in
            October 2026, wheat's being 2027, 2024 to 2026 is four requests, 2024 to 2027
            five, and 2024 to 2028 is refused after one; beef muscle cuts (1701), on the
            calendar year, refuse 2025 to 2027. A range ending before the current calendar
            year reads no release list (2023 to 2024 is two requests).
    """
    validate_commodity_code(commodity_code)
    validate_country_code(country_code)
    validate_market_year(start_year, name="start_year")
    validate_market_year(end_year, name="end_year")
    _series_range(start_year, end_year)
    request: dict[str, int] = {
        "commodity_code": commodity_code,
        "country_code": country_code,
        "start_year": start_year,
        "end_year": end_year,
    }
    await _check_released(
        commodity_code,
        end_year,
        refused=lambda latest: (
            f"the range {start_year} to {end_year} is refused rather than returned without "
            f"it; ask for market years up to {latest}"
        ),
    )
    # ESR's empty 404 is no data for that market year, which adds no rows; any other error
    # stops the series, naming the market years fetched before it (sdk-core ADR-0054).
    years = range(start_year, end_year + 1)
    fetched = await fetch_periods(
        years,
        lambda market_year: api.get_country_data(commodity_code, country_code, market_year),
        skip=(NoDataForYear,),
    )
    records = [record for _, answer in fetched for record in answer.payload]
    retrieved = [answer.retrieved_at for _, answer in fetched]
    # sorted() is stable: a week in two market years keeps the older year's row first.
    series = sorted(records, key=lambda record: record.week_ending_date)
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetCountryData",
        # the oldest answer assembled; now where every year answered ESR's empty 404 (§4)
        retrieved_at=min(retrieved, default=datetime.now(UTC)),
        request=request,
        notes=[_years_note(years, fetched)],
    )
    return Result(data=series, meta=meta)


async def list_commodities_async(*, search: str | None = None) -> Result[list[Commodity]]:
    """List ESR's commodities with their codes, the values commodity_code takes.

    Answered from ``ESRData_GetCommodities`` as packaged with this version
    (``reference/commodities.json``), without an upstream call: 44 commodities when
    packaged, in upstream order, from ``101`` (Wheat - HRW) to ``1702`` (Fresh, Chilled, or
    Frozen Muscle Cuts of Pork), each with the ``unit_id`` ESR reports it in
    (``list_units_of_measure``), e.g. ``104`` Wheat - White, ``401`` Corn, ``801``
    Soybeans (all ``1``, Metric Tons), ``1404`` All Upland Cotton (``2``, Running Bales).
    Names are upstream's, unchanged. ``meta.retrieved_at`` is when the package fetched the
    list (2026-10-28, UTC); ``meta.vintage`` is empty, as upstream gives the list no
    release identifier.

    Args:
        search: Keep the commodities where this text occurs, ignoring case, in the code
            (as digits) or the name, e.g. ``"wheat"`` (101 to 107 and 201 Wheat
            Products), ``"cotton"`` (1201 to 1203 cottonseed and its products, 1301 and
            1401 to 1404 the cottons), ``"104"`` (104 Wheat - White), ``"14"`` (1401 to
            1404, and 1498 and 1499, rough rice: the code matches as text). Omit
            (``None``) for all.
    """
    packaged = PackagedList.load(PACKAGE, "commodities")
    commodities = packaged.parse(Commodity, source=SOURCE)
    selected = [c for c in commodities if matches(search, c.commodity_code, c.commodity_name)]
    return Result(data=selected, meta=packaged.meta(SOURCE, request={"search": search}))


async def list_countries_async(
    *, region_id: int | None = None, search: str | None = None
) -> Result[list[Country]]:
    """List ESR's destination countries with their codes and regions, the values country_code takes.

    Answered from ``ESRData_GetCountries`` as packaged with this version
    (``reference/countries.json``), without an upstream call: 211 countries when
    packaged, in upstream order, each with its ESR region (``list_regions``) and its GENC
    code where upstream has one (50 have none). Codes are ESR's own, not ISO: ``1220``
    CANADA, ``2010`` MEXICO, ``5700`` CHINA, PEOPLES REPUBLIC OF, ``5880`` JAPAN; ``1`` is
    the EUROPEAN UNION - 27 aggregate and ``9990`` UNKNOWN. The names are upstream's,
    padded with spaces, and kept so: ``country_name`` to eight characters
    (``"CANADA  "``), ``country_description`` to 31 (``"CANADA"`` and 25 spaces); only
    ``9990`` and the description of ``1`` are unpadded. ``meta.retrieved_at`` is when the
    package fetched the list (2026-10-28, UTC); ``meta.vintage`` is empty, as upstream
    gives the list no release identifier.

    Args:
        region_id: Keep the countries of this ESR region, an integer as ``list_regions``
            gives it, e.g. ``11`` (WESTERN HEMISPHERE, 40 countries), ``10`` (AFRICA, 58),
            ``9`` (OTHER ASIA AND OCEANIA, 55), ``1`` (EUROPEAN UNION - 27, 27 countries,
            as upstream sends them: the aggregate ``1`` itself, ``4120`` UNITED KINGDOM and
            ``4230`` BELGIUM-LUXEMBOURG as one code besides 24 other members, while ``4791``
            CROATIA sits in ``2`` OTHER EUROPE); ``5`` (JAPAN), ``6`` (TAIWAN), ``7``
            (CHINA) and ``8`` (INDIA) hold one country each. Matched exactly, and checked
            against the packaged regions list first: an id it lacks, e.g. ``12``, raises
            ``InvalidRequestError`` naming the closest ids. Omit (``None``) for every
            region.
        search: Keep the countries where this text occurs, ignoring case, in the code (as
            digits), the name, the description or the GENC code, e.g. ``"united"`` (4120
            UNITED KINGDOM, 5200 UNITED ARAB EMIRATES, 7830 TANZANIA, UNITED REPUBLIC OF),
            ``"korea"`` (5790 and 5800), ``"DEU"`` (4280 GERMANY, by its GENC code),
            ``"1220"`` (CANADA). Omit (``None``) for every country.
    """
    if region_id is not None:
        validate_region_id(region_id)
    packaged = PackagedList.load(PACKAGE, "countries")
    countries = packaged.parse(Country, source=SOURCE)
    selected = [
        c
        for c in countries
        if (region_id is None or c.region_id == region_id)
        and matches(search, c.country_code, c.country_name, c.country_description, c.genc_code)
    ]
    request: dict[str, int | str | None] = {"region_id": region_id, "search": search}
    return Result(data=selected, meta=packaged.meta(SOURCE, request=request))


async def list_regions_async() -> Result[list[Region]]:
    """List ESR's regions with their ids, the values region_id of list_countries takes.

    Answered from ``ESRData_GetRegions`` as packaged with this version
    (``reference/regions.json``), without an upstream call: 12 regions when packaged, in
    upstream order, alphabetical by name: ``10`` AFRICA, ``7`` CHINA, ``3`` EASTERN EUROPE,
    ``1`` EUROPEAN UNION - 27, ``4`` FORMER SOVIET UNION-12, ``8`` INDIA, ``5`` JAPAN,
    ``9`` OTHER ASIA AND OCEANIA, ``2`` OTHER EUROPE, ``6`` TAIWAN, ``99`` UNKNOWN, ``11``
    WESTERN HEMISPHERE. Every one holds at least one country of ``list_countries``.
    ``meta.retrieved_at`` is when the package fetched the list (2026-10-28, UTC);
    ``meta.vintage`` is empty, as upstream gives the list no release identifier. Takes no
    parameters.
    """
    packaged = PackagedList.load(PACKAGE, "regions")
    return Result(data=packaged.parse(Region, source=SOURCE), meta=packaged.meta(SOURCE))


async def list_units_of_measure_async() -> Result[list[UnitOfMeasure]]:
    """List ESR's units of measure with their ids, the unit_id of every commodity and export.

    Answered from ``ESRData_GetUnitsOfMeasure`` as packaged with this version
    (``reference/unitsOfMeasure.json``), without an upstream call: 5 units when packaged,
    in upstream order: ``1`` Metric Tons (grains, oilseeds and their products, rice, beef
    and pork), ``2`` Running Bales (the cottons, 1301 to 1404), ``3`` Pieces (whole hides
    and skins, 1601 to 1603), ``4`` NUMBER (1604, 1606, 1607) and ``5`` Pounds (1605,
    1608). The name field is plural upstream, ``unit_names``, and stays so; the names are
    upstream's, unchanged. ``enums.UnitId`` names the same ids. ``meta.retrieved_at`` is
    when the package fetched the list (2026-10-28, UTC); ``meta.vintage`` is empty, as
    upstream gives the list no release identifier. Takes no parameters.
    """
    packaged = PackagedList.load(PACKAGE, "unitsOfMeasure")
    return Result(data=packaged.parse(UnitOfMeasure, source=SOURCE), meta=packaged.meta(SOURCE))


get_exports = sync(get_exports_async)
get_release_dates = sync(get_release_dates_async)
get_weekly_series = sync(get_weekly_series_async)
list_commodities = sync(list_commodities_async)
list_countries = sync(list_countries_async)
list_regions = sync(list_regions_async)
list_units_of_measure = sync(list_units_of_measure_async)
