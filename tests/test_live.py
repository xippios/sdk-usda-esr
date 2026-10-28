"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

One live smoke test per task function, thirteen keyed calls in all: ``get_exports`` for
wheat white to Canada and for soybeans to Mexico, market year 2024;
``get_release_dates``, once whole and once with ``since``, and ``get_market_year`` for
wheat white; the slices, ``get_latest_week`` for wheat HRW and ``get_top_destinations``
for soybeans, one call each, and ``get_weekly_series`` for wheat white to Canada, market
years 2023 to 2024, two calls, one per market year, and no release-list call, since the
range ends before the current calendar year (a range into next year adds one). The codes
are taken from the packaged lists by their upstream names, so a renamed or recoded
commodity or country fails here first. The four list tasks answer from the package
without a call, so their test fetches the list through its endpoint wrapper, one call
each, and checks that the packaged records equal it: the freshness check
``reference/README.md`` promises. A difference fails the test naming what is gone and
what is new; ``/refresh-reference-data`` then refreshes the package. Next to them, the
template's reachability check, ``test_upstream_answers``, sends no key: a plain request
to ``BASE_URL`` that spends no quota call.
"""

from datetime import date, datetime
from typing import Any

import httpx
import pytest
from xippios.core import PackagedList
from xippios.core.data_gov import Gateway

from xippios.usda.esr import api, tasks
from xippios.usda.esr._client import BASE_URL, config
from xippios.usda.esr.enums import UnitId
from xippios.usda.esr.models import ExportField
from xippios.usda.esr.params import PACKAGE

pytestmark = [pytest.mark.live, pytest.mark.anyio]


def _code(list_name: str, code_field: str, name_field: str, name: str) -> int:
    """The packaged code whose upstream name, stripped of padding, is ``name``."""
    packaged = PackagedList.load(PACKAGE, list_name)
    codes = {str(r[name_field]).strip(): int(r[code_field]) for r in packaged.records}
    return codes[name]


WHEAT_WHITE = _code("commodities", "commodityCode", "commodityName", "Wheat - White")
WHEAT_HRW = _code("commodities", "commodityCode", "commodityName", "Wheat - HRW")
SOYBEANS = _code("commodities", "commodityCode", "commodityName", "Soybeans")
CANADA = _code("countries", "countryCode", "countryDescription", "CANADA")
MEXICO = _code("countries", "countryCode", "countryDescription", "MEXICO")


async def test_upstream_answers() -> None:
    """The base URL answers without a server error.

    A plain request, not the package's client, so no key goes out and it spends no keyed
    call; a keyed gateway's answer to it (a 403 or a 404, say) still shows the host is up.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
    assert response.status_code < 500


async def test_get_exports_for_one_country_live() -> None:
    result = await tasks.get_exports_async(WHEAT_WHITE, 2024, CANADA)
    assert result.data
    assert {(r.commodity_code, r.country_code) for r in result.data} == {(WHEAT_WHITE, CANADA)}
    assert {r.unit_id for r in result.data} == {UnitId.METRIC_TONS}
    weeks = [r.week_ending_date for r in result.data]
    assert date(2023, 5, 25) < min(weeks), "wheat's market year 2024 starts in June 2023"
    assert max(weeks) < date(2024, 6, 14), "and ends in May 2024; its last week ends in June"
    assert result.meta.vintage == max(weeks).isoformat()
    assert result.meta.published_at is None
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert snapshot.limit == 1000


async def test_get_exports_soybeans_live() -> None:
    result = await tasks.get_exports_async(SOYBEANS, 2024, MEXICO)
    assert result.data
    assert {(r.commodity_code, r.country_code) for r in result.data} == {(SOYBEANS, MEXICO)}
    weeks = [r.week_ending_date for r in result.data]
    assert date(2023, 8, 25) < min(weeks), "soybeans' market year 2024 starts in September 2023"
    assert max(weeks) < date(2024, 9, 14), "and ends in August 2024"
    assert result.meta.endpoint == "ESRData_GetCountryData"
    assert result.meta.vintage == max(weeks).isoformat()


async def test_get_release_dates_live() -> None:
    result = await tasks.get_release_dates_async()
    by_code = {r.commodity_code: r for r in result.data}
    assert WHEAT_WHITE in by_code
    assert SOYBEANS in by_code
    wheat = by_code[WHEAT_WHITE]
    assert wheat.market_year == wheat.market_year_end.year, "named by its end year"
    assert (wheat.market_year_start.month, wheat.market_year_end.month) == (6, 5)
    assert all(r.release_time_stamp.tzinfo is None for r in result.data)
    latest = max(result.data, key=lambda r: r.release_time_stamp)
    assert result.meta.vintage == latest.release_time_stamp_text, "upstream's text"
    assert result.meta.published_at == latest.release_time_stamp, "naive, as upstream gives it"
    assert result.meta.published_at_naive is True


async def test_get_release_dates_since_live() -> None:
    since = "2000-01-01T00:00:00"
    result = await tasks.get_release_dates_async(since=since)
    assert result.data
    assert all(r.release_time_stamp > datetime.fromisoformat(since) for r in result.data), (
        "every record released after since"
    )
    assert result.meta.request == {"since": since}
    latest = max(result.data, key=lambda r: r.release_time_stamp)
    assert result.meta.vintage == latest.release_time_stamp_text


async def test_get_market_year_live() -> None:
    result = await tasks.get_market_year_async(WHEAT_WHITE)
    year = result.data
    assert year.commodity_code == WHEAT_WHITE
    assert year.market_year >= 2027, "wheat's 2027 began on 2026-06-01"
    assert year.market_year_start < year.market_year_end
    assert year.market_year == year.market_year_end.year, "named by its end year"
    assert datetime.fromisoformat(year.release_time_stamp_text) == year.release_time_stamp
    assert result.meta.vintage == year.release_time_stamp_text, "upstream's text"
    assert result.meta.published_at == year.release_time_stamp
    assert result.meta.published_at_naive is True


async def test_get_latest_week_live() -> None:
    result = await tasks.get_latest_week_async(WHEAT_HRW, 2024)
    assert result.data
    weeks = {r.week_ending_date for r in result.data}
    assert len(weeks) == 1, "one week"
    (week,) = weeks
    assert date(2024, 5, 1) < week < date(2024, 6, 14), "wheat's market year 2024 ends in May"
    destinations = [r.country_code for r in result.data]
    assert len(set(destinations)) == len(destinations), "one row per destination"
    assert {r.commodity_code for r in result.data} == {WHEAT_HRW}
    assert result.meta.endpoint == "ESRData_GetAllCountriesData"
    assert result.meta.vintage == week.isoformat()
    assert result.meta.published_at is None


async def test_get_top_destinations_live() -> None:
    result = await tasks.get_top_destinations_async(
        SOYBEANS, 2024, ExportField.ACCUMULATED_EXPORTS, 5
    )
    assert len(result.data) == 5
    values = [r.accumulated_exports for r in result.data]
    assert values == sorted(values, reverse=True), "largest first"
    weeks = {r.week_ending_date for r in result.data}
    assert len(weeks) == 1, "one week"
    (week,) = weeks
    assert date(2024, 8, 1) < week < date(2024, 9, 14), "soybeans' 2024 ends in August 2024"
    assert result.meta.request == {
        "commodity_code": SOYBEANS,
        "market_year": 2024,
        "field": "accumulatedExports",
        "n": 5,
    }
    assert result.meta.vintage == week.isoformat()


async def test_get_weekly_series_live() -> None:
    result = await tasks.get_weekly_series_async(WHEAT_WHITE, CANADA, 2023, 2024)
    weeks = [r.week_ending_date for r in result.data]
    assert weeks
    assert weeks == sorted(weeks), "oldest first"
    assert date(2022, 5, 25) < weeks[0], "wheat's market year 2023 starts in June 2022"
    assert weeks[0] < date(2023, 5, 25) < weeks[-1], "weeks of both market years"
    assert weeks[-1] < date(2024, 6, 14), "2024 ends in May 2024; its last week ends in June"
    assert len(weeks) - len(set(weeks)) <= 1, "one row per week, but the one 2023 and 2024 share"
    assert {(r.commodity_code, r.country_code) for r in result.data} == {(WHEAT_WHITE, CANADA)}
    assert result.meta.endpoint == "ESRData_GetCountryData"
    assert result.meta.request == {
        "commodity_code": WHEAT_WHITE,
        "country_code": CANADA,
        "start_year": 2023,
        "end_year": 2024,
    }
    assert result.meta.vintage == weeks[-1].isoformat()
    assert result.meta.published_at is None


LISTS = [
    # task, the operation its list came from, its wrapper (conventions §2)
    ("list_commodities", "ESRData_GetCommodities", "get_commodities"),
    ("list_countries", "ESRData_GetCountries", "get_countries"),
    ("list_regions", "ESRData_GetRegions", "get_regions"),
    ("list_units_of_measure", "ESRData_GetUnitsOfMeasure", "get_units_of_measure"),
]


@pytest.mark.parametrize(("task", "endpoint", "wrapper"), LISTS, ids=[task for task, *_ in LISTS])
async def test_packaged_list_equals_the_live_list(task: str, endpoint: str, wrapper: str) -> None:
    packaged = await getattr(tasks, f"{task}_async")()
    live: list[Any] = await getattr(api, wrapper)()
    stale = [record for record in packaged.data if record not in live]
    new = [record for record in live if record not in packaged.data]
    behind = bool(stale or new)
    assert not behind, (
        f"{task} is behind upstream (packaged {packaged.meta.retrieved_at:%Y-%m-%d}): "
        f"{len(stale)} packaged records upstream no longer sends, {len(new)} upstream records "
        "the package lacks; "
        f"first of each: {stale[:5]}, {new[:5]}. Refresh with /refresh-reference-data."
    )
    assert packaged.data == live, f"{task}: the same records in another order"
    assert packaged.meta.endpoint == endpoint
