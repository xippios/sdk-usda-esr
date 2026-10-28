"""Packaged reference lists, their enum and the argument checks built on them."""

import ast
import importlib.util
import inspect
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from xippios.core import InvalidRequestError, PackagedList, UnknownCode, parse
from xippios.core.http import status_for
from xippios.core.testing import load_fixture

from xippios.usda.esr import enums
from xippios.usda.esr.models import Commodity, CommodityData, Country, Region, UnitOfMeasure
from xippios.usda.esr.params import (
    PACKAGE,
    PACKAGED_LISTS,
    latest_market_year,
    validate_commodity_code,
    validate_country_code,
    validate_market_year,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_reference.py"
SOURCES = {
    # packaged list: the operation it came from, its wrapper (the fixture directory), model
    "commodities": ("ESRData_GetCommodities", "get_commodities", Commodity),
    "countries": ("ESRData_GetCountries", "get_countries", Country),
    "regions": ("ESRData_GetRegions", "get_regions", Region),
    "unitsOfMeasure": ("ESRData_GetUnitsOfMeasure", "get_units_of_measure", UnitOfMeasure),
}
FETCHED = {
    "commodities": datetime(2026, 10, 28, 19, 19, 51, tzinfo=UTC),
    "countries": datetime(2026, 10, 28, 19, 19, 52, tzinfo=UTC),
    "regions": datetime(2026, 10, 28, 19, 19, 53, tzinfo=UTC),
    "unitsOfMeasure": datetime(2026, 10, 28, 19, 19, 53, tzinfo=UTC),
}
"""The packaged lists' ``fetched``, each list's UTC time of the refresh to the second, as
``PackagedList.write`` writes it (ADR-0022, amendment 2026-10-27, point 1)."""


def _recorded(wrapper: str, case: str) -> list[dict[str, object]]:
    body: list[dict[str, object]] = json.loads(
        load_fixture(FIXTURES / wrapper / f"{case}.json").response.body
    )
    return body


def _records(name: str) -> list[dict[str, object]]:
    return PackagedList.load(PACKAGE, name).records


def _refresh_script() -> ModuleType:
    """``scripts/refresh_reference.py``, loaded without running it: no request, no key."""
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _endpoint_literals(wrapper: Callable[[], object]) -> list[object]:
    """Every ``endpoint=`` the wrapper's module passes, read from its source."""
    tree = ast.parse(inspect.getsource(sys.modules[wrapper.__module__]))
    return [
        keyword.value.value if isinstance(keyword.value, ast.Constant) else keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "endpoint"
    ]


def test_every_packaged_list_loads_and_parses() -> None:
    assert set(PACKAGED_LISTS) == set(SOURCES)
    for name, (endpoint, _, model) in SOURCES.items():
        packaged = PackagedList.load(PACKAGE, name)
        assert (packaged.param, packaged.endpoint) == (name, endpoint)
        assert packaged.fetched == FETCHED[name], name
        parsed = parse(list[model], packaged.records, source="usda-esr", endpoint=endpoint)  # type: ignore[valid-type]
        assert parsed, name


def test_the_refresh_script_names_each_lists_upstream_operation() -> None:
    """The script writes a list's ``endpoint`` from the operation its entry names, not from
    the wrapper's name (conventions 1.22 §2), so a refresh cannot drift from the verbatim
    ``operationId``: the entry's operation is the packaged file's ``endpoint``, the one
    ``endpoint=`` literal its wrapper passes and the first line of the wrapper's docstring;
    the wrapper names the list's fixture directory (conventions §10)."""
    script = _refresh_script()
    assert script.LISTS == {}, "ESR publishes no value list"
    entries: dict[str, tuple[str, Callable[[], object]]] = {
        **{name: (operation, fetch) for name, (operation, fetch) in script.TABLES.items()},
        **{name: (operation, fetch) for name, (operation, fetch, _, _) in script.ID_LISTS.items()},
    }
    assert set(entries) == set(PACKAGED_LISTS) == set(SOURCES)
    for name, (operation, fetch) in entries.items():
        assert (operation, fetch.__name__) == SOURCES[name][:2], name
        assert (FIXTURES / fetch.__name__ / "all.json").is_file(), name
        assert operation == PackagedList.load(PACKAGE, name).endpoint, name
        assert _endpoint_literals(fetch) == [operation], name
        assert (fetch.__doc__ or "").splitlines()[0] == f"Call ``{operation}``.", name


def test_packaged_lists_equal_the_recorded_answers() -> None:
    """Fetched live on 2026-10-28, three days after the recordings; the records are the same."""
    for name, (_, wrapper, _) in SOURCES.items():
        assert _records(name) == _recorded(wrapper, "all"), name


def test_the_enum_matches_the_packaged_units() -> None:
    assert enums.__all__ == ["UnitId"]
    units = _records("unitsOfMeasure")
    assert [(m.value, m.name) for m in enums.UnitId] == [
        (1, "METRIC_TONS"),
        (2, "RUNNING_BALES"),
        (3, "PIECES"),
        (4, "NUMBER"),
        (5, "POUNDS"),
    ]
    assert [m.value for m in enums.UnitId] == [r["unitId"] for r in units]


def test_enum_members_compare_equal_to_upstream_ints() -> None:
    record = UnitOfMeasure.model_validate({"unitId": 2, "unitNames": "Running Bales"})
    assert record.unit_id == enums.UnitId.RUNNING_BALES
    assert enums.UnitId(1) is enums.UnitId.METRIC_TONS


def test_every_recorded_unit_id_is_in_the_packaged_list() -> None:
    """Reference-data freshness, not a model constraint: the models keep ``unit_id`` a plain
    ``int`` so a new upstream unit never fails an answer. When this fails, a recorded
    answer names a unit the packaged list lacks: run ``/refresh-reference-data``."""
    units = {member.value for member in enums.UnitId}
    assert {r["unitId"] for r in _records("commodities")} <= units
    for wrapper, case in [
        ("get_country_data", "wheat_white_canada_2024"),
        ("get_all_countries_data", "cottonseed_2024"),
    ]:
        assert {r["unitId"] for r in _recorded(wrapper, case)} <= units, case


def test_every_recorded_destination_is_in_the_packaged_list() -> None:
    countries = {r["countryCode"] for r in _records("countries")}
    destinations = {
        r["countryCode"] for r in _recorded("get_all_countries_data", "cottonseed_2024")
    }
    assert destinations <= countries


def test_a_unit_the_list_lacks_still_parses() -> None:
    record = CommodityData.model_validate(
        {
            "commodityCode": 104,
            "countryCode": 1220,
            "weeklyExports": 0,
            "accumulatedExports": 0,
            "outstandingSales": 0,
            "grossNewSales": 0,
            "currentMYNetSales": 0,
            "currentMYTotalCommitment": 0,
            "nextMYOutstandingSales": 0,
            "nextMYNetSales": 0,
            "unitId": 99,
            "weekEndingDate": "2024-06-06T00:00:00",
        }
    )
    assert record.unit_id == 99
    assert 99 not in {member.value for member in enums.UnitId}


@pytest.mark.parametrize("code", [104, 101, 401, 801, 1404, 1702])
def test_known_commodity_codes_pass(code: int) -> None:
    assert validate_commodity_code(code) == code


def test_the_recorded_unknown_commodity_is_refused_naming_the_nearest() -> None:
    with pytest.raises(UnknownCode) as info:
        validate_commodity_code(999)
    error = info.value
    assert isinstance(error, InvalidRequestError)
    assert status_for(error) == 422
    assert (error.param, error.value, error.list_name) == ("commodity_code", 999, "commodities")
    assert error.fetched == FETCHED["commodities"]
    assert error.closest == ((1001, "Flaxseed"), (902, "Soybean Oil"))
    assert error.source == "usda-esr"
    assert error.message == (
        "999 is not a commodity_code in the packaged commodities list (fetched 2026-10-28). "
        "Did you mean 1001 (Flaxseed), 902 (Soybean Oil)? ESR answers unknown codes with an "
        "empty result, so the package refuses them. If upstream added it since, the packaged "
        "list needs a refresh (/refresh-reference-data)."
    )


def test_a_stray_digit_leads_to_the_code_by_its_digits() -> None:
    with pytest.raises(UnknownCode) as info:
        validate_commodity_code(1040)
    assert (104, "Wheat - White") in info.value.closest


@pytest.mark.parametrize("code", [1220, 1, 2010, 5880, 9990])
def test_known_country_codes_pass(code: int) -> None:
    assert validate_country_code(code) == code


def test_the_recorded_unknown_country_is_refused_naming_the_nearest() -> None:
    with pytest.raises(UnknownCode) as info:
        validate_country_code(9999)
    assert info.value.closest[0] == (9990, "UNKNOWN")
    assert "9999 is not a country_code in the packaged countries list" in info.value.message


def test_swapped_digits_lead_to_the_country() -> None:
    with pytest.raises(UnknownCode) as info:
        validate_country_code(1202)
    assert info.value.closest[0] == (1220, "CANADA"), "names without upstream's padding"


def test_a_name_instead_of_a_code_is_refused_naming_codes_by_name() -> None:
    with pytest.raises(InvalidRequestError, match="must be an integer code") as commodity:
        validate_commodity_code("wheat")  # type: ignore[arg-type]
    assert not isinstance(commodity.value, UnknownCode)
    assert "By name: 101 (Wheat - HRW), 102 (Wheat - SRW), 103 (Wheat - HRS)." in str(
        commodity.value
    )
    with pytest.raises(InvalidRequestError, match=r"By name: 1220 \(CANADA\)"):
        validate_country_code("Canada")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["104", True, False, 104.0, None])
def test_codes_that_are_not_integers_are_refused(value: object) -> None:
    with pytest.raises(InvalidRequestError, match="commodity_code must be an integer code") as info:
        validate_commodity_code(value)  # type: ignore[arg-type]
    if value == "104":
        assert "Pass it as the integer 104." in str(info.value)


def test_the_latest_market_year_is_this_year_plus_two() -> None:
    assert latest_market_year() == datetime.now(UTC).year + 2


def test_the_latest_market_year_covers_the_release_list_and_the_next_year() -> None:
    """The release list's latest market year (2027 on 2026-10-25), and the one after it."""
    years = [r["marketYear"] for r in _recorded("get_data_release_info", "all")]
    assert all(isinstance(year, int) for year in years)
    latest = max(int(str(year)) for year in years)
    assert latest == 2027
    assert latest + 1 <= latest_market_year()


@pytest.mark.parametrize("year", [2024, 1999, 1900, 1000])
def test_four_digit_market_years_pass(year: int) -> None:
    """1900 passes: ESR answers it with HTTP 404, ``NoDataForYear``, which says so itself."""
    assert validate_market_year(year) == year


def test_the_latest_market_year_passes_and_the_next_is_refused() -> None:
    latest = latest_market_year()
    assert validate_market_year(latest) == latest
    with pytest.raises(InvalidRequestError, match=f"no later than {latest}"):
        validate_market_year(latest + 1)


def test_a_future_market_year_is_refused_as_future() -> None:
    """2099 is recorded: ESR answers a future market year with HTTP 200 and ``[]``."""
    with pytest.raises(InvalidRequestError, match=f"no later than {latest_market_year()}") as info:
        validate_market_year(2099)
    assert "answers a future one with an empty result" in info.value.message
    assert "four-digit" not in info.value.message


def test_a_refusal_names_the_parameter_the_year_came_in() -> None:
    """``market_year`` by default, as every task with one market year has it; the weekly
    series passes ``start_year`` or ``end_year``, as ``UnknownCode`` names its ``param``."""
    with pytest.raises(InvalidRequestError) as default:
        validate_market_year(24)
    assert default.value.message.startswith("market_year must be a four-digit year no later")
    with pytest.raises(InvalidRequestError) as start:
        validate_market_year(24, name="start_year")
    assert start.value.message.startswith("start_year must be a four-digit year no later")
    assert "market_year must" not in start.value.message
    with pytest.raises(InvalidRequestError) as end:
        validate_market_year(2099, name="end_year")
    assert end.value.message.startswith(
        f"end_year must be no later than {latest_market_year()}, the current year plus two, "
        "got 2099."
    )
    assert validate_market_year(2024, name="start_year") == 2024


@pytest.mark.parametrize("year", [24, 999, 10000, -2024, True, 2024.0])
def test_a_market_year_that_is_not_four_digits_is_refused_as_such(year: int) -> None:
    """The shape reason, not the future one: 10000 is a five-digit year before it is a future
    one, and ``True`` and ``2024.0`` are not integers."""
    with pytest.raises(InvalidRequestError, match="must be a four-digit year") as info:
        validate_market_year(year)
    assert f"got {year!r}" in info.value.message
    assert "future" not in info.value.message
