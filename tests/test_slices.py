"""The wave 2 slices: the latest week, the top destinations, the weekly series.

Each replays a recorded answer and checks that the slice selects and orders upstream's
records without changing one (ADR-0003; Johannes, 2026-10-25). ``_recorded`` parses a
fixture the way the wrapper does, without a request, so a test compares with what
upstream sent while the task's own request is counted on its route. Nothing new is
recorded: the slices make the requests ``get_exports`` makes, and its fixtures serve them.
"""

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from xippios.core import InvalidRequestError, NotFoundError, parse
from xippios.core.testing import fixture_path, load_fixture, mcp_call, sent_urls

import xippios.usda.esr as package
from xippios.usda.esr import api, models, tasks
from xippios.usda.esr._client import BASE_URL
from xippios.usda.esr.errors import NoDataForYear, UnknownCode
from xippios.usda.esr.mcp import server
from xippios.usda.esr.models import CommodityData, ExportField

FIXTURES = Path(__file__).parent / "fixtures"
WHEAT_WHITE, COTTONSEED, RYE = 104, 1201, 501
CANADA = 1220
COUNTRY = "ESRData_GetCountryData"
ALL = "ESRData_GetAllCountriesData"
EXPORTS = f"{BASE_URL}/api/esr/exports/commodityCode"
SLICES = ["get_latest_week", "get_top_destinations", "get_weekly_series"]

LATEST = date(2024, 8, 1)
"""The newest week of ``cottonseed_2024``, whose 498 records span 53 weeks from 2023-08-03."""

LATEST_DESTINATIONS = [1220, 2010, 5170, 5180, 5230, 5520, 5700, 5800, 5830, 5880, 7140]
"""The 11 destinations of that week, in upstream's order: by code."""


def _recorded(endpoint: str, case: str) -> list[CommodityData]:
    """The recorded answer parsed as the wrapper parses it, without a request."""
    body = json.loads(load_fixture(fixture_path(FIXTURES, endpoint, case)).response.body)
    return parse(list[CommodityData], body, source="usda-esr", endpoint=endpoint)


def _latest_week_recorded() -> list[CommodityData]:
    return [r for r in _recorded(ALL, "cottonseed_2024") if r.week_ending_date == LATEST]


def _mount_recorded_404(respx_mock: respx.MockRouter, path: str) -> respx.Route:
    """Serve ESR's recorded empty 404 for market year 1900 at ``path``.

    ``year_1900`` was recorded on the one-country path (status 404, empty ``text/plain``
    body); the every-country form was not recorded. The recorded answer is moved, not
    written by hand, as sdk-usda-psd's slice tests do.
    """
    absent = load_fixture(fixture_path(FIXTURES, COUNTRY, "year_1900"))
    assert (absent.response.status, absent.response.content) == (404, b"")
    return respx_mock.get(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(
            absent.response.status,
            headers=absent.response.headers,
            content=absent.response.content,
        )
    )


def test_every_slice_is_exported() -> None:
    for name in SLICES:
        assert name in tasks.__all__
        assert name in package.__all__
        assert getattr(package, name) is getattr(tasks, name)
        assert name not in tasks.MCP_CAPS, "one week or one destination fits the default"
    assert "ExportField" in models.__all__


@pytest.mark.anyio
async def test_slice_tool_names_and_the_field_schema() -> None:
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert {f"usda_esr_{name}" for name in SLICES} <= set(tools)
    schema = tools["usda_esr_get_top_destinations"].input_schema
    assert schema["properties"]["field"] == {"$ref": "#/$defs/ExportField"}
    assert schema["$defs"]["ExportField"]["enum"] == [member.value for member in ExportField]
    assert schema["required"] == ["commodity_code", "market_year", "field"]


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
    assert result.meta.endpoint == ALL
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
    assert top.meta.endpoint == ALL
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


def test_get_weekly_series_is_one_destinations_weeks_oldest_first(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024)
    assert sent_urls(route) == [f"{EXPORTS}/104/countryCode/1220/marketYear/2024"], "one request"
    recorded = _recorded(COUNTRY, "wheat_white_canada_2024")
    weeks = [r.week_ending_date for r in recorded]
    assert weeks == sorted(weeks), "upstream already sends them oldest first"
    assert len(set(weeks)) == len(weeks) == 54
    assert result.data == recorded, "so the order is upstream's and nothing changed"
    assert (result.data[0].week_ending_date, result.data[-1].week_ending_date) == (
        date(2023, 6, 1),
        date(2024, 6, 6),
    )
    assert result.meta.source == "usda-esr"
    assert result.meta.endpoint == COUNTRY
    assert result.meta.request == {
        "commodity_code": 104,
        "country_code": 1220,
        "market_year": 2024,
    }
    assert result.meta.vintage == "2024-06-06", "the last week"
    assert result.meta.published_at is None
    assert result.meta.total is None


def test_weekly_series_orders_what_upstream_sends_out_of_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded records, reversed in memory (a function input, not a fixture file): the
    slice orders them by week, oldest first, and changes none."""
    recorded = _recorded(COUNTRY, "wheat_white_canada_2024")

    async def reversed_answer(*_: int) -> list[CommodityData]:
        return recorded[::-1]

    monkeypatch.setattr(api, "ESRData_GetCountryData", reversed_answer)
    result = tasks.get_weekly_series(WHEAT_WHITE, CANADA, 2024)
    assert result.data == recorded
    assert result.meta.vintage == "2024-06-06"


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


def test_the_weekly_series_names_a_market_year_esr_lacks(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 1900)
    assert str(info.value) == (
        "ESR has no data for commodity 104, country 1220, market year 1900: GET "
        "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900 answered HTTP 404 "
        "with an empty body."
    )
    assert route.call_count == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda: tasks.get_latest_week(WHEAT_WHITE, 1900),
        lambda: tasks.get_top_destinations(WHEAT_WHITE, 1900, ExportField.OUTSTANDING_SALES),
    ],
    ids=["get_latest_week", "get_top_destinations"],
)
def test_every_destination_slices_name_a_market_year_esr_lacks(
    respx_mock: respx.MockRouter, call: Callable[[], object]
) -> None:
    path = "/api/esr/exports/commodityCode/104/allCountries/marketYear/1900"
    route = _mount_recorded_404(respx_mock, path)
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
            lambda: tasks.get_weekly_series(104, 1220, 2024),
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
    with pytest.raises(InvalidRequestError, match="field must be one of upstream's"):
        tasks.get_top_destinations(COTTONSEED, 2024, 3)  # type: ignore[arg-type]

    with pytest.raises(UnknownCode, match=r"9990 \(UNKNOWN\)"):
        tasks.get_weekly_series(WHEAT_WHITE, 9999, 2024)
    with pytest.raises(UnknownCode, match="commodity_code"):
        tasks.get_weekly_series(999, CANADA, 2024)
    with pytest.raises(InvalidRequestError, match="must be an integer code"):
        tasks.get_weekly_series(WHEAT_WHITE, "1220", 2024)  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError, match="four-digit year"):
        tasks.get_weekly_series(WHEAT_WHITE, CANADA, 24)
    assert not respx_mock.calls


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
    assert payload["meta"]["endpoint"] == ALL
    assert payload["meta"]["vintage"] == "2024-08-01"
    assert payload["meta"]["published_at"] is None
    with pytest.raises(AssertionError, match=r"(?s)field.*Input should be 'weeklyExports'"):
        await mcp_call(
            server, "usda_esr_get_top_destinations", {**arguments, "field": "outstanding_sales"}
        )
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
        {"commodity_code": 104, "country_code": 1220, "market_year": 2024},
    )
    assert len(series["data"]) == 54
    assert "note" not in series, "54 weeks fit the default cap"
    assert series["data"][-1]["week_ending_date"] == series["meta"]["vintage"] == "2024-06-06"


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
