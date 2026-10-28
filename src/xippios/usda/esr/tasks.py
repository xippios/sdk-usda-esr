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
``get_release_dates`` is the way to learn when ESR released the data (Johannes,
2026-10-28, superseding the ruling of 2026-10-26; ADR-0022, rule 2). Its
``meta.published_at`` is the newest ``releaseTimeStamp`` as upstream gives it, naive,
with ``meta.published_at_naive`` set: the snapshot states no time zone for it (the
program page that might say Eastern answers 403 to headless clients,
``docs/upstream/FETCHED.md``), and none is invented, since an invented zone could shift
the time by hours in an as-of store. Its ``meta.vintage`` is that record's
``releaseTimeStamp`` text as upstream prints it (``"2026-10-22T08:30:42.67"``), upstream's
release identifier: where the identifier is the timestamp text, ``vintage`` holds the
text and ``published_at`` its parsed value with the flag (conventions §4). Both are
``None`` for an empty answer.

The slices (``get_latest_week``, ``get_top_destinations``, ``get_weekly_series``;
Johannes, 2026-10-25) each make the one request ``get_exports`` makes and only select and
order its records (ADR-0003): no record is changed, nothing is derived, converted, filled
or excluded, and nothing is compared with another source. Their ``meta.endpoint`` is the
operation called, ``meta.request`` carries every parameter (``field`` as its upstream
name), ``meta.vintage`` is the latest ``weekEndingDate`` among the records considered as an
ISO date, ``None`` for an empty answer, and ``meta.published_at`` stays ``None``, as for
``get_exports``.

The ``list_*`` tasks answer from the four lists packaged under ``reference/`` and make no
upstream call (Johannes, 2026-10-25). Core's ``PackagedList`` reads the file and builds
``meta`` (ADR-0022, rule 1): ``meta.endpoint`` is the operation the list was fetched from
(``"ESRData_GetCountries"``), ``meta.retrieved_at`` is when the package fetched the list,
the file's ``fetched`` (a bare date, ``2026-10-25``, reads as 00:00 UTC of that day), and
``meta.vintage`` is ``None``: upstream gives these lists no release identifier, and a
fetch date is not one. ``meta.published_at`` stays ``None``, and so does ``meta.total``,
since upstream reports no count (ADR-0012). The records keep upstream's order, field
names (snake_cased) and values, padding included. Their filters only select records of
the packaged list (ADR-0003), and ``meta.request`` carries those given: ``region_id`` is
named after upstream's ``regionId`` and matches it exactly, ``search`` is the package's
own (the four operations take no parameters), a case-insensitive substring match on
codes, as digits, on names and, for countries, on GENC codes (``xippios.core.matches``).
"""

from xippios.core import (
    InvalidRequestError,
    PackagedList,
    Result,
    ResultCap,
    ResultMeta,
    matches,
    sync,
)

from xippios.usda.esr import api
from xippios.usda.esr._client import SOURCE
from xippios.usda.esr.errors import NoDataForYear
from xippios.usda.esr.models import (
    Commodity,
    CommodityData,
    Country,
    DataReleaseInfo,
    ExportField,
    Region,
    UnitOfMeasure,
)
from xippios.usda.esr.params import (
    PACKAGE,
    validate_commodity_code,
    validate_country_code,
    validate_market_year,
)

__all__ = [
    "get_exports",
    "get_latest_week",
    "get_release_dates",
    "get_top_destinations",
    "get_weekly_series",
    "list_commodities",
    "list_countries",
    "list_regions",
    "list_units_of_measure",
]

# A task named here is Python-only: no tool, no route; the adapters skip it (ADR-0019 decision 4).
BULK_TASKS: frozenset[str] = frozenset()

MCP_CAPS = {
    "get_exports": ResultCap(
        note="pass country_code, e.g. 1220 (Canada), for one destination's weeks, up to 54 rows"
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
"""MCP result caps of their own, by task function name (conventions §8, ADR-0016).

``get_exports`` keeps the family's bounds, 200 rows or 64 KB, with a note of its own: a
tool with filters names them in its cap's note (§8; Johannes, 2026-10-25). Every country
at once is one row per destination and week (cottonseed 2024: 498 rows for 11
destinations), and ``country_code`` narrows it to one destination's weeks, up to 54 rows
(wheat white to Canada 2024). ``get_release_dates``, 44 rows, keeps the default.

The slices have no entry and keep the family's bounds (§8; ADR-0016): none returns more
than one market year of one destination or one week of every destination.
``get_weekly_series`` is one destination's weeks, 54 rows in the largest recorded answer;
``get_latest_week`` one row per destination, 11 for cottonseed 2024 and for wheat HRW
2024 at most 28, the destinations of its whole answer as measured (1,136 rows for 28);
``get_top_destinations`` at most ``n`` of those. Their parameters choose the one request
and the order, and none is an optional filter that narrows a cut answer, so a note would
have nothing to name (§8); ``n`` bounds the rows already.

``list_countries`` is a reference list an agent needs whole to find codes (ADR-0016;
Johannes, 2026-10-25): 211 countries when packaged, past the default of 200 rows, so its
cap is 250 rows; the whole list is 28,936 bytes of compact JSON over MCP as packaged,
within the default 64 KB, which it keeps. Its note names its filters, ``region_id`` and
``search`` (§8). ``list_commodities``, 44 rows, fits the default and keeps the family's bounds, but
it has a filter, so its entry carries a note naming ``search`` and nothing else.
``list_regions`` (12 rows) and ``list_units_of_measure`` (5) have no filter and no entry.
"""


def _vintage(records: list[CommodityData]) -> str | None:
    """The latest ``weekEndingDate`` across ``records`` as an ISO date; ``None`` if empty."""
    if not records:
        return None
    return max(record.week_ending_date for record in records).isoformat()


def _newest_release(releases: list[DataReleaseInfo]) -> DataReleaseInfo | None:
    """The record with the latest ``releaseTimeStamp``, the first of equals; ``None`` if empty."""
    return max(releases, key=lambda release: release.release_time_stamp, default=None)


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
    when ESR released the data. Every country at once is one row per destination and week
    (cottonseed 2024: 498 rows for 11 destinations; wheat HRW 2024: 1,136 rows for 28);
    one country is up to 54 rows.

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
    sends it, without a time zone, since the documentation names none: so
    ``meta.published_at`` is the latest release time stamp as given, naive, with
    ``meta.published_at_naive`` true, and ``meta.vintage`` is its text as ESR prints it,
    ESR's release identifier (``"2026-10-22T08:30:42.67"``). Takes no parameters: the
    endpoint takes none.
    """
    releases = await api.ESRData_GetDataReleaseInfo()
    newest = _newest_release(releases)
    published_at = None if newest is None else newest.release_time_stamp
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetDataReleaseInfo",
        published_at=published_at,
        published_at_naive=published_at is not None,
        vintage=None if newest is None else newest.release_time_stamp_text,
        request={},
    )
    return Result(data=releases, meta=meta)


_FIELD_ATTRIBUTES: dict[str, str] = {
    info.validation_alias: name
    for name, info in CommodityData.model_fields.items()
    if isinstance(info.validation_alias, str)
}
"""``CommodityData``'s attribute for each upstream field name, read once from the model's
fields: ``"outstandingSales"`` is ``outstanding_sales``. ``get_top_destinations`` sorts by
the attribute that carries its ``ExportField``'s value."""


def _export_field(field: object) -> ExportField:
    """``field`` as an ``ExportField``; ``InvalidRequestError`` naming the eight otherwise."""
    if isinstance(field, str):  # an ExportField is a str too
        try:
            return ExportField(field)
        except ValueError:
            pass
    values = ", ".join(member.value for member in ExportField)
    # The attribute name ("outstanding_sales") or upstream's in another case ("outstandingsales").
    by_name = {member.name.casefold(): member for member in ExportField}
    by_name |= {member.value.casefold(): member for member in ExportField}
    named = by_name.get(field.casefold()) if isinstance(field, str) else None
    hint = (
        f" Pass {named.value!r}, upstream's name for the rows' {named.name.lower()}."
        if named
        else ""
    )
    raise InvalidRequestError(
        f"field must be one of upstream's names of the eight quantities, {values}; got "
        f"{field!r}.{hint}",
        source=SOURCE,
    )


async def _every_destination(commodity_code: int, market_year: int) -> list[CommodityData]:
    """``ESRData_GetAllCountriesData``'s records; ESR's empty 404 raised again, naming the ask."""
    try:
        return await api.ESRData_GetAllCountriesData(commodity_code, market_year)
    except NoDataForYear as exc:
        raise _absent(exc, commodity_code, "every country", market_year) from exc


def _latest_week(records: list[CommodityData]) -> list[CommodityData]:
    """The records whose ``weekEndingDate`` is the newest in ``records``, in their order; pure.

    An empty list gives an empty list.
    """
    newest = max((record.week_ending_date for record in records), default=None)
    return [record for record in records if record.week_ending_date == newest]


async def get_latest_week_async(
    commodity_code: int, market_year: int
) -> Result[list[CommodityData]]:
    """The newest week of US export sales of a commodity in a market year, one row per destination.

    One request to ``ESRData_GetAllCountriesData``, the call ``get_exports`` makes without
    a country; of its records, one per destination and week, those whose
    ``week_ending_date`` is the newest in the answer are kept, unchanged and in upstream's
    order (by destination code in the recorded answer). Cottonseed 2024 as recorded: 11
    destinations in the week ending 2024-08-01, of 498 records over 53 weeks; wheat HRW
    2024 at most 28, the destinations of its whole answer as measured (1,136 records for
    28). A destination ESR sends no record for in that week is not in the list. Nothing is
    excluded: ``9990`` (UNKNOWN in ``list_countries``) is a row like any country when ESR
    sends one; ``list_countries`` names every code. Quantities are in the unit ``unit_id``
    names (``enums.UnitId``). ``meta.vintage`` is that week's ending date
    (``"2024-08-01"``); ``meta.published_at`` stays empty, ``get_release_dates`` tells when
    ESR released the data. Codes and the year are checked before the call, as for
    ``get_exports``. Valid codes without exports (rye 2024) give an empty list and an empty
    ``meta.vintage``; a market year ESR holds no data for (1900) raises ``NotFoundError``.

    Args:
        commodity_code: ESR commodity code, an integer, e.g. ``801`` (Soybeans), ``101``
            (Wheat - HRW), ``401`` (Corn), ``1201`` (Cottonseed); ``list_commodities``
            lists them.
        market_year: ESR market year, named by its end year, e.g. ``2024`` (for soybeans
            September 2023 to August 2024, for cottonseed August 2023 to July 2024);
            ``get_release_dates`` names each commodity's current one.
    """
    validate_commodity_code(commodity_code)
    validate_market_year(market_year)
    request: dict[str, int] = {"commodity_code": commodity_code, "market_year": market_year}
    week = _latest_week(await _every_destination(commodity_code, market_year))
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetAllCountriesData",
        vintage=_vintage(week),
        request=request,
    )
    return Result(data=week, meta=meta)


async def get_top_destinations_async(
    commodity_code: int, market_year: int, field: ExportField, n: int = 10
) -> Result[list[CommodityData]]:
    """The top n destinations by one quantity in the newest week of a commodity's market year.

    One request to ``ESRData_GetAllCountriesData``; the records of the newest week in the
    answer (what ``get_latest_week`` returns) are sorted by ``field``, largest first, and
    the first ``n`` kept, each exactly as upstream sent it. Equal values keep upstream's
    order (by destination code in the recorded answer); net sales can be negative and then
    rank last. Values are compared as sent, in the commodity's unit (``unit_id``).
    Cottonseed 2024 by ``"outstandingSales"`` as recorded: 5800 KOREA, REPUBLIC OF
    (17,092), 5880 JAPAN (4,223), 5230 OMAN (939), 1220 CANADA (31), then seven
    destinations at 0 in upstream's order. Nothing is excluded: ``9990`` (UNKNOWN in
    ``list_countries``) ranks alongside countries when ESR sends it; check codes with
    ``list_countries`` if only countries should count. ``meta.vintage`` is the week ranked
    (``"2024-08-01"``); ``meta.published_at`` stays empty. Codes, the year, ``field`` and
    ``n`` are checked before the call. Valid codes without exports (rye 2024) give an empty
    list; a market year ESR holds no data for (1900) raises ``NotFoundError``.

    Args:
        commodity_code: ESR commodity code, an integer, e.g. ``801`` (Soybeans), ``101``
            (Wheat - HRW), ``401`` (Corn), ``1201`` (Cottonseed); ``list_commodities``
            lists them.
        market_year: ESR market year, named by its end year, e.g. ``2024`` (for soybeans
            September 2023 to August 2024).
        field: The quantity to rank by, upstream's field name (``models.ExportField``):
            ``"outstandingSales"`` (the rows' ``outstanding_sales``),
            ``"accumulatedExports"``, ``"weeklyExports"``, ``"grossNewSales"``,
            ``"currentMYNetSales"``, ``"currentMYTotalCommitment"``,
            ``"nextMYOutstandingSales"``, ``"nextMYNetSales"``.
        n: How many destinations to keep, a whole number of at least 1, e.g. ``5``, ``10``
            (the default); more than the destinations in the week returns them all.
    """
    validate_commodity_code(commodity_code)
    validate_market_year(market_year)
    field = _export_field(field)
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise InvalidRequestError(
            f"n must be a whole number of at least 1, such as 5 or 10, got {n!r}.",
            source=SOURCE,
        )
    request: dict[str, int | str] = {
        "commodity_code": commodity_code,
        "market_year": market_year,
        "field": field.value,
        "n": n,
    }
    week = _latest_week(await _every_destination(commodity_code, market_year))
    attribute = _FIELD_ATTRIBUTES[field.value]
    ranked = sorted(
        week,
        key=lambda record: getattr(record, attribute),
        reverse=True,  # sorted() stays stable with reverse=True: ties keep upstream order
    )
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetAllCountriesData",
        vintage=_vintage(week),
        request=request,
    )
    return Result(data=ranked[:n], meta=meta)


async def get_weekly_series_async(
    commodity_code: int, country_code: int, market_year: int
) -> Result[list[CommodityData]]:
    """One destination's weekly US export sales of a commodity in a market year, oldest first.

    One request to ``ESRData_GetCountryData``, the call ``get_exports`` makes with a
    country; its records, one per week, are ordered by ``week_ending_date`` ascending and
    otherwise unchanged. Upstream already sends them in that order in the recorded answer
    (wheat white to Canada 2024: 54 weeks, 2023-06-01 to 2024-06-06), so the sort changes
    nothing there and keeps the order should upstream's change. Nothing is filled: a week
    ESR sends no record for is absent. ``9990`` (UNKNOWN in ``list_countries``) is a
    destination code like any other. Quantities are in the unit ``unit_id`` names
    (``enums.UnitId``). ``meta.vintage`` is the last week's ending date (``"2024-06-06"``);
    ``meta.published_at`` stays empty, ``get_release_dates`` tells when ESR released the
    data. Codes and the year are checked before the call; an empty list means ESR has no
    records for that combination, and a market year ESR holds no data for (1900) raises
    ``NotFoundError``.

    Args:
        commodity_code: ESR commodity code, an integer, e.g. ``104`` (Wheat - White),
            ``101`` (Wheat - HRW), ``801`` (Soybeans), ``1404`` (All Upland Cotton).
        country_code: ESR destination country code (not ISO), an integer, e.g. ``1220``
            (Canada), ``2010`` (Mexico), ``5880`` (Japan); ``list_countries`` lists them.
        market_year: ESR market year, named by its end year, e.g. ``2024`` (for wheat
            June 2023 to May 2024).
    """
    validate_commodity_code(commodity_code)
    validate_country_code(country_code)
    validate_market_year(market_year)
    request: dict[str, int] = {
        "commodity_code": commodity_code,
        "country_code": country_code,
        "market_year": market_year,
    }
    try:
        records = await api.ESRData_GetCountryData(commodity_code, country_code, market_year)
    except NoDataForYear as exc:
        raise _absent(exc, commodity_code, f"country {country_code}", market_year) from exc
    series = sorted(records, key=lambda record: record.week_ending_date)
    meta = ResultMeta(
        source=SOURCE,
        endpoint="ESRData_GetCountryData",
        vintage=_vintage(series),
        request=request,
    )
    return Result(data=series, meta=meta)


async def list_commodities_async(search: str | None = None) -> Result[list[Commodity]]:
    """List ESR's commodities with their codes, the values commodity_code takes.

    Answered from ``ESRData_GetCommodities`` as packaged with this version
    (``reference/commodities.json``), without an upstream call: 44 commodities when
    packaged, in upstream order, from ``101`` (Wheat - HRW) to ``1702`` (Fresh, Chilled, or
    Frozen Muscle Cuts of Pork), each with the ``unit_id`` ESR reports it in
    (``list_units_of_measure``), e.g. ``104`` Wheat - White, ``401`` Corn, ``801``
    Soybeans (all ``1``, Metric Tons), ``1404`` All Upland Cotton (``2``, Running Bales).
    Names are upstream's, unchanged. ``meta.retrieved_at`` is when the package fetched the
    list (2026-10-25, UTC); ``meta.vintage`` is empty, as upstream gives the list no
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
    region_id: int | None = None, search: str | None = None
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
    package fetched the list (2026-10-25, UTC); ``meta.vintage`` is empty, as upstream
    gives the list no release identifier.

    Args:
        region_id: Keep the countries of this ESR region, an integer as ``list_regions``
            gives it, e.g. ``11`` (WESTERN HEMISPHERE, 40 countries), ``10`` (AFRICA, 58),
            ``9`` (OTHER ASIA AND OCEANIA, 55), ``1`` (EUROPEAN UNION - 27, 27 countries,
            as upstream sends them: the aggregate ``1`` itself, ``4120`` UNITED KINGDOM and
            ``4230`` BELGIUM-LUXEMBOURG as one code besides 24 other members, while ``4791``
            CROATIA sits in ``2`` OTHER EUROPE); ``5`` (JAPAN), ``6`` (TAIWAN), ``7``
            (CHINA) and ``8`` (INDIA) hold one country each. Matched exactly and not
            checked: a region no country carries, e.g. ``12``, yields an empty list. Omit
            (``None``) for every region.
        search: Keep the countries where this text occurs, ignoring case, in the code (as
            digits), the name, the description or the GENC code, e.g. ``"united"`` (4120
            UNITED KINGDOM, 5200 UNITED ARAB EMIRATES, 7830 TANZANIA, UNITED REPUBLIC OF),
            ``"korea"`` (5790 and 5800), ``"DEU"`` (4280 GERMANY, by its GENC code),
            ``"1220"`` (CANADA). Omit (``None``) for every country.
    """
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
    ``meta.retrieved_at`` is when the package fetched the list (2026-10-25, UTC);
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
    when the package fetched the list (2026-10-25, UTC); ``meta.vintage`` is empty, as
    upstream gives the list no release identifier. Takes no parameters.
    """
    packaged = PackagedList.load(PACKAGE, "unitsOfMeasure")
    return Result(data=packaged.parse(UnitOfMeasure, source=SOURCE), meta=packaged.meta(SOURCE))


get_exports = sync(get_exports_async)
get_latest_week = sync(get_latest_week_async)
get_release_dates = sync(get_release_dates_async)
get_top_destinations = sync(get_top_destinations_async)
get_weekly_series = sync(get_weekly_series_async)
list_commodities = sync(list_commodities_async)
list_countries = sync(list_countries_async)
list_regions = sync(list_regions_async)
list_units_of_measure = sync(list_units_of_measure_async)
