"""The wave 2 slices: the latest week, the top destinations, the weekly series.

Each replays a recorded answer and checks that the slice selects and orders upstream's
records without changing one (ADR-0003; Johannes, 2026-10-25). ``_recorded`` parses a
fixture the way the wrapper does, without a request, so a test compares with what
upstream sent while the task's own request is counted on its route. The slices make the
requests ``get_exports`` makes, and its fixtures serve them: ``wheat_white_2027`` carries
a ``9990`` (UNKNOWN) destination, and ``get_all_countries_data/year_1900`` is ESR's empty
404 on the every-country path. ``get_weekly_series`` makes one request per market year, so
its range replays two one-country recordings, ``wheat_white_canada_2023`` (recorded
2026-10-28) and ``wheat_white_canada_2024``, and moves the recorded empty 404 and ``[]``
to a year inside the range (``url=``) rather than writing an answer. A range past the
current calendar year reads the release list first (``get_data_release_info/all``,
recorded 2026-10-25), so those tests pin the calendar year to 2026 (``in_2026``).
"""

import dataclasses
import json
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from xippios.core import InvalidRequestError, NotFoundError, UnknownCode, parse
from xippios.core.mcp import cap_result
from xippios.core.testing import (
    ReplayFixture,
    fixture_path,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_urls,
)

import xippios.usda.esr as package
from xippios.usda.esr import api, models, tasks
from xippios.usda.esr._client import BASE_URL
from xippios.usda.esr.errors import NoDataForYear
from xippios.usda.esr.mcp import server
from xippios.usda.esr.models import CommodityData, DataReleaseInfo, ExportField
from xippios.usda.esr.params import latest_market_year

FIXTURES = Path(__file__).parent / "fixtures"
WHEAT_WHITE, COTTONSEED, RYE = 104, 1201, 501
CANADA = 1220
COUNTRY = "get_country_data"
ALL = "get_all_countries_data"
OPERATIONS = {COUNTRY: "ESRData_GetCountryData", ALL: "ESRData_GetAllCountriesData"}
"""Each wrapper, the name of its fixture directory, to its verbatim ``operationId``, the
``meta.endpoint`` of the slices that call it (conventions §2, §10)."""
EXPORTS = f"{BASE_URL}/api/esr/exports/commodityCode"
SLICES = ["get_latest_week", "get_top_destinations", "get_weekly_series"]


def _country_url(market_year: int, commodity_code: int = 104) -> str:
    """The one-country URL of a commodity, wheat white by default, to Canada."""
    return f"{EXPORTS}/{commodity_code}/countryCode/1220/marketYear/{market_year}"


RELEASES = "get_data_release_info"
RELEASE_DATES = f"{BASE_URL}/api/esr/datareleasedates"


@pytest.fixture
def in_2026(monkeypatch: pytest.MonkeyPatch) -> None:
    """The calendar year pinned to 2026, when ``get_data_release_info/all`` was recorded:
    there wheat white's current market year is 2027 and beef muscle cuts' (1701) 2026."""
    monkeypatch.setattr(tasks, "_calendar_year", lambda: 2026)


def _serve(respx_mock: respx.MockRouter, answers: dict[str, tuple[str, str]]) -> respx.Route:
    """One route for every URL in ``answers``, each served the recorded answer of its
    ``(wrapper, case)``, moved where the URL is another, so ``sent_urls(route)`` shows the
    order of the requests across both operations."""
    recorded = {
        url: load_fixture(fixture_path(FIXTURES, wrapper, case)).response
        for url, (wrapper, case) in answers.items()
    }

    def answer(request: httpx.Request) -> httpx.Response:
        found = recorded[str(request.url)]
        return httpx.Response(found.status, headers=found.headers, content=found.content)

    pattern = "|".join(re.escape(url) for url in recorded)
    return respx_mock.get(url__regex=f"^(?:{pattern})$").mock(side_effect=answer)


BOUNDARY = date(2023, 6, 1)
"""The week ending 2023-06-01: the last of ``wheat_white_canada_2023`` (53 weeks from
2022-06-02) and the first of ``wheat_white_canada_2024`` (54 weeks to 2024-06-06), with
other values in each: the week straddles wheat's market years, which end in May."""

LATEST = date(2024, 8, 1)
"""The newest week of ``cottonseed_2024``, whose 498 records span 53 weeks from 2023-08-03."""

LATEST_DESTINATIONS = [1220, 2010, 5170, 5180, 5230, 5520, 5700, 5800, 5830, 5880, 7140]
"""The 11 destinations of that week, in upstream's order: by code."""

UNKNOWN = 9990
"""``countryCode`` 9990, UNKNOWN in the packaged countries list (region 99, UNKNOWN)."""

WHEAT_WHITE_2027_LATEST = [
    1220, 2010, 2050, 2250, 3310, 3370, 4910, 5380, 5420, 5460, 5490,
    5520, 5570, 5590, 5600, 5650, 5800, 5820, 5830, 5880, 7530, UNKNOWN,
]  # fmt: skip
"""The 22 destinations of the newest week of ``wheat_white_2027`` (2026-10-15), by code,
``9990`` last, as upstream sends them; its 385 records span 20 weeks from 2026-06-04."""


def _recorded(wrapper: str, case: str) -> list[CommodityData]:
    """The recorded answer parsed as the wrapper parses it, without a request."""
    body = json.loads(load_fixture(fixture_path(FIXTURES, wrapper, case)).response.body)
    return parse(list[CommodityData], body, source="usda-esr", endpoint=OPERATIONS[wrapper])


def _latest_week_recorded() -> list[CommodityData]:
    return [r for r in _recorded(ALL, "cottonseed_2024") if r.week_ending_date == LATEST]


def test_every_slice_is_exported() -> None:
    for name in SLICES:
        assert name in tasks.__all__
        assert name in package.__all__
        assert getattr(package, name) is getattr(tasks, name)
    for name in ["get_latest_week", "get_top_destinations"]:
        assert name not in tasks.MCP_CAPS, "one week of every destination fits the default"
    assert "ExportField" in models.__all__


@pytest.mark.anyio
async def test_slice_tool_names_and_the_field_schema() -> None:
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert {f"usda_esr_{name}" for name in SLICES} <= set(tools)
    schema = tools["usda_esr_get_top_destinations"].input_schema
    assert schema["properties"]["field"] == {"$ref": "#/$defs/ExportField"}
    assert schema["$defs"]["ExportField"]["enum"] == [member.value for member in ExportField]
    assert schema["required"] == ["commodity_code", "market_year", "field"]
    series = tools["usda_esr_get_weekly_series"].input_schema
    assert series["required"] == ["commodity_code", "country_code", "start_year", "end_year"]
    assert "market_year" not in series["properties"], "0.1.0's parameter is gone"


def test_export_field_values_are_the_records_quantity_aliases() -> None:
    """``ExportField`` and ``CommodityData`` cannot drift: the values are the aliases of the
    record's ``Decimal`` fields, in its order, the member names its attribute names."""
    quantities = {
        name: info
        for name, info in CommodityData.model_fields.items()
        if info.annotation is Decimal
    }
    assert len(quantities) == len(ExportField) == 8
    assert [member.value for member in ExportField] == [
        info.validation_alias for info in quantities.values()
    ]
    assert [member.name for member in ExportField] == [name.upper() for name in quantities]
    assert {member.value: tasks._FIELD_ATTRIBUTES[member.value] for member in ExportField} == {
        member.value: member.name.lower() for member in ExportField
    }, "the attribute each value is sorted by"


# get_latest_week


def test_get_latest_week_is_the_newest_week_of_every_destination(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(ALL, "cottonseed_2024")
    result = tasks.get_latest_week(COTTONSEED, 2024)
    assert sent_urls(route) == [f"{EXPORTS}/1201/allCountries/marketYear/2024"], "one request"
    recorded = _recorded(ALL, "cottonseed_2024")
    assert len(recorded) == 498
    assert max(r.week_ending_date for r in recorded) == LATEST
    assert result.data == _latest_week_recorded(), "unchanged, in upstream's order"
    assert [r.country_code for r in result.data] == LATEST_DESTINATIONS, "one row each"
    assert {r.week_ending_date for r in result.data} == {LATEST}
    assert result.meta.source == "usda-esr"
    assert result.meta.endpoint == OPERATIONS[ALL]
    assert result.meta.request == {"commodity_code": 1201, "market_year": 2024}
    assert result.meta.vintage == "2024-08-01", "the week itself"
    assert result.meta.published_at is None
    assert result.meta.total is None


def test_latest_week_of_nothing_is_nothing() -> None:
    """Pure: the newest week of no records is no records."""
    assert tasks._latest_week([]) == []


# get_top_destinations


def test_top_destinations_by_outstanding_sales_ties_keep_upstream_order(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(ALL, "cottonseed_2024")
    top = tasks.get_top_destinations(COTTONSEED, 2024, ExportField.OUTSTANDING_SALES, 5)
    assert route.call_count == 1
    assert [(r.country_code, r.outstanding_sales) for r in top.data] == [
        (5800, Decimal(17092)),
        (5880, Decimal(4223)),
        (5230, Decimal(939)),
        (1220, Decimal(31)),
        (2010, Decimal(0)),  # the first of seven at 0, in upstream's order
    ]
    week = _latest_week_recorded()
    assert all(record in week for record in top.data), "records as upstream sent them"
    assert top.meta.endpoint == OPERATIONS[ALL]
    assert top.meta.request == {
        "commodity_code": 1201,
        "market_year": 2024,
        "field": "outstandingSales",
        "n": 5,
    }
    assert type(top.meta.request["field"]) is str, "the upstream value, not the member"
    assert top.meta.vintage == "2024-08-01"
    assert top.meta.published_at is None
    assert top.meta.total is None

    every = tasks.get_top_destinations(COTTONSEED, 2024, ExportField.OUTSTANDING_SALES, 20)
    assert len(every.data) == 11, "n above the destinations of the week returns them all"
    zeros = [r for r in every.data if r.outstanding_sales == 0]
    assert [r.country_code for r in zeros] == [2010, 5170, 5180, 5520, 5700, 5830, 7140]
    assert zeros == [r for r in week if r.outstanding_sales == 0], "ties keep upstream order"
    assert every.data[-7:] == zeros
    assert every.meta.vintage == "2024-08-01"


def test_top_destinations_by_accumulated_exports(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(ALL, "cottonseed_2024")
    top = tasks.get_top_destinations(COTTONSEED, 2024, ExportField.ACCUMULATED_EXPORTS, 3)
    assert [(r.country_code, r.accumulated_exports) for r in top.data] == [
        (5800, Decimal(121478)),
        (5880, Decimal(70388)),
        (2010, Decimal(20355)),
    ]
    default = tasks.get_top_destinations(COTTONSEED, 2024, ExportField.ACCUMULATED_EXPORTS)
    assert default.meta.request["n"] == 10
    assert [r.country_code for r in default.data] == [
        5800, 5880, 2010, 5170, 7140, 5700, 5180, 5520, 1220, 5830
    ], "the eleventh, 5230 OMAN at 0, is left out"  # fmt: skip
    every = tasks.get_top_destinations(COTTONSEED, 2024, ExportField.ACCUMULATED_EXPORTS, 11)
    values = [r.accumulated_exports for r in every.data]
    assert values == sorted(values, reverse=True)
    assert every.data[-1].country_code == 5230
    by_name = tasks.get_top_destinations(COTTONSEED, 2024, "accumulatedExports", 3)  # type: ignore[arg-type]
    assert by_name.data == top.data, "upstream's name as a plain string is the member"
    assert by_name.meta.request["field"] == "accumulatedExports"
    assert route.call_count == 4


# get_weekly_series


def test_get_weekly_series_spans_market_years_oldest_first(
    replay_fixture: ReplayFixture,
) -> None:
    """2023 to 2024: one request per market year, oldest first, and the two recordings'
    rows put together by week, each unchanged; the week both carry keeps 2023's row first."""
    older = replay_fixture(COUNTRY, "wheat_white_canada_2023")
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert sent_urls(older) == [_country_url(2023)]
    assert sent_urls(newer) == [_country_url(2024)]
    recorded_2023 = _recorded(COUNTRY, "wheat_white_canada_2023")
    recorded_2024 = _recorded(COUNTRY, "wheat_white_canada_2024")
    assert (len(recorded_2023), len(recorded_2024)) == (53, 54)
    assert len(result.data) == 53 + 54, "every row of both years, nothing dropped or filled"
    assert result.data == recorded_2023 + recorded_2024, "2023's rows, then 2024's, unchanged"
    weeks = [r.week_ending_date for r in result.data]
    assert weeks == sorted(weeks), "ascending by week_ending_date"
    assert (weeks[0], weeks[-1]) == (date(2022, 6, 2), date(2024, 6, 6))
    assert recorded_2023[-1].week_ending_date == BOUNDARY == recorded_2024[0].week_ending_date
    twice = [r for r in result.data if r.week_ending_date == BOUNDARY]
    assert twice == [recorded_2023[-1], recorded_2024[0]], "once per market year, older first"
    assert [r.accumulated_exports for r in twice] == [Decimal(11060), Decimal(0)]
    assert result.meta.source == "usda-esr"
    assert result.meta.endpoint == OPERATIONS[COUNTRY]
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2023,
        "end_year": 2024,
    }
    assert result.meta.vintage == "2024-06-06", "the last week"
    assert result.meta.published_at is None
    assert result.meta.total is None


def test_the_requests_go_out_oldest_first(respx_mock: respx.MockRouter) -> None:
    """One route for every year's URL, so ``sent_urls`` shows the order the requests went
    out in; it serves the two recorded answers in turn, as recorded."""
    answers = [
        load_fixture(fixture_path(FIXTURES, COUNTRY, f"wheat_white_canada_{year}")).response
        for year in (2023, 2024)
    ]
    every_year = re.escape(f"{EXPORTS}/104/countryCode/1220/marketYear/") + r"\d{4}$"
    route = respx_mock.get(url__regex=every_year)
    route.mock(
        side_effect=[
            httpx.Response(a.status, headers=a.headers, content=a.content) for a in answers
        ]
    )
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert sent_urls(route) == [_country_url(2023), _country_url(2024)], "oldest first"
    assert len(result.data) == 53 + 54


def test_a_weekly_series_of_one_market_year_is_its_weeks(
    replay_fixture: ReplayFixture,
) -> None:
    """2024 to 2024, a range of one: one request, the 54 weeks 0.1.0 answered for 2024."""
    route = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2024)
    assert sent_urls(route) == [_country_url(2024)], "one request"
    recorded = _recorded(COUNTRY, "wheat_white_canada_2024")
    weeks = [r.week_ending_date for r in recorded]
    assert weeks == sorted(weeks), "upstream already sends them oldest first"
    assert len(set(weeks)) == len(weeks) == 54
    assert result.data == recorded, "so the order is upstream's and nothing changed"
    assert (result.data[0].week_ending_date, result.data[-1].week_ending_date) == (
        date(2023, 6, 1),
        date(2024, 6, 6),
    )
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2024,
        "end_year": 2024,
    }
    assert result.meta.vintage == "2024-06-06"
    assert result.meta.published_at is None


def test_weekly_series_orders_what_upstream_sends_out_of_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded records, reversed in memory (a function input, not a fixture file): the
    slice orders them by week, oldest first, and changes none; across two market years
    the week both carry keeps the older year's row first, whatever upstream's order."""
    answers = {
        2023: _recorded(COUNTRY, "wheat_white_canada_2023"),
        2024: _recorded(COUNTRY, "wheat_white_canada_2024"),
    }

    async def reversed_answer(_: int, __: int, market_year: int) -> list[CommodityData]:
        return answers[market_year][::-1]

    monkeypatch.setattr(api, "get_country_data", reversed_answer)
    one = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2024)
    assert one.data == answers[2024]
    assert one.meta.vintage == "2024-06-06"
    both = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert both.data == answers[2023] + answers[2024]


# empty answers, absent market years, the gateway's 404


def test_valid_codes_without_exports_are_an_empty_result(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Recorded: rye for market year 2024 answers 200 with ``[]``. Empty means empty."""
    route = replay_fixture(ALL, "rye_2024")
    latest = tasks.get_latest_week(RYE, 2024)
    top = tasks.get_top_destinations(RYE, 2024, ExportField.WEEKLY_EXPORTS)
    assert latest.data == [] == top.data
    assert (latest.meta.vintage, latest.meta.published_at) == (None, None)
    assert (top.meta.vintage, top.meta.published_at) == (None, None)
    assert latest.meta.request == {"commodity_code": 501, "market_year": 2024}
    assert top.meta.request == {
        "commodity_code": 501,
        "market_year": 2024,
        "field": "weeklyExports",
        "n": 10,
    }
    assert route.call_count == 2


def test_an_empty_weekly_series_is_an_empty_result(replay_fixture: ReplayFixture) -> None:
    """ESR's ``[]`` for one destination: the recorded body of ``year_2099`` (HTTP 200,
    ``[]``) served at a valid year's URL (``url=``), moved, not written. Nothing is
    filled, and an empty answer has no vintage."""
    route = replay_fixture(COUNTRY, "year_2099", url=_country_url(2025))
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2025, 2025)
    assert sent_urls(route) == [_country_url(2025)]
    assert result.data == []
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2025,
        "end_year": 2025,
    }
    assert result.meta.endpoint == OPERATIONS[COUNTRY]


@pytest.mark.usefixtures("in_2026")
def test_a_released_year_without_exports_adds_no_rows(replay_fixture: ReplayFixture) -> None:
    """``year_2099``'s recorded ``[]`` at the 2023 URL. In 2026 market year 2023 is long
    released, so its ``[]`` is a year without exports to Canada, as rye 2024's is for every
    country (``rye_2024``): it adds no rows, 2024's come alone, and the range, ending
    before the calendar year, reads no release list."""
    releases = replay_fixture(RELEASES, "all")
    empty = replay_fixture(COUNTRY, "year_2099", url=_country_url(2023))
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert (empty.call_count, newer.call_count) == (1, 1)
    assert sent_urls(releases) == []
    assert result.data == _recorded(COUNTRY, "wheat_white_canada_2024")
    assert result.meta.vintage == "2024-06-06"


# a range past the current calendar year: the release list first


@pytest.mark.usefixtures("in_2026")
def test_a_range_into_next_year_reads_the_release_list_first(
    respx_mock: respx.MockRouter,
) -> None:
    """2024 to 2027 in 2026: the release list (wheat white's current market year 2027),
    then the four yearly requests, oldest first. 2025 to 2027 were not recorded for this
    pair: ``year_2099``'s recorded ``[]`` is moved to their URLs; the order is the point."""
    route = _serve(
        respx_mock,
        {
            RELEASE_DATES: (RELEASES, "all"),
            _country_url(2024): (COUNTRY, "wheat_white_canada_2024"),
            **{_country_url(year): (COUNTRY, "year_2099") for year in (2025, 2026, 2027)},
        },
    )
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2027)
    assert sent_urls(route) == [
        RELEASE_DATES,
        _country_url(2024),
        _country_url(2025),
        _country_url(2026),
        _country_url(2027),
    ], "one request more, first"
    assert result.data == _recorded(COUNTRY, "wheat_white_canada_2024")
    assert result.meta.endpoint == OPERATIONS[COUNTRY], "the records' operation"
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2024,
        "end_year": 2027,
    }
    assert result.meta.vintage == "2024-06-06"
    assert result.meta.published_at is None


@pytest.mark.usefixtures("in_2026")
def test_a_range_ending_this_year_or_before_reads_no_release_list(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """2024 to 2026 in 2026, and 2023 to 2024: every market year named by them has begun,
    so only the yearly requests go out (``year_2099``'s ``[]`` moved to 2025 and 2026)."""
    releases = replay_fixture(RELEASES, "all")
    route = _serve(
        respx_mock,
        {
            _country_url(2023): (COUNTRY, "wheat_white_canada_2023"),
            _country_url(2024): (COUNTRY, "wheat_white_canada_2024"),
            _country_url(2025): (COUNTRY, "year_2099"),
            _country_url(2026): (COUNTRY, "year_2099"),
        },
    )
    this_year = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2026)
    assert sent_urls(route) == [_country_url(2024), _country_url(2025), _country_url(2026)]
    assert this_year.data == _recorded(COUNTRY, "wheat_white_canada_2024")
    historical = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert len(historical.data) == 53 + 54
    assert sent_urls(releases) == [], "no release list for either range"


RANGE_REFUSED = (
    "ESR has not released market year 2028 of commodity 104 yet: its latest released market "
    "year is 2027, the current one in ESR's release list (ESRData_GetDataReleaseInfo). ESR "
    "answers a market year it has not released with an empty list, the same answer as a year "
    "without exports, so the range 2024 to 2028 is refused rather than returned without it; "
    "ask for market years up to 2027."
)
"""Probed 2026-10-28, one keyed call, not kept: wheat white to Canada, market year 2028,
answered HTTP 200 with ``[]``, the answer of a released year without exports."""


@pytest.mark.usefixtures("in_2026")
def test_a_range_past_the_current_market_year_is_refused(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """2024 to 2028 in 2026: 2028 is after wheat white's current market year, 2027, so the
    whole range is refused naming 2027 (conventions §4; ADR-0022, amendment points 6 and
    7), after the one release-list request and before any yearly one, nothing partial."""
    releases = replay_fixture(RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2028)
    assert str(info.value) == RANGE_REFUSED
    assert not isinstance(info.value, (InvalidRequestError, NoDataForYear))
    assert sent_urls(releases) == [RELEASE_DATES]
    assert len(respx_mock.calls) == 1, "no yearly request"
    with pytest.raises(NotFoundError, match="its latest released market year is 2027"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2028, 2028)


@pytest.mark.usefixtures("in_2026")
def test_a_calendar_year_commodity_is_refused_past_this_year(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """Beef muscle cuts (1701) run the calendar year: on the recorded list their current
    market year is 2026, so 2025 to 2027 is refused naming 2026."""
    releases = replay_fixture(RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(1701, CANADA, 2025, 2027)
    assert str(info.value).startswith(
        "ESR has not released market year 2027 of commodity 1701 yet: its latest released "
        "market year is 2026, "
    )
    assert "ask for market years up to 2026." in str(info.value)
    assert sent_urls(releases) == [RELEASE_DATES]
    assert len(respx_mock.calls) == 1


@pytest.mark.usefixtures("in_2026")
def test_a_commodity_the_release_list_lacks_refuses_a_range_into_next_year(
    monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    """The recorded release list without wheat white, in memory (a function input, not a
    fixture file): ``get_market_year``'s refusal, before any yearly request."""
    body = json.loads(load_fixture(fixture_path(FIXTURES, RELEASES, "all")).response.body)
    recorded = parse(
        list[DataReleaseInfo], body, source="usda-esr", endpoint="ESRData_GetDataReleaseInfo"
    )

    async def without_wheat_white() -> list[DataReleaseInfo]:
        return [r for r in recorded if r.commodity_code != WHEAT_WHITE]

    monkeypatch.setattr(api, "get_data_release_info", without_wheat_white)
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2027)
    assert str(info.value) == (
        "ESR lists no market year for commodity 104: GET /api/esr/datareleasedates "
        "(ESRData_GetDataReleaseInfo) answered without a record for it, although the packaged "
        "commodities list names it."
    )
    assert not respx_mock.calls, "no yearly request"


def test_a_market_year_esr_lacks_inside_the_range_is_skipped(
    replay_fixture: ReplayFixture,
) -> None:
    """``year_1900``'s recorded empty 404 (``text/plain``) at the 2023 URL: the year adds no
    rows, no error is raised, and the series goes on with 2024 (conventions §4, as
    sdk-usda-psd's ``get_time_series`` skips PSD's empty 404)."""
    absent = load_fixture(fixture_path(FIXTURES, COUNTRY, "year_1900"))
    assert (absent.response.status, absent.response.content) == (404, b"")
    missing = replay_fixture(COUNTRY, "year_1900", url=_country_url(2023))
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert (missing.call_count, newer.call_count) == (1, 1)
    assert result.data == _recorded(COUNTRY, "wheat_white_canada_2024")
    assert result.meta.vintage == "2024-06-06"
    assert result.meta.request["start_year"] == 2023


def test_a_range_esr_lacks_entirely_is_an_empty_list(replay_fixture: ReplayFixture) -> None:
    """Every year answers the empty 404: an empty list without a vintage, not an error.
    Market year 1900 as a range of one is the recorded answer itself, where 0.1.0 raised
    ``NoDataForYear``; 2023 to 2024 serves it at both URLs."""
    route = replay_fixture(COUNTRY, "year_1900")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 1900, 1900)
    assert sent_urls(route) == [_country_url(1900)]
    assert result.data == []
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 1900,
        "end_year": 1900,
    }
    first = replay_fixture(COUNTRY, "year_1900", url=_country_url(2023))
    second = replay_fixture(COUNTRY, "year_1900", url=_country_url(2024))
    both = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert (first.call_count, second.call_count) == (1, 1)
    assert both.data == []
    assert both.meta.vintage is None


def test_get_exports_still_names_a_market_year_esr_lacks(replay_fixture: ReplayFixture) -> None:
    """The single-year task keeps raising for ESR's empty 404; only the series skips it."""
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        tasks.get_exports(WHEAT_WHITE, 1900, CANADA)
    assert str(info.value) == (
        "ESR has no data for commodity 104, country 1220, market year 1900: GET "
        "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900 answered HTTP 404 "
        "with an empty body."
    )
    assert route.call_count == 1


def test_the_gateways_not_found_inside_the_range_stops_the_series(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """NOT RECORDED: the gateway's documented ``NOT_FOUND`` body at the 2023 URL, as
    ``test_tasks.py`` builds it. It says the request is wrong, not that the year is empty:
    raised, the request for 2024 never sent, nothing partial returned."""
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    gateway = respx_mock.get(_country_url(2023)).mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "NOT_FOUND", "message": "The requested URL was not found."}},
        )
    )
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert not isinstance(info.value, NoDataForYear)
    assert str(info.value).startswith("api.data.gov has no route for /api/esr/exports/")
    assert (gateway.call_count, newer.call_count) == (1, 0), "nothing after the error"


def test_a_refusal_inside_the_range_stops_the_series(replay_fixture: ReplayFixture) -> None:
    """ESR's recorded HTTP 400 (``not_an_integer``) moved to the 2023 URL: any error but
    the empty 404 is raised, and 2024 is never asked for."""
    later = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    refused = replay_fixture(COUNTRY, "not_an_integer", url=_country_url(2023))
    with pytest.raises(InvalidRequestError, match=r"HTTP 400: The request is invalid\."):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert (refused.call_count, later.call_count) == (1, 0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: tasks.get_latest_week(WHEAT_WHITE, 1900),
        lambda: tasks.get_top_destinations(WHEAT_WHITE, 1900, ExportField.OUTSTANDING_SALES),
    ],
    ids=["get_latest_week", "get_top_destinations"],
)
def test_every_destination_slices_name_a_market_year_esr_lacks(
    replay_fixture: ReplayFixture, call: Callable[[], object]
) -> None:
    """Recorded on the every-country path as on the one-country one (2026-10-28): HTTP 404
    with an empty ``text/plain`` body, so ``classify`` gives ``NoDataForYear`` for both."""
    absent = load_fixture(fixture_path(FIXTURES, ALL, "year_1900"))
    assert (absent.response.status, absent.response.content) == (404, b"")
    headers = dict(absent.response.headers)
    assert headers["content-type"].startswith("text/plain")
    path = "/api/esr/exports/commodityCode/104/allCountries/marketYear/1900"
    route = replay_fixture(ALL, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        call()
    assert info.value.path == path
    assert str(info.value) == (
        f"ESR has no data for commodity 104, every country, market year 1900: GET {path} "
        "answered HTTP 404 with an empty body."
    )
    assert route.call_count == 1


@pytest.mark.parametrize(
    ("path", "call"),
    [
        ("104/allCountries/marketYear/2024", lambda: tasks.get_latest_week(104, 2024)),
        (
            "104/allCountries/marketYear/2024",
            lambda: tasks.get_top_destinations(104, 2024, ExportField.WEEKLY_EXPORTS),
        ),
        (
            "104/countryCode/1220/marketYear/2024",
            lambda: tasks.get_weekly_series(104, 1220, 2024, 2024),
        ),
    ],
    ids=SLICES,
)
def test_the_gateways_not_found_propagates_unchanged(
    respx_mock: respx.MockRouter, path: str, call: Callable[[], object]
) -> None:
    """NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body, as ``test_tasks.py``
    builds it. Only ESR's empty 404 means "no data for this market year"."""
    respx_mock.get(f"{EXPORTS}/{path}").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "NOT_FOUND", "message": "The requested URL was not found."}},
        )
    )
    with pytest.raises(NotFoundError) as info:
        call()
    assert not isinstance(info.value, NoDataForYear)
    assert str(info.value).startswith("api.data.gov has no route for /api/esr/exports/")


# 9990, UNKNOWN: a destination code like any other


def test_the_latest_week_keeps_the_unknown_destination(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(ALL, "wheat_white_2027")
    result = tasks.get_latest_week(WHEAT_WHITE, 2027)
    assert sent_urls(route) == [f"{EXPORTS}/104/allCountries/marketYear/2027"]
    recorded = _recorded(ALL, "wheat_white_2027")
    assert len(recorded) == 385
    assert sum(r.country_code == UNKNOWN for r in recorded) == 20, "one row in every week"
    newest = date(2026, 10, 15)
    assert result.data == [r for r in recorded if r.week_ending_date == newest]
    assert [r.country_code for r in result.data] == WHEAT_WHITE_2027_LATEST
    assert result.meta.vintage == "2026-10-15"


def test_top_destinations_rank_the_unknown_destination_like_a_country(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """No special casing: 9990 ranks by its value, second by outstanding sales in the week
    ending 2026-10-15, first by current market year net sales."""
    route = replay_fixture(ALL, "wheat_white_2027")
    top = tasks.get_top_destinations(WHEAT_WHITE, 2027, ExportField.OUTSTANDING_SALES, 3)
    assert [(r.country_code, r.outstanding_sales) for r in top.data] == [
        (5650, Decimal(346900)),  # PHILIPPINES
        (UNKNOWN, Decimal(156328)),
        (5800, Decimal(152280)),  # KOREA, REPUBLIC OF
    ]
    net = tasks.get_top_destinations(WHEAT_WHITE, 2027, ExportField.CURRENT_MY_NET_SALES, 2)
    assert [(r.country_code, r.current_my_net_sales) for r in net.data] == [
        (UNKNOWN, Decimal(20000)),
        (5590, Decimal(18000)),  # SINGAPORE
    ]
    recorded = _recorded(ALL, "wheat_white_2027")
    assert all(r in recorded for r in [*top.data, *net.data]), "records as upstream sent them"
    assert route.call_count == 2


def test_list_countries_names_the_unknown_destination() -> None:
    (country,) = package.list_countries(search=str(UNKNOWN)).data
    assert (country.country_code, country.country_name, country.region_id) == (
        UNKNOWN,
        "UNKNOWN",
        99,
    )


def test_every_country_of_wheat_white_2027(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    replay_fixture(ALL, "wheat_white_2027")
    result = tasks.get_exports(WHEAT_WHITE, 2027)
    assert len(result.data) == 385
    assert len({r.country_code for r in result.data}) == 22
    assert UNKNOWN in {r.country_code for r in result.data}
    assert result.meta.vintage == "2026-10-15"


# validation, before any request


def test_slices_check_their_arguments_before_any_request(respx_mock: respx.MockRouter) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly."""
    with pytest.raises(UnknownCode, match=r"1001 \(Flaxseed\)"):
        tasks.get_latest_week(999, 2024)
    with pytest.raises(InvalidRequestError, match="answers a future one"):
        tasks.get_latest_week(COTTONSEED, 2099)
    with pytest.raises(InvalidRequestError, match="four-digit year"):
        tasks.get_top_destinations(COTTONSEED, 24, ExportField.OUTSTANDING_SALES)
    with pytest.raises(UnknownCode):
        tasks.get_top_destinations(999, 2024, ExportField.OUTSTANDING_SALES)

    bad_n: list[Any] = [0, -1, True, 2.5, "5"]
    for n in bad_n:
        with pytest.raises(InvalidRequestError, match="n must be a whole number of at least 1"):
            tasks.get_top_destinations(COTTONSEED, 2024, ExportField.OUTSTANDING_SALES, n)
    with pytest.raises(InvalidRequestError, match="field must be one of upstream's") as unknown:
        tasks.get_top_destinations(COTTONSEED, 2024, "exports")  # type: ignore[arg-type]
    assert "weeklyExports, accumulatedExports, outstandingSales, grossNewSales" in str(
        unknown.value
    )
    with pytest.raises(
        InvalidRequestError,
        match="Pass 'outstandingSales', upstream's name for the rows' outstanding_sales",
    ):
        tasks.get_top_destinations(COTTONSEED, 2024, "outstanding_sales")  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError, match="for the rows' current_my_net_sales"):
        tasks.get_top_destinations(COTTONSEED, 2024, "CURRENT_MY_NET_SALES")  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError, match="Pass 'outstandingSales', upstream's name"):
        tasks.get_top_destinations(COTTONSEED, 2024, "outstandingsales")  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError, match="field must be one of upstream's"):
        tasks.get_top_destinations(COTTONSEED, 2024, 3)  # type: ignore[arg-type]

    with pytest.raises(UnknownCode, match=r"9990 \(UNKNOWN\)"):
        tasks.get_weekly_series(WHEAT_WHITE, 9999, 2024, 2024)
    with pytest.raises(UnknownCode, match="commodity_code"):
        tasks.get_weekly_series(999, CANADA, 2024, 2024)
    with pytest.raises(InvalidRequestError, match="must be an integer code"):
        tasks.get_weekly_series(WHEAT_WHITE, "1220", 2024, 2024)  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError, match=r"^start_year must be a four-digit year"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 24, 2024)
    with pytest.raises(InvalidRequestError, match=r"^end_year must be a four-digit year"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 24)
    with pytest.raises(InvalidRequestError, match=r"^market_year must be a four-digit year"):
        tasks.get_exports(WHEAT_WHITE, 24, CANADA)
    assert not respx_mock.calls


def test_the_weekly_series_checks_its_range_before_any_request(
    respx_mock: respx.MockRouter,
) -> None:
    """respx is active with no routes mounted: a backwards range, one over the ceiling and
    a year after ``latest_market_year()`` are refused without a request."""
    with pytest.raises(InvalidRequestError) as backwards:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, 2023)
    assert str(backwards.value) == (
        "start_year 2024 is after end_year 2023: pass the earlier market year first, e.g. "
        "start_year=2022, end_year=2024."
    )
    assert tasks.SERIES_MAX_YEARS == 10
    with pytest.raises(InvalidRequestError) as eleven:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2015, 2025)
    assert str(eleven.value) == (
        "2015 to 2025 is 11 market years, and the weekly series makes one request per market "
        "year; it spans at most 10 market years per call. Narrow the range, e.g. "
        "start_year=2016, end_year=2025, or split it into calls of at most 10."
    )
    future = latest_market_year() + 1
    with pytest.raises(InvalidRequestError, match="answers a future one") as end:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024, future)
    assert str(end.value).startswith(f"end_year must be no later than {future - 1}, ")
    with pytest.raises(InvalidRequestError, match="answers a future one") as start:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, future, future)
    assert str(start.value).startswith(f"start_year must be no later than {future - 1}, ")
    assert not respx_mock.calls


def test_the_ceiling_counts_market_years_ends_included(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the ceiling lowered to 2, 2023 to 2024 is served and 2023 to 2025 refused before
    any request; the real ceiling is 10, and ten years would need ten recordings."""
    monkeypatch.setattr(tasks, "SERIES_MAX_YEARS", 2)
    with pytest.raises(InvalidRequestError, match="2023 to 2025 is 3 market years"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2025)
    assert not respx_mock.calls
    replay_fixture(COUNTRY, "wheat_white_canada_2023")
    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024)
    assert len(result.data) == 107
    assert len(respx_mock.calls) == 2


# adapters


@pytest.mark.anyio
async def test_top_destinations_tool_end_to_end(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(ALL, "cottonseed_2024")
    arguments: dict[str, Any] = {
        "commodity_code": 1201,
        "market_year": 2024,
        "field": "outstandingSales",
        "n": 3,
    }
    payload = await mcp_call(server, "usda_esr_get_top_destinations", dict(arguments))
    assert [(row["country_code"], row["outstanding_sales"]) for row in payload["data"]] == [
        (5800, 17092),
        (5880, 4223),
        (5230, 939),
    ]
    assert {row["week_ending_date"] for row in payload["data"]} == {"2024-08-01"}
    assert "note" not in payload
    assert payload["meta"]["request"] == arguments, "field as its upstream value, a string"
    assert payload["meta"]["endpoint"] == OPERATIONS[ALL]
    assert payload["meta"]["vintage"] == "2024-08-01"
    assert payload["meta"]["published_at"] is None
    refused = await mcp_call_text(
        server, "usda_esr_get_top_destinations", {**arguments, "field": "outstanding_sales"}
    )
    assert refused.startswith(
        "error: InvalidRequestError: field: Input should be 'weeklyExports', "
    ), "core's text for an argument the schema refuses"
    assert route.call_count == 1, "the schema refused the unknown field before any request"


@pytest.mark.anyio
async def test_latest_week_and_series_tools_are_whole(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    replay_fixture(ALL, "cottonseed_2024")
    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    week = await mcp_call(
        server, "usda_esr_get_latest_week", {"commodity_code": 1201, "market_year": 2024}
    )
    assert [row["country_code"] for row in week["data"]] == LATEST_DESTINATIONS
    assert "note" not in week
    series = await mcp_call(
        server,
        "usda_esr_get_weekly_series",
        {"commodity_code": 104, "country_code": 1220, "start_year": 2024, "end_year": 2024},
    )
    assert len(series["data"]) == 54
    assert "note" not in series, "54 weeks fit the default cap"
    assert series["data"][-1]["week_ending_date"] == series["meta"]["vintage"] == "2024-06-06"


@pytest.mark.anyio
async def test_weekly_series_tool_end_to_end(replay_fixture: ReplayFixture) -> None:
    older = replay_fixture(COUNTRY, "wheat_white_canada_2023")
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    arguments: dict[str, Any] = {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2023,
        "end_year": 2024,
    }
    payload = await mcp_call(server, "usda_esr_get_weekly_series", dict(arguments))
    assert len(payload["data"]) == 107
    assert "note" not in payload, "two market years, 107 rows, fit the default cap"
    weeks = [row["week_ending_date"] for row in payload["data"]]
    assert (weeks[0], weeks[52], weeks[53], weeks[-1]) == (
        "2022-06-02",
        "2023-06-01",
        "2023-06-01",
        "2024-06-06",
    ), "the boundary week once per market year"
    assert payload["meta"]["request"] == arguments
    assert payload["meta"]["endpoint"] == OPERATIONS[COUNTRY]
    assert payload["meta"]["vintage"] == "2024-06-06"
    assert payload["meta"]["published_at"] is None
    refused = await mcp_call_text(
        server, "usda_esr_get_weekly_series", {**arguments, "start_year": 2015, "end_year": 2025}
    )
    assert refused.startswith(
        "error: InvalidRequestError: 2015 to 2025 is 11 market years, and the weekly series "
        "makes one request per market year; it spans at most 10 market years per call."
    )
    backwards = await mcp_call_text(
        server, "usda_esr_get_weekly_series", {**arguments, "start_year": 2024, "end_year": 2023}
    )
    assert backwards.startswith("error: InvalidRequestError: start_year 2024 is after end_year")
    assert (older.call_count, newer.call_count) == (1, 1), "the refusals sent nothing"


@pytest.mark.anyio
@pytest.mark.usefixtures("in_2026")
async def test_an_unreleased_market_year_over_mcp(replay_fixture: ReplayFixture) -> None:
    releases = replay_fixture(RELEASES, "all")
    refused = await mcp_call_text(
        server,
        "usda_esr_get_weekly_series",
        {"commodity_code": 104, "country_code": 1220, "start_year": 2024, "end_year": 2028},
    )
    assert refused == f"error: NotFoundError: {RANGE_REFUSED}"
    assert sent_urls(releases) == [RELEASE_DATES]


def test_the_weekly_series_cap_note_names_the_range() -> None:
    """A note of the task's own, the family's bounds kept (conventions §8, ADR-0016;
    Johannes, 2026-10-28), as ``get_exports``' names ``country_code``."""
    cap = tasks.MCP_CAPS["get_weekly_series"]
    assert (cap.max_rows, cap.max_bytes) == (200, 65_536), "a note-only cap"
    assert cap.note == (
        "narrow start_year and end_year, e.g. 2023 and 2024: each market year is up to 54 "
        "rows, so three fit, and the oldest weeks come first"
    )


def test_the_series_note_is_what_an_agent_reads_when_the_range_outgrows_the_cap(
    replay_fixture: ReplayFixture,
) -> None:
    """Not reachable with two recordings, 107 rows; with the row bound lowered to 100 the
    same cap shows the text an agent reads past 200 rows, four market years or more."""
    replay_fixture(COUNTRY, "wheat_white_canada_2023")
    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    cap = dataclasses.replace(tasks.MCP_CAPS["get_weekly_series"], max_rows=100)
    payload = json.loads(cap_result(tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2023, 2024), cap))
    assert len(payload["data"]) == 100
    assert payload["data"][0]["week_ending_date"] == "2022-06-02", "the oldest weeks first"
    assert payload["note"] == (
        "showing 100 of 107 rows (cap: 100 rows or 65536 bytes); narrow start_year and "
        "end_year, e.g. 2023 and 2024: each market year is up to 54 rows, so three fit, and "
        "the oldest weeks come first"
    )


def test_top_destinations_over_http(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    route = replay_fixture(ALL, "cottonseed_2024")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    params: dict[str, Any] = {
        "commodity_code": 1201,
        "market_year": 2024,
        "field": "accumulatedExports",
        "n": 2,
    }
    response = http.get("/usda-esr/get_top_destinations", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["country_code"] for row in body["data"]] == [5800, 5880]
    assert body["meta"]["request"]["field"] == "accumulatedExports"
    refused = http.get(
        "/usda-esr/get_top_destinations", params={**params, "field": "accumulated_exports"}
    )
    assert refused.status_code == 422
    assert route.call_count == 1


def test_weekly_series_over_http(replay_fixture: ReplayFixture) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    older = replay_fixture(COUNTRY, "wheat_white_canada_2023")
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    params: dict[str, Any] = {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2023,
        "end_year": 2024,
    }
    response = http.get("/usda-esr/get_weekly_series", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["data"]) == 107
    assert body["data"][0]["week_ending_date"] == "2022-06-02"
    assert body["meta"]["request"] == params
    assert body["meta"]["vintage"] == "2024-06-06"
    refused = http.get("/usda-esr/get_weekly_series", params={**params, "start_year": 2014})
    assert refused.status_code == 422, "InvalidRequestError is 422"
    assert "at most 10 market years" in refused.text
    old_call = http.get(
        "/usda-esr/get_weekly_series",
        params={"commodity_code": 104, "country_code": 1220, "market_year": 2024},
    )
    assert old_call.status_code == 422, "0.1.0's market_year alone is no longer a call"
    assert (older.call_count, newer.call_count) == (1, 1)


@pytest.mark.usefixtures("in_2026")
def test_an_unreleased_market_year_over_http(replay_fixture: ReplayFixture) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    releases = replay_fixture(RELEASES, "all")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    params = {"commodity_code": 104, "country_code": 1220, "start_year": 2024, "end_year": 2028}
    refused = http.get("/usda-esr/get_weekly_series", params=params)
    assert refused.status_code == 404, "NotFoundError is a 404 problem"
    assert refused.json()["title"] == "NotFoundError"
    assert "its latest released market year is 2027" in refused.text
    assert sent_urls(releases) == [RELEASE_DATES]
