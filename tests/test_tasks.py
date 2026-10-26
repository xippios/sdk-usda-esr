"""Structural checks every task must satisfy. Per-task tests with recorded fixtures go below.

A replay test that checks what was sent compares ``xippios.core.testing.sent_urls(route)``,
the URLs the route received with credentials redacted, rather than keep a request from
``route.calls`` in its frame, where a failure or ``pytest -l`` would print it.
"""

import inspect
from collections.abc import Callable
from datetime import date

import httpx
import pytest
import respx
from xippios.core import InvalidRequestError, NotFoundError
from xippios.core.testing import mcp_call, sent_urls

from xippios.usda.esr import __version__, get_exports, get_release_dates, tasks
from xippios.usda.esr._client import BASE_URL
from xippios.usda.esr.enums import UnitId
from xippios.usda.esr.errors import NoDataForYear, UnknownCode
from xippios.usda.esr.mcp import server
from xippios.usda.esr.params import latest_market_year

TASKS = [getattr(tasks, name) for name in tasks.__all__]


def test_package_has_a_version() -> None:
    assert __version__


@pytest.mark.parametrize("task", TASKS, ids=tasks.__all__)
def test_task_is_a_sync_facade_with_an_agent_docstring(task: object) -> None:
    assert callable(task)
    assert hasattr(task, "async_fn"), "write the async function and derive the sync one with sync()"
    doc = inspect.getdoc(task) or ""
    assert doc, "task functions need a docstring: agents read it"
    assert doc.splitlines()[0].endswith("."), "the first line is one sentence"
    if inspect.signature(task).parameters:
        assert "Args:" in doc, "explain every parameter under Args: with valid-value examples"


def test_the_package_exports_the_tasks() -> None:
    assert get_exports is tasks.get_exports
    assert get_release_dates is tasks.get_release_dates
    assert tasks.__all__ == [
        "get_exports",
        "get_release_dates",
        "list_commodities",
        "list_countries",
        "list_regions",
        "list_units_of_measure",
    ]


def test_get_exports_has_a_note_only_cap_with_the_family_bounds() -> None:
    """The list tasks' caps are checked in ``test_lists.py``."""
    assert set(tasks.MCP_CAPS) == {"get_exports", "list_commodities", "list_countries"}
    cap = tasks.MCP_CAPS["get_exports"]
    assert (cap.max_rows, cap.max_bytes) == (200, 65_536), "a note-only cap"
    assert cap.note is not None
    assert "country_code" in cap.note


WHEAT_WHITE, COTTONSEED, RYE = 104, 1201, 501
CANADA = 1220
COUNTRY = "ESRData_GetCountryData"
ALL = "ESRData_GetAllCountriesData"
RELEASES = "ESRData_GetDataReleaseInfo"
EXPORTS = f"{BASE_URL}/api/esr/exports/commodityCode"


def test_get_exports_for_one_country(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_exports(WHEAT_WHITE, 2024, CANADA)
    assert sent_urls(route) == [f"{EXPORTS}/104/countryCode/1220/marketYear/2024"], "one call"
    assert len(result.data) == 54
    assert {(r.commodity_code, r.country_code, r.unit_id) for r in result.data} == {
        (104, 1220, UnitId.METRIC_TONS)
    }
    # wheat's market year 2024 runs June 2023 to May 2024; the last week ends in June
    assert result.data[0].week_ending_date == date(2023, 6, 1)
    assert result.meta.source == "usda-esr"
    assert result.meta.endpoint == "ESRData_GetCountryData"
    assert result.meta.request == {"commodity_code": 104, "market_year": 2024, "country_code": 1220}
    assert result.meta.vintage == "2024-06-06", "the latest weekEndingDate, an ISO date"
    assert result.meta.published_at is None
    assert result.meta.total is None
    assert result.meta.retrieved_at.tzinfo is not None


def test_get_exports_for_every_country(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture(ALL, "cottonseed_2024")
    result = tasks.get_exports(COTTONSEED, 2024)
    assert sent_urls(route) == [f"{EXPORTS}/1201/allCountries/marketYear/2024"]
    assert result.meta.endpoint == "ESRData_GetAllCountriesData"
    assert result.meta.request == {
        "commodity_code": 1201,
        "market_year": 2024,
        "country_code": None,
    }
    assert len(result.data) == 498
    assert len({r.country_code for r in result.data}) == 11
    assert result.meta.vintage == "2024-08-01", "cottonseed 2024 runs August 2023 to July 2024"
    assert result.meta.published_at is None


def test_valid_codes_without_exports_are_an_empty_result(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Recorded: rye for market year 2024 answers 200 with ``[]``. Empty means empty, not an
    error: no vintage, nothing else fetched."""
    route = replay_fixture(ALL, "rye_2024")
    result = tasks.get_exports(RYE, 2024)
    assert result.data == []
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.request == {"commodity_code": 501, "market_year": 2024, "country_code": None}
    assert route.call_count == 1


def test_vintage_is_none_for_empty_answers() -> None:
    assert tasks._vintage([]) is None
    assert tasks._release_vintage([]) is None


def test_get_release_dates(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture(RELEASES, "all")
    result = tasks.get_release_dates()
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/datareleasedates"]
    assert len(result.data) == 44
    assert result.meta.endpoint == "ESRData_GetDataReleaseInfo"
    assert result.meta.request == {}
    assert result.meta.vintage == "2026-10-22T08:30:42.670000", (
        "the latest releaseTimeStamp's isoformat(): upstream's two fractional digits render six"
    )
    assert result.meta.published_at is None, "the snapshot states no time zone"
    wheat = next(r for r in result.data if r.commodity_code == WHEAT_WHITE)
    assert (wheat.market_year, wheat.market_year_start, wheat.market_year_end) == (
        2027,
        date(2026, 6, 1),
        date(2027, 5, 31),
    )


def test_a_market_year_esr_lacks_is_not_found(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        tasks.get_exports(WHEAT_WHITE, 1900, CANADA)
    assert info.value.path == "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900"
    assert str(info.value) == (
        "ESR has no data for commodity 104, country 1220, market year 1900: GET "
        "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900 answered HTTP 404 "
        "with an empty body."
    )
    assert route.call_count == 1


def test_unknown_codes_and_future_years_are_refused_before_any_request(
    respx_mock: respx.MockRouter,
) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly. The
    recorded answers to 999, 9999 and 2099 are 200 ``[]``, which would read as no exports."""
    with pytest.raises(UnknownCode, match=r"1001 \(Flaxseed\)"):
        tasks.get_exports(999, 2024, CANADA)
    with pytest.raises(UnknownCode, match=r"9990 \(UNKNOWN\)"):
        tasks.get_exports(WHEAT_WHITE, 2024, 9999)
    with pytest.raises(UnknownCode):
        tasks.get_exports(999, 2024)
    with pytest.raises(InvalidRequestError, match="answers a future one"):
        tasks.get_exports(WHEAT_WHITE, 2099, CANADA)
    with pytest.raises(InvalidRequestError, match="answers a future one"):
        tasks.get_exports(WHEAT_WHITE, latest_market_year() + 1)
    with pytest.raises(InvalidRequestError, match="four-digit year"):
        tasks.get_exports(WHEAT_WHITE, 24)
    with pytest.raises(InvalidRequestError, match="must be an integer code"):
        tasks.get_exports("104", 2024)  # type: ignore[arg-type]
    assert not respx_mock.calls


@pytest.mark.parametrize(
    ("path", "call"),
    [
        ("104/countryCode/1220/marketYear/2024", lambda: tasks.get_exports(104, 2024, 1220)),
        ("104/allCountries/marketYear/2024", lambda: tasks.get_exports(104, 2024)),
    ],
    ids=["one_country", "every_country"],
)
def test_the_gateways_not_found_propagates_unchanged(
    respx_mock: respx.MockRouter, path: str, call: Callable[[], object]
) -> None:
    """NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body. Only ESR's empty 404 means
    "no data for this market year"; the gateway's 404 says the route is wrong and reaches
    the caller as classify raised it."""
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
    assert "ESR has no data for commodity" not in str(info.value)


@pytest.mark.anyio
async def test_mcp_tool_call_end_to_end(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    payload = await mcp_call(
        server,
        "usda_esr_get_exports",
        {"commodity_code": 104, "market_year": 2024, "country_code": 1220},
    )
    assert sent_urls(route) == [f"{EXPORTS}/104/countryCode/1220/marketYear/2024"]
    assert len(payload["data"]) == 54
    assert "note" not in payload, "one country fits the default cap"
    assert payload["data"][0] == {
        "commodity_code": 104,
        "country_code": 1220,
        "weekly_exports": 0,
        "accumulated_exports": 0,
        "outstanding_sales": 311,
        "gross_new_sales": 311,
        "current_my_net_sales": 311,
        "current_my_total_commitment": 311,
        "next_my_outstanding_sales": 0,
        "next_my_net_sales": 0,
        "unit_id": 1,
        "week_ending_date": "2023-06-01",
    }
    assert all(isinstance(row["accumulated_exports"], float) for row in payload["data"])
    assert payload["meta"]["endpoint"] == "ESRData_GetCountryData"
    assert payload["meta"]["request"] == {
        "commodity_code": 104,
        "market_year": 2024,
        "country_code": 1220,
    }
    assert payload["meta"]["vintage"] == "2024-06-06"
    assert payload["meta"]["published_at"] is None
    with pytest.raises(AssertionError, match=r"UnknownCode.*1001 \(Flaxseed\)"):
        await mcp_call(server, "usda_esr_get_exports", {"commodity_code": 999, "market_year": 2024})
    assert route.call_count == 1


@pytest.mark.anyio
async def test_every_country_over_mcp_is_cut_with_a_note_naming_country_code(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Cottonseed 2024 for every country, 498 rows, over MCP: cut at the family's bounds, and
    the cap's note names the tool's filter, ``country_code`` (conventions §8, ADR-0016)."""
    replay_fixture(ALL, "cottonseed_2024")
    payload = await mcp_call(
        server, "usda_esr_get_exports", {"commodity_code": 1201, "market_year": 2024}
    )
    shown = len(payload["data"])
    assert shown == 200, "the row bound comes first; 200 rows fit 64 KB"
    assert payload["note"] == (
        f"showing {shown} of 498 rows (cap: 200 rows or 65536 bytes); pass country_code, e.g. "
        "1220 (Canada), for one destination's weeks, up to 54 rows"
    )
    assert payload["meta"]["request"]["country_code"] is None
    assert payload["meta"]["vintage"] == "2024-08-01"


@pytest.mark.anyio
async def test_release_dates_over_mcp(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    replay_fixture(RELEASES, "all")
    payload = await mcp_call(server, "usda_esr_get_release_dates", {})
    assert len(payload["data"]) == 44
    assert "note" not in payload
    wheat = next(row for row in payload["data"] if row["commodity_code"] == 104)
    assert wheat == {
        "commodity_code": 104,
        "market_year_start": "2026-06-01",
        "market_year_end": "2027-05-31",
        "market_year": 2027,
        "release_time_stamp": "2026-10-22T08:30:42.670000",
    }
    assert payload["meta"]["vintage"] == "2026-10-22T08:30:42.670000"
    assert payload["meta"]["published_at"] is None


def test_quantities_are_json_numbers_over_http(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """ADR-0008: ``Decimal`` in Python, a JSON number on the wire, never a string; and the
    package's refusal of an unknown code is a 422 problem."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    replay_fixture(COUNTRY, "wheat_white_canada_2024")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    response = http.get(
        "/usda-esr/get_exports",
        params={"commodity_code": 104, "market_year": 2024, "country_code": 1220},
    )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 54
    assert rows[-1]["accumulated_exports"] == 16217
    assert isinstance(rows[-1]["accumulated_exports"], float)
    assert rows[-1]["week_ending_date"] == "2024-06-06"
    rejected = http.get(
        "/usda-esr/get_exports", params={"commodity_code": 999, "market_year": 2024}
    )
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "UnknownCode"
