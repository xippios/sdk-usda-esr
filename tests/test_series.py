"""The weekly series, one destination's weeks over market years.

Each test replays a recorded answer and checks that the series puts upstream's records together
in order without changing one (sdk-core ADR-0028; https://github.com/xippios/sdk-usda-esr/pull/5).
``_recorded`` parses a fixture the way the wrapper does, without a request, so a test compares
with what upstream sent while the task's own request is counted on its route. The series makes
the one-country request ``get_exports`` makes, once per market year, so its range replays two
one-country recordings, ``wheat_white_canada_2023`` (recorded 2026-10-28) and
``wheat_white_canada_2024``, and moves the recorded empty 404 and ``[]`` to a year inside
the range (``url=``) rather than writing an answer. A range ending in the current calendar
year or later reads the release list first (``get_data_release_info/all``, recorded
2026-10-25), so those tests pin the calendar year to 2026 (``in_2026``), or to 2027 for the
January case.
"""

import dataclasses
import json
import re
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from xippios.core import Answer, AuthError, InvalidRequestError, NotFoundError, UnknownCode, parse
from xippios.core.mcp import cap_result
from xippios.core.testing import (
    ReplayFixture,
    fixture_path,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_urls,
)
from xippios.usda.fas import NoDataForYear

import xippios.usda.esr as package
from xippios.usda.esr import api, models, tasks
from xippios.usda.esr._client import BASE_URL
from xippios.usda.esr.api.get_data_release_info import ReleaseList
from xippios.usda.esr.mcp import server
from xippios.usda.esr.models import CommodityData, DataReleaseInfo
from xippios.usda.esr.params import latest_market_year

FIXTURES = Path(__file__).parent / "fixtures"
WHEAT_WHITE, COTTONSEED, RYE = 104, 1201, 501
CANADA = 1220
COUNTRY = "get_country_data"
ALL = "get_all_countries_data"
OPERATIONS = {COUNTRY: "ESRData_GetCountryData", ALL: "ESRData_GetAllCountriesData"}
"""Each wrapper, the name of its fixture directory, to its verbatim ``operationId``, the
``meta.endpoint`` of the tasks that call it (conventions §2, §10)."""
EXPORTS = f"{BASE_URL}/api/esr/exports/commodityCode"


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
    order of the requests across both operations.
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
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


UNKNOWN = 9990
"""``countryCode`` 9990, UNKNOWN in the packaged countries list (region 99, UNKNOWN)."""


def _recorded(wrapper: str, case: str) -> list[CommodityData]:
    """The recorded answer parsed as the wrapper parses it, without a request."""
    body = json.loads(load_fixture(fixture_path(FIXTURES, wrapper, case)).response.body)
    return parse(list[CommodityData], body, source="usda-esr", endpoint=OPERATIONS[wrapper])


def test_the_ranking_and_the_newest_week_leave_the_package() -> None:
    """A task that ranks, or that picks the newest week for the caller, is no task of a
    source package (conventions §14): ``get_top_destinations`` and ``get_latest_week`` leave
    with ``ExportField``, and a caller reads the same records from ``get_exports``. The series
    stays, the one request per market year that a caller could not compose otherwise."""
    for name in ["get_latest_week", "get_top_destinations"]:
        assert name not in tasks.__all__
        assert not hasattr(tasks, name)
        assert name not in package.__all__
    assert "ExportField" not in models.__all__
    assert not hasattr(models, "ExportField")
    assert "get_weekly_series" in tasks.__all__


# get_weekly_series


def test_get_weekly_series_spans_market_years_oldest_first(
    replay_fixture: ReplayFixture,
) -> None:
    """2023 to 2024: one request per market year, oldest first, and the two recordings'
    rows put together by week, each unchanged; the week both carry keeps 2023's row first."""
    older = replay_fixture(COUNTRY, "wheat_white_canada_2023")
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
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
    assert result.meta.vintage is None, (
        "ESR states no release for the records answered; a week computed from them is none"
    )
    assert result.meta.notes == [
        "Market years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows."
    ], (
        "each market year with its rows, in their order: the first 53 rows are 2023's, so the "
        "two rows of the week ending 2023-06-01 are told apart (sdk-usda-esr#23)"
    )
    assert result.meta.names == {
        "country_code": {"1220": "CANADA"},
        "unit_id": {"1": "Metric Tons"},
    }, "the codes of the rows, named by the record's model (sdk-usda-esr#30)"
    assert result.meta.published_at is None
    assert result.meta.total is None


def test_the_requests_go_out_oldest_first(respx_mock: respx.MockRouter) -> None:
    """One route for every year's URL, so ``sent_urls`` shows the order the requests went
    out in; it serves the two recorded answers in turn, as recorded.
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
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
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert sent_urls(route) == [_country_url(2023), _country_url(2024)], "oldest first"
    assert len(result.data) == 53 + 54


def test_a_weekly_series_of_one_market_year_is_its_weeks(
    replay_fixture: ReplayFixture,
) -> None:
    """2024 to 2024, a range of one: one request, the 54 weeks 0.1.0 answered for 2024."""
    route = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2024)
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
    assert result.meta.vintage is None
    assert result.meta.notes == ["Market years in the order of the rows: 2024 with 54 rows."]
    assert result.meta.published_at is None


def test_weekly_series_orders_what_upstream_sends_out_of_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded records, reversed and handed on by a replaced wrapper: the series orders
    them by week, oldest first, and changes none; across two market years the week both carry
    keeps the older year's row first, whatever upstream's order. The records are an input of
    the test, not an answer from ESR (conventions §10)."""
    answers = {
        2023: _recorded(COUNTRY, "wheat_white_canada_2023"),
        2024: _recorded(COUNTRY, "wheat_white_canada_2024"),
    }

    async def reversed_answer(_: int, __: int, market_year: int) -> Answer[list[CommodityData]]:
        return Answer(answers[market_year][::-1], datetime.now(UTC))

    monkeypatch.setattr(api, "get_country_data", reversed_answer)
    one = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2024)
    assert one.data == answers[2024]
    assert one.meta.vintage is None
    both = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert both.data == answers[2023] + answers[2024]
    assert both.meta.notes == [
        "Market years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows."
    ], "the order of the rows, whatever upstream's"


# empty answers, absent market years, the gateway's 404


def test_an_empty_weekly_series_is_an_empty_result(replay_fixture: ReplayFixture) -> None:
    """ESR's ``[]`` for one destination: the recorded body of ``year_2099`` (HTTP 200,
    ``[]``) served at a valid year's URL (``url=``), moved, not written. Nothing is
    filled, an empty answer has no vintage, and it names the country asked for
    (https://github.com/xippios/sdk-usda-esr/issues/30).
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
    route = replay_fixture(COUNTRY, "year_2099", url=_country_url(2025))
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2025, end_year=2025)
    assert sent_urls(route) == [_country_url(2025)]
    assert result.data == []
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.notes == ["Market years in the order of the rows: 2025 with 0 rows."]
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2025,
        "end_year": 2025,
    }
    assert result.meta.names == {"country_code": {"1220": "CANADA"}}, (
        "the country asked for, though no row names it (conventions §4)"
    )
    assert result.meta.endpoint == OPERATIONS[COUNTRY]


@pytest.mark.usefixtures("in_2026")
def test_a_released_year_without_exports_adds_no_rows(replay_fixture: ReplayFixture) -> None:
    """``year_2099``'s recorded ``[]`` at the 2023 URL. In 2026 market year 2023 is long
    released, so its ``[]`` is a year without exports to Canada, as rye 2024's is for every
    country (``rye_2024``): it adds no rows, 2024's come alone, and the range, ending
    before the calendar year, reads no release list.
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
    releases = replay_fixture(RELEASES, "all")
    empty = replay_fixture(COUNTRY, "year_2099", url=_country_url(2023))
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert (empty.call_count, newer.call_count) == (1, 1)
    assert sent_urls(releases) == []
    assert result.data == _recorded(COUNTRY, "wheat_white_canada_2024")
    assert result.meta.vintage is None
    assert result.meta.notes == [
        "Market years in the order of the rows: 2023 with 0 rows, 2024 with 54 rows."
    ], "a released year without exports is answered, with no rows"


# a range past the current calendar year: the release list first


@pytest.mark.usefixtures("in_2026")
def test_a_range_into_next_year_reads_the_release_list_first(
    respx_mock: respx.MockRouter,
) -> None:
    """2024 to 2027 in 2026: the release list (wheat white's current market year 2027),
    then the four yearly requests, oldest first. 2025 to 2027 were not recorded for this
    pair: ``year_2099``'s recorded ``[]`` is moved to their URLs and stands in for the
    request order only (upstream's ``wheat_white_2027`` recording has 20 rows to Canada),
    so neither the rows nor ``meta.vintage`` are asserted."""
    route = _serve(
        respx_mock,
        {
            RELEASE_DATES: (RELEASES, "all"),
            _country_url(2024): (COUNTRY, "wheat_white_canada_2024"),
            **{_country_url(year): (COUNTRY, "year_2099") for year in (2025, 2026, 2027)},
        },
    )
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2027)
    assert sent_urls(route) == [
        RELEASE_DATES,
        _country_url(2024),
        _country_url(2025),
        _country_url(2026),
        _country_url(2027),
    ], "one request more, first"
    assert result.meta.endpoint == OPERATIONS[COUNTRY], "the records' operation"
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 2024,
        "end_year": 2027,
    }
    assert result.meta.published_at is None


@pytest.mark.usefixtures("in_2026")
def test_a_range_ending_this_year_reads_the_release_list_first(
    respx_mock: respx.MockRouter,
) -> None:
    """2024 to 2026 in 2026: a market year named by the current year may not be released yet
    (https://github.com/xippios/sdk-usda-esr/pull/10), so the release list comes first, then the
    three yearly requests. ``year_2099``'s ``[]`` at 2025 and 2026 stands in for the order only."""
    route = _serve(
        respx_mock,
        {
            RELEASE_DATES: (RELEASES, "all"),
            _country_url(2024): (COUNTRY, "wheat_white_canada_2024"),
            _country_url(2025): (COUNTRY, "year_2099"),
            _country_url(2026): (COUNTRY, "year_2099"),
        },
    )
    tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2026)
    assert sent_urls(route) == [
        RELEASE_DATES,
        _country_url(2024),
        _country_url(2025),
        _country_url(2026),
    ], "four requests"


@pytest.mark.usefixtures("in_2026")
def test_a_range_ending_before_this_year_reads_no_release_list(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """2023 to 2024 and 2024 to 2025 in 2026: ESR has released every market year named by
    a past year, so only the yearly requests go out (``year_2099``'s ``[]`` moved to 2025,
    for the order only)."""
    releases = replay_fixture(RELEASES, "all")
    route = _serve(
        respx_mock,
        {
            _country_url(2023): (COUNTRY, "wheat_white_canada_2023"),
            _country_url(2024): (COUNTRY, "wheat_white_canada_2024"),
            _country_url(2025): (COUNTRY, "year_2099"),
        },
    )
    historical = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert len(historical.data) == 53 + 54
    tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2025)
    assert sent_urls(route) == [
        _country_url(2023),
        _country_url(2024),
        _country_url(2025),
    ], "the second range's 2024 is the cache's"
    assert sent_urls(releases) == [], "no release list for either range"


RANGE_REFUSED = (
    "ESR has not released market year 2028 of commodity 104 yet: its latest released market "
    "year is 2027, the current one in ESR's release list (ESRData_GetDataReleaseInfo). The "
    "release list was read and no exports were requested. ESR answers a market year it has not "
    "released with an empty list, the same answer as a year without exports, so the range 2024 "
    "to 2028 is refused rather than returned without it; ask for market years up to 2027."
)
"""Probed 2026-10-28, one keyed call, not kept: wheat white to Canada, market year 2028,
answered HTTP 200 with ``[]``, the answer of a released year without exports."""


@pytest.mark.usefixtures("in_2026")
def test_a_range_past_the_current_market_year_is_refused(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """2024 to 2028 in 2026: 2028 is after wheat white's current market year, 2027, so the
    whole range is refused naming 2027 (conventions §4; sdk-core ADR-0041, decisions 6 and
    7), after the one release-list request and before any yearly one, nothing partial."""
    releases = replay_fixture(RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2028)
    assert str(info.value) == RANGE_REFUSED
    assert not isinstance(info.value, (InvalidRequestError, NoDataForYear))
    assert sent_urls(releases) == [RELEASE_DATES]
    assert len(respx_mock.calls) == 1, "no yearly request"
    with pytest.raises(NotFoundError, match="its latest released market year is 2027"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2028, end_year=2028)


@pytest.mark.usefixtures("in_2026")
def test_a_calendar_year_commodity_is_refused_past_this_year(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """Beef muscle cuts (1701) run the calendar year: on the recorded list their current
    market year is 2026, so 2025 to 2027 is refused naming 2026."""
    releases = replay_fixture(RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(1701, CANADA, start_year=2025, end_year=2027)
    assert str(info.value).startswith(
        "ESR has not released market year 2027 of commodity 1701 yet: its latest released "
        "market year is 2026, "
    )
    assert "ask for market years up to 2026." in str(info.value)
    assert sent_urls(releases) == [RELEASE_DATES]
    assert len(respx_mock.calls) == 1


def test_a_calendar_year_commodity_in_january_is_refused(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The January window: with the calendar at 2027 and the recorded list still naming 2026 as
    beef muscle cuts' current market year, as it would until ESR releases a week of 2027, 2026
    to 2027 is refused naming 2026 after the release-list request alone, where a gate on years
    after the current one would have read 2027's ``[]`` as a year without exports
    (https://github.com/xippios/sdk-usda-esr/pull/10)."""
    monkeypatch.setattr(tasks, "_calendar_year", lambda: 2027)
    releases = replay_fixture(RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(1701, CANADA, start_year=2026, end_year=2027)
    assert str(info.value).startswith(
        "ESR has not released market year 2027 of commodity 1701 yet: its latest released "
        "market year is 2026, "
    )
    assert "the range 2026 to 2027 is refused" in str(info.value)
    assert sent_urls(releases) == [RELEASE_DATES]
    assert len(respx_mock.calls) == 1, "no yearly request"


@pytest.mark.usefixtures("in_2026")
def test_a_commodity_the_release_list_lacks_refuses_a_range_into_next_year(
    monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    """The recorded release list without wheat white, handed on by a replaced wrapper: the
    series' refusal, before any yearly request. The records are an input of the test, not an
    answer from ESR (conventions §10)."""
    body = json.loads(load_fixture(fixture_path(FIXTURES, RELEASES, "all")).response.body)
    recorded = parse(
        list[DataReleaseInfo], body, source="usda-esr", endpoint="ESRData_GetDataReleaseInfo"
    )

    records = [r for r in recorded if r.commodity_code != WHEAT_WHITE]
    printed = [r["releaseTimeStamp"] for r in body if r["commodityCode"] != WHEAT_WHITE]

    async def without_wheat_white() -> Answer[ReleaseList]:
        return Answer(ReleaseList(records, printed), datetime.now(UTC))

    monkeypatch.setattr(api, "get_data_release_info", without_wheat_white)
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2027)
    assert str(info.value) == (
        "ESR lists no market year for commodity 104: GET /api/esr/datareleasedates "
        "(ESRData_GetDataReleaseInfo) answered without a record for it, although the packaged "
        "commodities list names it. The release list was read and no exports were requested."
    )
    assert not respx_mock.calls, "no yearly request"


def test_a_market_year_esr_lacks_inside_the_range_is_skipped(
    replay_fixture: ReplayFixture,
) -> None:
    """``year_1900``'s recorded empty 404 (``text/plain``) at the 2023 URL: the year adds no
    rows, no error is raised, and the series goes on with 2024 (conventions §4, as
    sdk-usda-psd's ``get_time_series`` skips PSD's empty 404).
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
    absent = load_fixture(fixture_path(FIXTURES, COUNTRY, "year_1900"))
    assert (absent.response.status, absent.response.content) == (404, b"")
    missing = replay_fixture(COUNTRY, "year_1900", url=_country_url(2023))
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert (missing.call_count, newer.call_count) == (1, 1)
    assert result.data == _recorded(COUNTRY, "wheat_white_canada_2024")
    assert result.meta.vintage is None
    assert result.meta.notes == [
        "Market years in the order of the rows: 2024 with 54 rows; passed over, without data "
        "in ESR: 2023."
    ], "the year passed over is named, since no row states it (sdk-usda-esr#23)"
    assert result.meta.request["start_year"] == 2023


def test_a_range_esr_lacks_entirely_is_an_empty_list(replay_fixture: ReplayFixture) -> None:
    """Every year answers the empty 404: an empty list without a vintage, not an error.
    Market year 1900 as a range of one is the recorded answer itself, where 0.1.0 raised
    ``NoDataForYear``; 2023 to 2024 serves it at both URLs.
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
    route = replay_fixture(COUNTRY, "year_1900")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=1900, end_year=1900)
    assert sent_urls(route) == [_country_url(1900)]
    assert result.data == []
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.notes == ["Market years passed over, without data in ESR: 1900."]
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "start_year": 1900,
        "end_year": 1900,
    }
    first = replay_fixture(COUNTRY, "year_1900", url=_country_url(2023))
    second = replay_fixture(COUNTRY, "year_1900", url=_country_url(2024))
    both = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert (first.call_count, second.call_count) == (1, 1)
    assert both.data == []
    assert both.meta.vintage is None
    assert both.meta.notes == ["Market years passed over, without data in ESR: 2023, 2024."]


def test_get_exports_still_names_a_market_year_esr_lacks(replay_fixture: ReplayFixture) -> None:
    """The single-year task keeps raising for ESR's empty 404; only the series skips it."""
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        tasks.get_exports(WHEAT_WHITE, 1900, country_code=CANADA)
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
    raised, the request for 2024 never sent, nothing partial returned.
    The body is composed from api.data.gov's documented answer (conventions §10, kind 2).
    """
    newer = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    gateway = respx_mock.get(_country_url(2023)).mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "NOT_FOUND", "message": "The requested URL was not found."}},
        )
    )
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert not isinstance(info.value, NoDataForYear)
    assert str(info.value).startswith("api.data.gov has no route for GET /api/esr/exports/")
    assert (gateway.call_count, newer.call_count) == (1, 0), "nothing after the error"


def test_a_refusal_inside_the_range_stops_the_series(replay_fixture: ReplayFixture) -> None:
    """api.data.gov's recorded refusal of the key, answered alike on every path behind it
    (conventions §10), at the 2023 URL: any error but the empty 404 stops the series.
    Each recording served at another URL is NOT RECORDED there (conventions §10, kind 3).
    """
    later = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    refused = replay_fixture("get_commodities", "invalid_key", url=_country_url(2023))
    with pytest.raises(AuthError, match="API_KEY_INVALID") as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert (refused.call_count, later.call_count) == (1, 0)
    assert "The series stopped" not in str(info.value), "nothing was fetched before it"


def test_a_refusal_after_the_first_market_year_names_the_years_fetched(
    replay_fixture: ReplayFixture,
) -> None:
    """The same recorded refusal at the 2024 URL, after 2023 was answered: the error keeps
    its class and names the market years fetched before it, and nothing is returned, core's
    walk of periods (https://github.com/xippios/sdk-usda-esr/issues/29; sdk-core ADR-0054).
    NOT RECORDED at that URL: api.data.gov refuses an invalid key alike on every path behind
    it, so the recorded refusal stands for this one (conventions §10, kind 3)."""
    earlier = replay_fixture(COUNTRY, "wheat_white_canada_2023")
    refused = replay_fixture("get_commodities", "invalid_key", url=_country_url(2024))
    with pytest.raises(AuthError, match="API_KEY_INVALID") as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert (earlier.call_count, refused.call_count) == (1, 1)
    assert str(info.value).endswith(
        " The series stopped at 2024 after 1 period answered, 2023, and returns nothing."
    )


def test_the_gateways_not_found_propagates_unchanged(respx_mock: respx.MockRouter) -> None:
    """NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body, as ``test_tasks.py``
    builds it. Only ESR's empty 404 means "no data for this market year".
    The body is composed from api.data.gov's documented answer (conventions §10, kind 2).
    """
    respx_mock.get(f"{EXPORTS}/104/countryCode/1220/marketYear/2024").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "NOT_FOUND", "message": "The requested URL was not found."}},
        )
    )
    with pytest.raises(NotFoundError) as info:
        tasks.get_weekly_series(104, 1220, start_year=2024, end_year=2024)
    assert not isinstance(info.value, NoDataForYear)
    assert str(info.value).startswith("api.data.gov has no route for GET /api/esr/exports/")


# 9990, UNKNOWN: a destination code like any other


def test_list_countries_names_the_unknown_destination() -> None:
    (country,) = package.list_countries(search=str(UNKNOWN)).data
    assert (country.country_code, country.country_name, country.region_id) == (
        UNKNOWN,
        "UNKNOWN",
        99,
    )


@pytest.mark.usefixtures("in_2026")
def test_every_country_of_wheat_white_2027(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Wheat white's current market year in 2026: the release list is read first, and the
    answer holds 9990 like any destination."""
    releases = replay_fixture(RELEASES, "all")
    replay_fixture(ALL, "wheat_white_2027")
    result = tasks.get_exports(WHEAT_WHITE, 2027)
    assert sent_urls(releases) == [RELEASE_DATES]
    assert len(result.data) == 385
    assert len({r.country_code for r in result.data}) == 22
    assert UNKNOWN in {r.country_code for r in result.data}
    assert max(r.week_ending_date for r in result.data) == date(2026, 10, 15)
    assert result.meta.vintage is None


# validation, before any request


def test_the_series_checks_its_arguments_before_any_request(respx_mock: respx.MockRouter) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly."""
    with pytest.raises(UnknownCode, match=r"9990 \(UNKNOWN\)"):
        tasks.get_weekly_series(WHEAT_WHITE, 9999, start_year=2024, end_year=2024)
    with pytest.raises(UnknownCode, match="commodity_code"):
        tasks.get_weekly_series(999, CANADA, start_year=2024, end_year=2024)
    with pytest.raises(InvalidRequestError, match="is not an integer code"):
        tasks.get_weekly_series(WHEAT_WHITE, "1220", start_year=2024, end_year=2024)  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError, match=r"^start_year must be a four-digit year"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=24, end_year=2024)
    with pytest.raises(InvalidRequestError, match=r"^end_year must be a four-digit year"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=24)
    with pytest.raises(InvalidRequestError, match=r"^market_year must be a four-digit year"):
        tasks.get_exports(WHEAT_WHITE, 24, country_code=CANADA)
    assert not respx_mock.calls


def test_the_weekly_series_checks_its_range_before_any_request(
    respx_mock: respx.MockRouter,
) -> None:
    """respx is active with no routes mounted: a backwards range, one over the ceiling and
    a year after ``latest_market_year()`` are refused without a request."""
    with pytest.raises(InvalidRequestError) as backwards:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=2023)
    assert str(backwards.value) == (
        "start_year 2024 is after end_year 2023. Nothing was sent. Pass the earlier market "
        "year first, e.g. start_year=2022, end_year=2024."
    ), "§5's sentence after the first (sdk-core#481)"
    assert (tasks.SERIES.most, tasks.SERIES.value, tasks.SERIES.unit) == (10, 10, "market years")
    assert (tasks.SERIES.mcp, tasks.SERIES.option) == (None, None), "the same over MCP"
    with pytest.raises(InvalidRequestError) as eleven:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2015, end_year=2025)
    assert str(eleven.value) == (
        "2015 to 2025 is 11 market years; one call fetches at most 10 market years. Nothing "
        "was sent. Narrow the range, e.g. start_year=2016, end_year=2025, or split it into "
        "calls of at most 10."
    ), "core's Ceiling with the task's advice (sdk-usda-esr#29; sdk-core ADR-0054)"
    future = latest_market_year() + 1
    with pytest.raises(InvalidRequestError, match="answers a future one") as end:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2024, end_year=future)
    assert str(end.value).startswith(f"end_year must be no later than {future - 1}, ")
    with pytest.raises(InvalidRequestError, match="answers a future one") as start:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=future, end_year=future)
    assert str(start.value).startswith(f"start_year must be no later than {future - 1}, ")
    assert not respx_mock.calls


@pytest.fixture
def ceiling_of_two() -> Iterator[None]:
    """The series' ceiling set to 2 for the test, and to its most again after it."""
    tasks.SERIES.set(2)
    try:
        yield
    finally:
        tasks.SERIES.set(tasks.SERIES.most)


@pytest.mark.usefixtures("ceiling_of_two")
def test_the_ceiling_counts_market_years_ends_included(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
) -> None:
    """With the ceiling lowered to 2, 2023 to 2024 is served and 2023 to 2025 refused before
    any request; the real ceiling is 10, and ten years would need ten recordings."""
    with pytest.raises(InvalidRequestError, match="2023 to 2025 is 3 market years"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2025)
    assert not respx_mock.calls
    replay_fixture(COUNTRY, "wheat_white_canada_2023")
    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024)
    assert len(result.data) == 107
    assert len(respx_mock.calls) == 2


# adapters


@pytest.mark.anyio
async def test_a_series_of_one_market_year_is_whole_over_mcp(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    series = await mcp_call(
        server,
        "usda_esr_get_weekly_series",
        {"commodity_code": 104, "country_code": 1220, "start_year": 2024, "end_year": 2024},
    )
    assert len(series["data"]) == 54
    assert "note" not in series, "54 weeks fit the default cap"
    assert series["data"][-1]["week_ending_date"] == "2024-06-06"
    assert series["meta"]["vintage"] is None
    assert series["meta"]["notes"] == ["Market years in the order of the rows: 2024 with 54 rows."]


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
    assert payload["meta"]["vintage"] is None
    assert payload["meta"]["notes"] == [
        "Market years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows."
    ]
    assert payload["meta"]["published_at"] is None
    refused = await mcp_call_text(
        server, "usda_esr_get_weekly_series", {**arguments, "start_year": 2015, "end_year": 2025}
    )
    assert refused.startswith(
        "error: InvalidRequestError: 2015 to 2025 is 11 market years; one call fetches at "
        "most 10 market years. Nothing was sent."
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
    """A note of the task's own, the family's bounds kept (conventions §8, sdk-core ADR-0038;
    https://github.com/xippios/sdk-usda-esr/pull/10), as ``get_exports``' names ``country_code``.
    The cap keeps the newest weeks and is not paged: with the cache a continuation would cost
    upstream nothing, so the rule allows a paged cap, and nothing asks for one
    (https://github.com/xippios/sdk-usda-esr/issues/28; sdk-core ADR-0047)."""
    cap = tasks.MCP_CAPS["get_weekly_series"]
    assert (cap.max_rows, cap.max_bytes) == (200, 65_536), "the family's bounds"
    assert (cap.paged, cap.keep) == (False, "last")
    assert cap.note == (
        "narrow start_year and end_year, e.g. 2023 and 2024: each market year is up to 54 "
        "rows, so three fit, and the newest weeks are shown; one call sends at most 11 "
        "requests, 44 attempts with retries"
    ), "the most that one call spends, retries counted (conventions §8; sdk-core ADR-0061)"


def test_the_series_note_is_what_an_agent_reads_when_the_range_outgrows_the_cap(
    replay_fixture: ReplayFixture,
) -> None:
    """Not reachable with two recordings, 107 rows; with the row bound lowered to 100 the
    same cap shows the text an agent reads past 200 rows, four market years or more: the
    newest 100 weeks, oldest first, and no offset to continue with."""
    replay_fixture(COUNTRY, "wheat_white_canada_2023")
    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    cap = dataclasses.replace(tasks.MCP_CAPS["get_weekly_series"], max_rows=100)
    payload = json.loads(
        cap_result(
            tasks.get_weekly_series(WHEAT_WHITE, CANADA, start_year=2023, end_year=2024), cap
        )
    )
    assert len(payload["data"]) == 100
    assert payload["data"][0]["week_ending_date"] == "2022-07-21", "the eighth week first"
    assert payload["data"][-1]["week_ending_date"] == "2024-06-06", "the newest week kept"
    assert payload["note"] == (
        "showing rows 8 to 107 of 107 (cap: 100 rows or 65536 bytes); narrow start_year and "
        "end_year, e.g. 2023 and 2024: each market year is up to 54 rows, so three fit, and "
        "the newest weeks are shown; one call sends at most 11 requests, 44 attempts with "
        "retries"
    )


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
    assert body["meta"]["vintage"] is None
    assert body["meta"]["notes"] == [
        "Market years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows."
    ]
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


@pytest.mark.anyio
async def test_the_series_tool_states_the_most_one_call_spends() -> None:
    """Ten market years and the release list are 11 requests, and core's four attempts for
    each make 44: the description an agent reads says so (conventions §8; sdk-core ADR-0061,
    decision 8; way P4 of https://github.com/xippios/sdk-usda-esr/issues/62)."""
    tools = {tool.name: tool for tool in await server.list_tools()}
    description = " ".join((tools["usda_esr_get_weekly_series"].description or "").split())
    assert "at most 11 requests, 44 attempts with retries" in description
    assert "meta.notes" in description, "the note on the market years is named"
    assert "since the records state no release: ``get_release_dates`` gives it" in description, (
        "why the vintage is empty, and where the release is (sdk-usda-esr#67; conventions §4)"
    )
