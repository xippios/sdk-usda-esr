"""The four list tasks answer from the packaged lists and never call upstream.

The packaged files were written from the same answers as those recorded in
``tests/fixtures/<operation>/all.json`` (``reference/README.md``), so a task returning
exactly the records parsed from that recording proves the package answers what upstream
answered. Every test here runs with ``respx`` active: a request no route matches fails
loudly, and each test checks that the tasks sent none. Where the recording is mounted, a
call would succeed silently; its route's call count shows that none is made.
"""

import dataclasses
import json
from collections import Counter
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import respx
from pydantic import BaseModel
from xippios.core.mcp import cap_result
from xippios.core.testing import ReplayFixture, load_fixture, mcp_call

import xippios.usda.esr as package
from xippios.usda.esr import tasks
from xippios.usda.esr.mcp import server
from xippios.usda.esr.models import Commodity, Country, Region, UnitOfMeasure

FIXTURES = Path(__file__).parent / "fixtures"
LISTS: list[tuple[str, str, str, type[BaseModel], int, dict[str, Any]]] = [
    # task, packaged list, operation it came from, model, records, meta.request unfiltered
    ("list_commodities", "commodities", "ESRData_GetCommodities", Commodity, 44, {"search": None}),
    (
        "list_countries",
        "countries",
        "ESRData_GetCountries",
        Country,
        211,
        {"region_id": None, "search": None},
    ),
    ("list_regions", "regions", "ESRData_GetRegions", Region, 12, {}),
    ("list_units_of_measure", "unitsOfMeasure", "ESRData_GetUnitsOfMeasure", UnitOfMeasure, 5, {}),
]
IDS = [task for task, *_ in LISTS]
DEFAULT_ROWS, DEFAULT_BYTES = 200, 65_536
"""The family's default MCP result cap (conventions §8)."""
WHEAT = [101, 102, 103, 104, 105, 106, 107, 201]
"""The commodities whose name holds "wheat": the six classes, All Wheat, Wheat Products."""


def _fetched(name: str) -> str:
    """``fetched`` as the packaged file stores it, read from the file itself."""
    path = resources.files("xippios.usda.esr").joinpath("reference", f"{name}.json")
    fetched = json.loads(path.read_text(encoding="utf-8"))["fetched"]
    assert isinstance(fetched, str)
    return fetched


def _recorded(endpoint: str, model: type[BaseModel]) -> list[Any]:
    """The records of ``tests/fixtures/<endpoint>/all.json``, parsed into ``model``."""
    body = json.loads(load_fixture(FIXTURES / endpoint / "all.json").response.body)
    return [model.model_validate(record) for record in body]


def test_every_list_task_is_exported() -> None:
    for task in IDS:
        assert task in tasks.__all__
        assert task in package.__all__
        assert getattr(package, task) is getattr(tasks, task)


@pytest.mark.anyio
@pytest.mark.respx(assert_all_called=False)
@pytest.mark.parametrize(("task", "name", "endpoint", "model", "count", "request_"), LISTS, ids=IDS)
async def test_list_answers_the_recorded_records_without_a_call(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
    task: str,
    name: str,
    endpoint: str,
    model: type[BaseModel],
    count: int,
    request_: dict[str, Any],
) -> None:
    """The recording is mounted, so a call would succeed silently; none is made."""
    route = replay_fixture(endpoint, "all")
    before = datetime.now(UTC)
    result = await getattr(tasks, f"{task}_async")()
    after = datetime.now(UTC)
    assert route.call_count == 0, f"{task} called upstream"
    assert not respx_mock.calls
    assert result.data == _recorded(endpoint, model), "same records, same values, upstream order"
    assert len(result.data) == count
    assert all(type(record) is model for record in result.data)
    assert result.meta.source == "usda-esr"
    assert result.meta.endpoint == endpoint
    assert result.meta.vintage == _fetched(name) == "2026-10-25"
    assert result.meta.published_at is None
    assert result.meta.total is None, "upstream reports no count (ADR-0012)"
    assert result.meta.request == request_
    assert before <= result.meta.retrieved_at <= after, "retrieved_at is when the task answered"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("task", "name", "endpoint", "request_"),
    [(task, name, endpoint, request_) for task, name, endpoint, _, _, request_ in LISTS],
    ids=IDS,
)
async def test_list_tool_end_to_end(
    respx_mock: respx.MockRouter,
    task: str,
    name: str,
    endpoint: str,
    request_: dict[str, Any],
) -> None:
    """Every list reaches an agent whole: ``list_countries`` through its own cap."""
    payload = await mcp_call(server, f"usda_esr_{task}", {})
    rows = [record.model_dump(mode="json") for record in getattr(tasks, task)().data]
    assert payload["data"] == rows
    assert "note" not in payload
    assert payload["meta"]["source"] == "usda-esr"
    assert payload["meta"]["endpoint"] == endpoint
    assert payload["meta"]["vintage"] == _fetched(name)
    assert payload["meta"]["published_at"] is None
    assert payload["meta"]["total"] is None
    assert payload["meta"]["request"] == request_
    assert not respx_mock.calls


def test_the_list_caps() -> None:
    """``list_countries`` has rows of its own and a note naming both filters;
    ``list_commodities`` keeps the family's bounds with a note naming ``search``; the
    filterless lists have no entry (conventions §8, ADR-0016; Johannes, 2026-10-25)."""
    countries = tasks.MCP_CAPS["list_countries"]
    assert (countries.max_rows, countries.max_bytes) == (250, DEFAULT_BYTES)
    assert countries.note is not None
    assert "region_id" in countries.note
    assert "search" in countries.note
    commodities = tasks.MCP_CAPS["list_commodities"]
    assert (commodities.max_rows, commodities.max_bytes) == (DEFAULT_ROWS, DEFAULT_BYTES)
    assert commodities.note is not None
    assert "search" in commodities.note
    assert "list_regions" not in tasks.MCP_CAPS
    assert "list_units_of_measure" not in tasks.MCP_CAPS


@pytest.mark.anyio
async def test_countries_over_mcp_are_whole_under_their_own_cap(
    respx_mock: respx.MockRouter,
) -> None:
    """211 countries, past the default cap of 200 rows: ``list_countries``'s own cap of
    250 lets every one through, 9990 UNKNOWN last, and every region and a search come
    back whole as well."""
    every = await mcp_call(server, "usda_esr_list_countries", {})
    countries = tasks.list_countries().data
    assert every["data"] == [country.model_dump(mode="json") for country in countries]
    assert len(every["data"]) == 211
    assert len(every["data"]) > DEFAULT_ROWS, "past the default cap"
    assert "note" not in every, "whole: nothing is cut, so no note"
    assert every["data"][-1]["country_code"] == 9990
    text = cap_result(tasks.list_countries(), tasks.MCP_CAPS["list_countries"])
    assert len(text.encode()) < DEFAULT_BYTES, "within the default byte bound it keeps"
    regions = Counter(country.region_id for country in countries)
    for region_id, count in regions.items():
        payload = await mcp_call(server, "usda_esr_list_countries", {"region_id": region_id})
        assert len(payload["data"]) == count, region_id
        assert "note" not in payload, region_id
        assert payload["meta"]["request"] == {"region_id": region_id, "search": None}
    united = await mcp_call(server, "usda_esr_list_countries", {"search": "united"})
    assert [row["country_code"] for row in united["data"]] == [4120, 5200, 7830]
    assert united["meta"]["request"] == {"region_id": None, "search": "united"}
    assert not respx_mock.calls


def test_the_country_note_is_what_an_agent_reads_when_the_list_outgrows_its_cap() -> None:
    """Not reachable with the packaged 211 countries; with the row bound lowered to the
    default the same cap shows the text an agent would read past 250 rows."""
    cap = dataclasses.replace(tasks.MCP_CAPS["list_countries"], max_rows=DEFAULT_ROWS)
    payload = json.loads(cap_result(tasks.list_countries(), cap))
    assert len(payload["data"]) == DEFAULT_ROWS
    assert payload["note"] == (
        "showing 200 of 211 rows (cap: 200 rows or 65536 bytes); pass region_id, e.g. 11 "
        '(WESTERN HEMISPHERE), or search, e.g. "korea" or "1220", to narrow by region or by '
        "code, name, description or GENC code"
    )


@pytest.mark.anyio
async def test_commodities_over_mcp_are_whole_and_search_narrows(
    respx_mock: respx.MockRouter,
) -> None:
    every = await mcp_call(server, "usda_esr_list_commodities", {})
    assert len(every["data"]) == 44
    assert "note" not in every
    assert every["data"][3] == {
        "commodity_code": 104,
        "commodity_name": "Wheat - White",
        "unit_id": 1,
    }
    wheat = await mcp_call(server, "usda_esr_list_commodities", {"search": "wheat"})
    assert [row["commodity_code"] for row in wheat["data"]] == WHEAT
    assert wheat["meta"]["request"] == {"search": "wheat"}
    assert not respx_mock.calls


def test_list_countries_by_region(respx_mock: respx.MockRouter) -> None:
    every = tasks.list_countries().data
    western = tasks.list_countries(region_id=11)
    assert len(western.data) == 40
    assert western.data[:3] == [c for c in every if c.region_id == 11][:3]
    assert [c.country_code for c in western.data[:3]] == [1010, 1220, 1610], "upstream order"
    assert western.data == [c for c in every if c.region_id == 11]
    assert western.meta.request == {"region_id": 11, "search": None}
    eastern = tasks.list_countries(region_id=3).data
    assert [c.country_code for c in eastern] == [4290, 4350]  # GDR, Czechoslovakia
    european_union = [c.country_code for c in tasks.list_countries(region_id=1).data]
    assert len(european_union) == 27
    assert european_union[0] == 1, "the aggregate itself, as upstream sends it"
    assert {4120, 4230} <= set(european_union), "UK; Belgium-Luxembourg as one code"
    croatia = tasks.list_countries(search="4791").data
    assert [c.region_id for c in croatia] == [2], "Croatia in OTHER EUROPE (Johannes, 2026-10-25)"
    region_ids = {r.region_id for r in tasks.list_regions().data}
    by_region = {rid: tasks.list_countries(region_id=rid).data for rid in region_ids}
    assert all(by_region.values()), "every region holds a country"
    assert sum(len(countries) for countries in by_region.values()) == 211
    assert not respx_mock.calls


def test_an_unknown_region_is_an_empty_list(respx_mock: respx.MockRouter) -> None:
    """No validation: a region no country carries has no countries, a correct answer."""
    unknown = tasks.list_countries(region_id=12)
    assert unknown.data == []
    assert unknown.meta.request == {"region_id": 12, "search": None}
    assert unknown.meta.vintage == "2026-10-25"
    assert tasks.list_countries(region_id=0).data == []
    assert not respx_mock.calls


def test_list_countries_search_by_code_or_name_ignoring_case(
    respx_mock: respx.MockRouter,
) -> None:
    united = tasks.list_countries(search="united")
    assert [(c.country_code, c.country_description.strip()) for c in united.data] == [
        (4120, "UNITED KINGDOM"),
        (5200, "UNITED ARAB EMIRATES"),
        (7830, "TANZANIA, UNITED REPUBLIC OF"),
    ]
    assert united.meta.request == {"region_id": None, "search": "united"}
    assert tasks.list_countries(search="UNITED").data == united.data
    assert tasks.list_countries(search="United").data == united.data
    assert [c.country_code for c in tasks.list_countries(search="korea").data] == [5790, 5800]
    assert [c.country_code for c in tasks.list_countries(search="1220").data] == [1220]
    assert [c.country_code for c in tasks.list_countries(search="122").data] == [1220], "digits"
    assert [c.country_code for c in tasks.list_countries(search="u king").data] == [4120], (
        "the short name"
    )
    both = tasks.list_countries(region_id=11, search="can")
    assert [c.country_code for c in both.data] == [1220, 2270, 2470]
    assert both.meta.request == {"region_id": 11, "search": "can"}
    assert tasks.list_countries(search="atlantis").data == []
    assert not respx_mock.calls


def test_list_countries_search_matches_the_genc_code(respx_mock: respx.MockRouter) -> None:
    """``"deu"`` occurs in no ESR code or name, only in Germany's GENC code; fields are
    matched one at a time, so ``"eu"`` finds the European Union by name and Germany by
    ``DEU``."""
    germany = tasks.list_countries(search="deu")
    assert [(c.country_code, c.genc_code) for c in germany.data] == [(4280, "DEU")]
    assert tasks.list_countries(search="DEU").data == germany.data
    assert [c.country_code for c in tasks.list_countries(search="eu").data] == [1, 4280]
    assert not respx_mock.calls


def test_list_countries_search_skips_a_null_genc_code(respx_mock: respx.MockRouter) -> None:
    """Upstream sends ``gencCode: null`` for 50 countries; a search passes over the null
    without raising and still finds them by code or name."""
    every = tasks.list_countries().data
    assert sum(c.genc_code is None for c in every) == 50
    european_union = tasks.list_countries(search="european union").data
    assert [(c.country_code, c.genc_code) for c in european_union] == [(1, None)]
    assert tasks.list_countries(search="none").data == [], "a null is not the text 'None'"
    assert len(tasks.list_countries(search="").data) == 211, "an empty search keeps every one"
    assert not respx_mock.calls


def test_countries_keep_upstream_padding(respx_mock: respx.MockRouter) -> None:
    canada = tasks.list_countries(search="1220").data
    assert canada == [
        Country(
            country_code=1220,
            country_name="CANADA  ",
            country_description="CANADA" + " " * 25,
            region_id=11,
            genc_code="CAN",
        )
    ]
    every = tasks.list_countries().data
    assert {c.country_code for c in every if len(c.country_name) != 8} == {9990}
    assert {c.country_code for c in every if len(c.country_description) != 31} == {1, 9990}
    assert not respx_mock.calls


def test_list_commodities_search(respx_mock: respx.MockRouter) -> None:
    wheat = tasks.list_commodities(search="wheat")
    assert [c.commodity_code for c in wheat.data] == WHEAT
    assert wheat.meta.request == {"search": "wheat"}
    assert tasks.list_commodities(search="WHEAT").data == wheat.data
    assert tasks.list_commodities(search="104").data == [
        Commodity(commodity_code=104, commodity_name="Wheat - White", unit_id=1)
    ]
    assert [c.commodity_code for c in tasks.list_commodities(search="14").data] == [
        1401,
        1402,
        1403,
        1404,
        1498,  # Rice - LG Rough: the code matches as text
        1499,
    ]
    cotton = [c.commodity_code for c in tasks.list_commodities(search="cotton").data]
    assert cotton == [1201, 1202, 1203, 1301, 1401, 1402, 1403, 1404]
    assert tasks.list_commodities(search="unobtainium").data == []
    assert not respx_mock.calls


def test_regions_and_units_as_upstream_sends_them(respx_mock: respx.MockRouter) -> None:
    regions = tasks.list_regions().data
    assert [(r.region_id, r.region_name) for r in regions][:2] == [(10, "AFRICA"), (7, "CHINA")]
    assert regions[-1] == Region(region_id=11, region_name="WESTERN HEMISPHERE")
    units = tasks.list_units_of_measure().data
    assert [(u.unit_id, u.unit_names) for u in units] == [
        (1, "Metric Tons"),
        (2, "Running Bales"),
        (3, "Pieces"),
        (4, "NUMBER"),
        (5, "Pounds"),
    ]
    assert not respx_mock.calls


def test_list_routes_are_whole_over_http(respx_mock: respx.MockRouter) -> None:
    """The cap is the MCP server's; HTTP answers every record."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    countries = http.get("/usda-esr/list_countries")
    assert countries.status_code == 200, countries.text
    assert len(countries.json()["data"]) == 211
    western = http.get("/usda-esr/list_countries", params={"region_id": 11}).json()
    assert len(western["data"]) == 40
    assert western["meta"]["request"] == {"region_id": 11, "search": None}
    assert western["meta"]["vintage"] == "2026-10-25"
    regions = http.get("/usda-esr/list_regions").json()
    assert len(regions["data"]) == 12
    assert regions["meta"]["request"] == {}
    assert not respx_mock.calls
