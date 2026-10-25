"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

One live smoke test per task function, three keyed calls in all: ``get_exports`` for
wheat white to Canada and for soybeans to Mexico, market year 2024, and
``get_release_dates``. The codes are taken from the packaged lists by their upstream
names, so a renamed or recoded commodity or country fails here first. Next to them, the
template's reachability check, ``test_upstream_answers``, sends no key: a plain request
to ``BASE_URL`` that spends no quota call.
"""

from datetime import date

import httpx
import pytest

from xippios.usda.esr import tasks
from xippios.usda.esr._client import BASE_URL, config, policy
from xippios.usda.esr.enums import UnitId
from xippios.usda.esr.params import packaged_values

pytestmark = [pytest.mark.live, pytest.mark.anyio]


def _code(list_name: str, code_field: str, name_field: str, name: str) -> int:
    """The packaged code whose upstream name, stripped of padding, is ``name``."""
    packaged = packaged_values(list_name)
    assert packaged is not None
    codes = {str(r[name_field]).strip(): int(r[code_field]) for r in packaged.records}
    return codes[name]


WHEAT_WHITE = _code("commodities", "commodityCode", "commodityName", "Wheat - White")
SOYBEANS = _code("commodities", "commodityCode", "commodityName", "Soybeans")
CANADA = _code("countries", "countryCode", "countryDescription", "CANADA")
MEXICO = _code("countries", "countryCode", "countryDescription", "MEXICO")


async def test_upstream_answers() -> None:
    """The base URL answers without a server error.

    A plain request, not the package's client, so no key goes out and no call counts
    against the key's quota; a keyed gateway's answer to it (a 403 or a 404, say) still
    shows the host is up.
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
    snapshot = policy.snapshot()
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
    latest = max(r.release_time_stamp for r in result.data)
    assert result.meta.vintage == latest.date().isoformat()
    assert result.meta.published_at is None
