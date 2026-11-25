"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import Answer, InvalidRequestError, NotFoundError, UnknownCode, parse
from xippios.core.testing import (
    fixture_path,
    load_fixture,
    mcp_call,
    mcp_call_text,
    sent_urls,
)
from xippios.usda.fas import NoDataForYear

from xippios.usda.esr import (
    api,
    tasks,
)
from xippios.usda.esr import mcp as esr_mcp
from xippios.usda.esr._client import BASE_URL
from xippios.usda.esr.enums import UnitId
from xippios.usda.esr.mcp import server
from xippios.usda.esr.models import DataReleaseInfo
from xippios.usda.esr.params import latest_market_year

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_package_exports_the_tasks() -> None:
    assert tasks.__all__ == [
        "get_exports",
        "get_release_dates",
        "get_weekly_series",
        "list_commodities",
        "list_countries",
        "list_regions",
        "list_units_of_measure",
    ]


def test_get_exports_has_a_paged_cap_that_keeps_the_newest_weeks() -> None:
    """The family's bounds, a note of its own, and a paged cap that keeps the last rows: a
    continuation is the cache's answer and costs upstream nothing (conventions §8; sdk-core
    ADR-0061, decision 9), and the rows run oldest week first, so a cut answer shows the
    newest weeks (https://github.com/xippios/sdk-usda-esr/issues/28). The list tasks' caps are
    checked in ``test_lists.py``, the weekly series' in ``test_series.py``."""
    assert set(tasks.MCP_CAPS) == {
        "get_exports",
        "get_release_dates",
        "get_weekly_series",
        "list_commodities",
        "list_countries",
    }
    cap = tasks.MCP_CAPS["get_exports"]
    assert (cap.max_rows, cap.max_bytes) == (200, 65_536), "the family's bounds"
    assert (cap.paged, cap.keep) == (True, "last")
    assert cap.note is not None
    assert "country_code" in cap.note


def test_get_release_dates_has_a_note_only_cap_naming_since() -> None:
    """A filtered tool names its filter in its cap's note even when its answer fits, as
    ``list_commodities`` names ``search`` (conventions §8, sdk-core ADR-0038)."""
    cap = tasks.MCP_CAPS["get_release_dates"]
    assert (cap.max_rows, cap.max_bytes) == (200, 65_536), "a note-only cap"
    assert cap.note is not None
    assert cap.note.startswith("pass since, ")
    assert '"2026-10-22T08:30:42.67"' in cap.note


WHEAT_WHITE, COTTONSEED, RYE = 104, 1201, 501
CANADA = 1220
COUNTRY = "get_country_data"
ALL = "get_all_countries_data"
RELEASES = "get_data_release_info"
EXPORTS = f"{BASE_URL}/api/esr/exports/commodityCode"
RELEASE_DATES = f"{BASE_URL}/api/esr/datareleasedates"
RELEASED = "2026-10-22T08:30:42.67"
"""The one ``releaseTimeStamp`` of all 44 records of ``get_data_release_info/all``, as printed."""
A_SECOND_EARLIER = "2026-10-22T08:30:41.67"


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
    assert result.meta.names == {
        "country_code": {"1220": "CANADA"},
        "unit_id": {"1": "Metric Tons"},
    }, "the codes of the rows, named by the record's model (sdk-usda-esr#30)"
    assert result.meta.notes == []
    assert result.meta.published_at is None
    assert result.meta.total is None
    assert result.meta.retrieved_at.tzinfo is not None


def test_get_exports_for_every_country(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture(ALL, "cottonseed_2024")
    result = tasks.get_exports(COTTONSEED, 2024)
    assert sent_urls(route) == [f"{EXPORTS}/1201/allCountries/marketYear/2024"]
    assert result.meta.endpoint == "ESRData_GetAllCountriesData"
    assert result.meta.request == {"commodity_code": 1201, "market_year": 2024}, (
        "country_code left None is left out (sdk-core ADR-0041, decision 3)"
    )
    assert len(result.data) == 498
    assert len({r.country_code for r in result.data}) == 11
    assert set(result.meta.names) == {"country_code", "unit_id"}
    assert result.meta.names["country_code"]["5880"] == "JAPAN", "every destination named"
    assert len(result.meta.names["country_code"]) == 11
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
    assert result.meta.request == {"commodity_code": 501, "market_year": 2024}
    assert route.call_count == 1


def test_vintage_is_none_for_empty_answers() -> None:
    assert tasks._vintage([]) is None
    assert tasks._newest_release([]) is None, "no release: vintage and published_at None"


def test_get_release_dates(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture(RELEASES, "all")
    result = tasks.get_release_dates()
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/datareleasedates"]
    assert len(result.data) == 44
    assert result.meta.endpoint == "ESRData_GetDataReleaseInfo"
    assert result.meta.request == {}
    assert result.meta.vintage == "2026-10-22T08:30:42.67", (
        "the latest releaseTimeStamp's text as upstream prints it, two fractional digits"
    )
    assert result.meta.published_at == datetime(2026, 10, 22, 8, 30, 42, 670000)
    assert result.meta.published_at.tzinfo is None, "the snapshot states no time zone"
    assert result.meta.published_at_naive is True
    wheat = next(r for r in result.data if r.commodity_code == WHEAT_WHITE)
    assert (wheat.market_year, wheat.market_year_start, wheat.market_year_end) == (
        2027,
        date(2026, 6, 1),
        date(2027, 5, 31),
    )


def test_get_release_dates_since_keeps_what_was_released_strictly_later(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """All 44 recorded records carry one release time: ``since`` equal to it keeps none, a
    second earlier keeps all; the vintage is the whole answer's either way
    (https://github.com/xippios/sdk-usda-esr/pull/9)."""
    route = replay_fixture(RELEASES, "all")
    whole = tasks.get_release_dates()
    same = tasks.get_release_dates(since=RELEASED)
    earlier = tasks.get_release_dates(since=A_SECOND_EARLIER)
    assert sent_urls(route) == [RELEASE_DATES], "one request, the cache's answer after it"
    assert len(whole.data) == 44
    assert whole.meta.request == {}, "since left None is left out (sdk-core ADR-0041, decision 3)"
    assert same.data == [], "a release at exactly since is not newer"
    assert same.meta.request == {"since": RELEASED}
    assert (same.meta.vintage, same.meta.published_at, same.meta.published_at_naive) == (
        RELEASED,
        datetime(2026, 10, 22, 8, 30, 42, 670000),
        True,
    ), "the whole answer's newest release, the marker to store for the next call"
    assert (same.meta.vintage, same.meta.published_at) == (
        whole.meta.vintage,
        whole.meta.published_at,
    )
    assert earlier.data == whole.data, "every record, unchanged, in upstream's order"
    assert earlier.meta.request == {"since": A_SECOND_EARLIER}
    assert earlier.meta.vintage == RELEASED
    assert len(tasks.get_release_dates(since="2026-10-22").data) == 44, "a date is its midnight"


def _no_releases(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """``api.get_data_release_info`` answering ``[]``, in memory (a function input, not a
    fixture file: that operation was never observed to answer empty); the list counts the
    calls."""
    calls: list[int] = []

    async def empty() -> Answer[list[DataReleaseInfo]]:
        calls.append(1)
        return Answer([], datetime.now(UTC))

    monkeypatch.setattr(api, "get_data_release_info", empty)
    return calls


def test_get_release_dates_since_over_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both markers are empty only when upstream lists nothing."""
    calls = _no_releases(monkeypatch)
    result = tasks.get_release_dates(since=RELEASED)
    assert result.data == []
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.published_at_naive is False
    assert result.meta.request == {"since": RELEASED}
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("since", "reason"),
    [
        ("not a time", "it is not an ISO date and time"),
        ("", "it is not an ISO date and time"),
        ("2026-10-22T08:30:42.67+00:00", "it carries a time zone"),
        ("2026-10-22T08:30:42Z", "it carries a time zone"),
        (datetime(2026, 10, 22, 8, 30, 42), "it is not an ISO date and time"),
    ],
    ids=["not_a_time", "empty", "utc_offset", "zulu", "a_datetime"],
)
def test_since_is_refused_before_the_request(
    replay_fixture: Callable[[str, str], respx.Route], since: object, reason: str
) -> None:
    route = replay_fixture(RELEASES, "all")
    with pytest.raises(InvalidRequestError) as info:
        tasks.get_release_dates(since=since)  # type: ignore[arg-type]
    message = str(info.value)
    assert message.startswith(
        "since must be the meta.vintage text of an earlier get_release_dates call, an ISO "
        "date and time without a time zone such as '2026-10-22T08:30:42.67'; got "
    ), "the package's own reader and words (sdk-core#473)"
    assert reason in message
    assert message.endswith(". Nothing was sent."), "a refusal before the request (§5)"
    assert sent_urls(route) == [], "refused before any request"


def _recorded_releases() -> list[DataReleaseInfo]:
    """The recorded release list parsed as the wrapper parses it, without a request."""
    body = json.loads(load_fixture(fixture_path(FIXTURES, RELEASES, "all")).response.body)
    return parse(
        list[DataReleaseInfo], body, source="usda-esr", endpoint="ESRData_GetDataReleaseInfo"
    )


def test_get_release_dates_of_one_commodity(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """``commodity_code`` is upstream's ``commodityCode``, compared by equality after the one
    request: the lookup of a commodity's market year is an argument of its list task, where
    ``get_market_year`` was a task of its own (conventions §14). The vintage stays the whole
    answer's newest release, as with ``since``."""
    route = replay_fixture(RELEASES, "all")
    result = tasks.get_release_dates(commodity_code=WHEAT_WHITE)
    assert sent_urls(route) == [RELEASE_DATES], "one request"
    (wheat,) = result.data
    assert (
        wheat.commodity_code,
        wheat.market_year,
        wheat.market_year_start,
        wheat.market_year_end,
    ) == (104, 2027, date(2026, 6, 1), date(2027, 5, 31))
    assert wheat.release_time_stamp == datetime(2026, 10, 22, 8, 30, 42, 670000)
    assert wheat.release_time_stamp_text == RELEASED
    recorded = next(r for r in _recorded_releases() if r.commodity_code == WHEAT_WHITE)
    assert wheat == recorded, "the record as upstream sent it: selected, not projected"
    assert result.meta.source == "usda-esr"
    assert result.meta.endpoint == "ESRData_GetDataReleaseInfo"
    assert result.meta.request == {"commodity_code": 104}
    assert result.meta.vintage == RELEASED, "the newest record's text as upstream prints it"
    assert result.meta.published_at == wheat.release_time_stamp
    assert result.meta.published_at.tzinfo is None
    assert result.meta.published_at_naive is True
    assert result.meta.total is None

    (corn,) = tasks.get_release_dates(commodity_code=401).data
    assert (corn.market_year, corn.market_year_start, corn.market_year_end) == (
        2027,
        date(2026, 9, 1),
        date(2027, 8, 31),
    ), "corn runs September to August"
    (beef,) = tasks.get_release_dates(commodity_code=1701).data
    assert (beef.market_year, beef.market_year_start, beef.market_year_end) == (
        2026,
        date(2026, 1, 1),
        date(2026, 12, 31),
    ), "beef muscle cuts, the calendar year"
    assert route.call_count == 1, "the cache answers the second and the third"


def test_the_release_dates_check_a_commodity_code_before_the_request(
    respx_mock: respx.MockRouter,
) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly."""
    with pytest.raises(UnknownCode, match=r"1001 \(Flaxseed\)"):
        tasks.get_release_dates(commodity_code=999)
    with pytest.raises(InvalidRequestError, match="is not an integer code"):
        tasks.get_release_dates(commodity_code="104")  # type: ignore[arg-type]
    assert not respx_mock.calls


def test_a_commodity_the_release_list_lacks_answers_the_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A packaged code the answer lacks: upstream dropped it, and the filter keeps nothing,
    the one answer of a list task for no data (conventions §5). Here the answer lists no
    commodity at all (``_no_releases``)."""
    calls = _no_releases(monkeypatch)
    result = tasks.get_release_dates(commodity_code=WHEAT_WHITE)
    assert result.data == []
    assert result.meta.request == {"commodity_code": WHEAT_WHITE}
    assert len(calls) == 1


def test_one_commodity_dropped_from_the_release_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded records without wheat white, in memory (a function input, not a fixture
    file): wheat white answers the empty list, every other commodity its record."""
    recorded = _recorded_releases()

    async def without_wheat_white() -> Answer[list[DataReleaseInfo]]:
        return Answer([r for r in recorded if r.commodity_code != WHEAT_WHITE], datetime.now(UTC))

    monkeypatch.setattr(api, "get_data_release_info", without_wheat_white)
    assert tasks.get_release_dates(commodity_code=WHEAT_WHITE).data == []
    (hrw,) = tasks.get_release_dates(commodity_code=101).data
    assert hrw.market_year == 2027


def test_a_market_year_esr_lacks_is_not_found(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        tasks.get_exports(WHEAT_WHITE, 1900, CANADA)
    assert info.value.path == "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900"
    assert info.value.source == "usda-esr", "raised again in the package's name"
    assert str(info.value) == (
        "ESR has no data for commodity 104, country 1220, market year 1900: GET "
        "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900 answered HTTP 404 "
        "with an empty body."
    )
    assert route.call_count == 1


def test_a_market_year_esr_lacks_is_not_found_for_every_country(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Recorded 2026-10-28: the every-country form answers 1900 with the same empty 404."""
    route = replay_fixture(ALL, "year_1900")
    with pytest.raises(NoDataForYear) as info:
        tasks.get_exports(WHEAT_WHITE, 1900)
    path = "/api/esr/exports/commodityCode/104/allCountries/marketYear/1900"
    assert info.value.path == path
    assert info.value.source == "usda-esr", "raised again in the package's name"
    assert str(info.value) == (
        f"ESR has no data for commodity 104, every country, market year 1900: GET {path} "
        "answered HTTP 404 with an empty body."
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
    with pytest.raises(InvalidRequestError, match="is not an integer code"):
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
    the caller as classify raised it.
    The body is composed from api.data.gov's documented answer (conventions §10, kind 2).
    """
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
    assert all(isinstance(row["accumulated_exports"], int) for row in payload["data"]), (
        "a Decimal without fractional digits is a JSON integer (sdk-core#478)"
    )
    assert payload["meta"]["names"]["country_code"] == {"1220": "CANADA"}
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
async def test_every_country_over_mcp_is_cut_to_its_newest_weeks_and_continues(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Cottonseed 2024 for every country, 498 rows, over MCP: cut at the family's bounds to
    the newest 200 rows, oldest first, with a note that names the tool's filter,
    ``country_code`` (conventions §8, sdk-core ADR-0038), and the call for the next rows, older
    ones. A continuation runs the task again, which the cache answers: one request in all
    (https://github.com/xippios/sdk-usda-esr/issues/28; sdk-core ADR-0047, ADR-0061, decision
    9). The last page names its rows alone."""
    route = replay_fixture(ALL, "cottonseed_2024")
    arguments: dict[str, int] = {"commodity_code": 1201, "market_year": 2024}
    payload = await mcp_call(server, "usda_esr_get_exports", dict(arguments))
    assert len(payload["data"]) == 200, "the row bound comes first; 200 rows fit 64 KB"
    assert payload["data"][-1]["week_ending_date"] == "2024-08-01", "the newest week kept"
    assert payload["note"] == (
        "showing rows 299 to 498 of 498 (cap: 200 rows or 65536 bytes); pass country_code, "
        "e.g. 1220 (Canada), for one destination's weeks, up to 54 rows; continue with "
        "offset=200"
    )
    older = await mcp_call(server, "usda_esr_get_exports", {**arguments, "offset": 200})
    assert older["note"].startswith("showing rows 99 to 298 of 498 ")
    assert older["note"].endswith("; continue with offset=400")
    oldest = await mcp_call(server, "usda_esr_get_exports", {**arguments, "offset": 400})
    assert len(oldest["data"]) == 98
    assert oldest["data"][0]["week_ending_date"] == "2023-08-03"
    assert oldest["note"] == "showing rows 1 to 98 of 498", "the last page: nothing after it"
    assert route.call_count == 1, "each continuation is the cache's answer"
    assert "country_code" not in payload["meta"]["request"]
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
    assert payload["meta"]["vintage"] == "2026-10-22T08:30:42.67"
    assert payload["meta"]["published_at"] == "2026-10-22T08:30:42.670000", "no zone added"
    assert payload["meta"]["published_at_naive"] is True


@pytest.mark.anyio
async def test_release_dates_since_over_mcp(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(RELEASES, "all")
    every = await mcp_call(server, "usda_esr_get_release_dates", {"since": A_SECOND_EARLIER})
    assert len(every["data"]) == 44
    assert every["meta"]["request"] == {"since": A_SECOND_EARLIER}, "verbatim, no credential"
    none_newer = await mcp_call(server, "usda_esr_get_release_dates", {"since": RELEASED})
    assert none_newer["data"] == []
    assert none_newer["meta"]["vintage"] == RELEASED, "the marker for the next call"
    assert none_newer["meta"]["published_at"] == "2026-10-22T08:30:42.670000"
    refused = await mcp_call_text(
        server, "usda_esr_get_release_dates", {"since": "2026-10-22T08:30:42.67+00:00"}
    )
    assert refused.startswith(
        "error: InvalidRequestError: since must be the meta.vintage text of an earlier "
        "get_release_dates call"
    )
    assert "it carries a time zone" in refused
    assert sent_urls(route) == [RELEASE_DATES], (
        "the cache answered the second; the refusal sent nothing"
    )


@pytest.mark.anyio
async def test_release_dates_of_one_commodity_over_mcp(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture(RELEASES, "all")
    payload = await mcp_call(server, "usda_esr_get_release_dates", {"commodity_code": 104})
    assert payload["data"] == [
        {
            "commodity_code": 104,
            "market_year_start": "2026-06-01",
            "market_year_end": "2027-05-31",
            "market_year": 2027,
            "release_time_stamp": "2026-10-22T08:30:42.670000",
        }
    ], "one record, the text not among its fields"
    assert "note" not in payload
    assert payload["meta"]["endpoint"] == "ESRData_GetDataReleaseInfo"
    assert payload["meta"]["request"] == {"commodity_code": 104}
    assert payload["meta"]["vintage"] == RELEASED
    assert payload["meta"]["published_at"] == "2026-10-22T08:30:42.670000", "no zone added"
    assert payload["meta"]["published_at_naive"] is True
    with pytest.raises(AssertionError, match=r"UnknownCode.*1001 \(Flaxseed\)"):
        await mcp_call(server, "usda_esr_get_release_dates", {"commodity_code": 999})
    assert sent_urls(route) == [RELEASE_DATES], "the unknown code sent nothing"


def test_release_dates_of_one_commodity_over_http(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    route = replay_fixture(RELEASES, "all")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    response = http.get("/usda-esr/get_release_dates", params={"commodity_code": 104})
    assert response.status_code == 200, response.text
    body = response.json()
    (wheat,) = body["data"]
    assert (wheat["market_year"], wheat["market_year_end"]) == (2027, "2027-05-31")
    assert (body["meta"]["vintage"], body["meta"]["published_at_naive"]) == (RELEASED, True)
    assert body["meta"]["request"] == {"commodity_code": 104}
    rejected = http.get("/usda-esr/get_release_dates", params={"commodity_code": 999})
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "UnknownCode"
    assert route.call_count == 1


def test_release_dates_over_http(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    """The HTTP envelope carries the naive release time with its flag, as MCP's does."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    replay_fixture(RELEASES, "all")
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/usda-esr/get_release_dates")
    assert response.status_code == 200, response.text
    meta = response.json()["meta"]
    assert (meta["vintage"], meta["published_at"], meta["published_at_naive"]) == (
        "2026-10-22T08:30:42.67",
        "2026-10-22T08:30:42.670000",
        True,
    )


def test_release_dates_since_over_http(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.esr.http import router

    route = replay_fixture(RELEASES, "all")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    response = http.get("/usda-esr/get_release_dates", params={"since": RELEASED})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"] == []
    assert (body["meta"]["vintage"], body["meta"]["request"]) == (RELEASED, {"since": RELEASED})
    earlier = http.get("/usda-esr/get_release_dates", params={"since": A_SECOND_EARLIER})
    assert len(earlier.json()["data"]) == 44
    refused = http.get("/usda-esr/get_release_dates", params={"since": "not a time"})
    assert refused.status_code == 422
    assert refused.json()["title"] == "InvalidRequestError"
    assert sent_urls(route) == [RELEASE_DATES], "the cache answered the second"


def test_quantities_are_json_numbers_over_http(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """``Decimal`` in Python, a JSON number on the wire, never a string (sdk-core ADR-0031,
    decision 1); and the package's refusal of an unknown code is a 422 problem."""
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
    assert isinstance(rows[-1]["accumulated_exports"], int), "a whole Decimal is an integer"
    assert rows[-1]["week_ending_date"] == "2024-06-06"
    rejected = http.get(
        "/usda-esr/get_exports", params={"commodity_code": 999, "market_year": 2024}
    )
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "UnknownCode"


def test_build_returns_the_tool_set_the_entry_point_serves() -> None:
    """``mcp.build()`` holds what ``tasks.py`` declares for the server: its caps and its
    instructions, ``MCP_INSTRUCTIONS``, and no option of its own (conventions §8; sdk-core
    ADR-0063, decision 7). Core's family check holds the rest of the package contract."""
    tools = esr_mcp.build()
    assert dict(tools.caps or {}) == dict(tasks.MCP_CAPS)
    assert tools.instructions == tasks.MCP_INSTRUCTIONS
    assert tools.instructions.startswith("USDA FAS Export Sales Reporting via xippios. ")
    assert (tools.add_options, tools.apply_options) == (None, None), "no options of its own"


def test_retrieved_at_is_the_answers_time_a_cache_hit_included(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """``meta.retrieved_at`` is the client's time of the answer (conventions §4): a second
    call that the cache answers carries the time its entry was stored."""
    route = replay_fixture(RELEASES, "all")
    first = tasks.get_release_dates()
    second = tasks.get_release_dates()
    assert route.call_count == 1
    assert second.meta.retrieved_at == first.meta.retrieved_at


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["get_exports"])
async def test_a_one_year_tool_says_an_empty_list_may_be_a_year_not_released(name: str) -> None:
    """The tool that fetches one market year reads no release list, and ESR answers a
    market year it has not released with ``[]``, as it answers one without exports: the
    description an agent reads, the task's docstring, names both readings of an empty list
    (conventions §4; sdk-core ADR-0041, decision 6;
    https://github.com/xippios/sdk-usda-esr/issues/18)."""
    tools = {tool.name: tool for tool in await server.list_tools()}
    description = " ".join((tools[f"usda_esr_{name}"].description or "").split())
    assert "a market year ESR has not released yet, which it answers alike" in description
    assert "no exports" in description or "without exports" in description
