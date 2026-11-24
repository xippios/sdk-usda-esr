"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

One live smoke test per task function: ``get_exports`` for wheat white to Canada and for
soybeans to Mexico, market year 2024; ``get_release_dates`` whole, with ``since`` and for
wheat white by ``commodity_code``; and ``get_weekly_series`` for wheat white to Canada,
market years 2023 to 2024, one call per market year, and no release-list call, since the
range ends before the current calendar year (a range ending this year or later adds one).
The codes are taken from the packaged lists by their upstream names, so a renamed or recoded
commodity or country fails here first. Core's nightly comparison of the packaged lists runs
here too, one keyed call for each list of ``LIVE_LISTS`` (sdk-core ADR-0055), the signal to
run ``/refresh-reference-data``. Core's testing plugin prints the run's requests as
``requests sent by the live run: <n>``, the count in the log of ``live.yml`` that
``/release-prep`` cites; core's response cache answers a second read of a path within its
lifetime, so the run sends fewer requests than its calls.
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime
from typing import Any

import pytest
from xippios.core import Answer, PackagedList, UpstreamModel
from xippios.core.testing.live import *  # noqa: F403
from xippios.usda.fas import Gateway

from xippios.usda.esr import api, tasks
from xippios.usda.esr.enums import UnitId
from xippios.usda.esr.params import COMMODITIES, COUNTRIES, PACKAGE, REGIONS, UNITS

pytestmark = [pytest.mark.live, pytest.mark.anyio]


def _records(
    wrapper: Callable[[], Awaitable[Answer[Any]]],
) -> Callable[[], Awaitable[Sequence[UpstreamModel]]]:
    """The wrapper as the comparison's fetch: its answer's payload, the records it compares."""

    async def fetch() -> Sequence[UpstreamModel]:
        records: Sequence[UpstreamModel] = (await wrapper()).payload
        return records

    return fetch


LIVE_LISTS = {  # each packaged list compared, by its file reference/<name>.json
    "commodities": (COMMODITIES, _records(api.get_commodities)),
    "countries": (COUNTRIES, _records(api.get_countries)),
    "regions": (REGIONS, _records(api.get_regions)),
    "unitsOfMeasure": (UNITS, _records(api.get_units_of_measure)),
}
NO_LIVE_LIST: dict[str, str] = {}  # every packaged list is compared


def _code(list_name: str, code_field: str, name_field: str, name: str) -> int:
    """The packaged code whose upstream name, stripped of padding, is ``name``."""
    packaged = PackagedList.load(PACKAGE, list_name)
    codes = {str(r[name_field]).strip(): int(r[code_field]) for r in packaged.records}
    return codes[name]


WHEAT_WHITE = _code("commodities", "commodityCode", "commodityName", "Wheat - White")
SOYBEANS = _code("commodities", "commodityCode", "commodityName", "Soybeans")
CANADA = _code("countries", "countryCode", "countryDescription", "CANADA")
MEXICO = _code("countries", "countryCode", "countryDescription", "MEXICO")


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


async def test_get_release_dates_of_one_commodity_live() -> None:
    result = await tasks.get_release_dates_async(commodity_code=WHEAT_WHITE)
    (year,) = result.data
    assert year.commodity_code == WHEAT_WHITE
    assert year.market_year >= 2027, "wheat's 2027 began on 2026-06-01"
    assert year.market_year_start < year.market_year_end
    assert year.market_year == year.market_year_end.year, "named by its end year"
    assert datetime.fromisoformat(year.release_time_stamp_text) == year.release_time_stamp
    assert result.meta.request == {"commodity_code": WHEAT_WHITE}
    assert result.meta.published_at_naive is True


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
