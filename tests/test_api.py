"""Replay tests for the endpoint wrappers (layer 1), against the answers recorded 2026-10-25.

What was sent is compared through ``sent_urls(route)``, never a request kept from
``route.calls``.
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

import pytest
import respx
from xippios.core import ValidationError, parse
from xippios.core.testing import sent_urls

from xippios.usda.esr import api
from xippios.usda.esr._client import BASE_URL
from xippios.usda.esr.enums import UnitId
from xippios.usda.esr.models import (
    Commodity,
    CommodityData,
    Country,
    DataReleaseInfo,
    Region,
    UnitOfMeasure,
)

pytestmark = pytest.mark.anyio


async def test_get_commodities(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture("ESRData_GetCommodities", "all")
    commodities = await api.ESRData_GetCommodities()
    assert len(commodities) == 44
    assert commodities[0] == Commodity(commodity_code=101, commodity_name="Wheat - HRW", unit_id=1)
    by_code = {c.commodity_code: c for c in commodities}
    assert by_code[104].commodity_name == "Wheat - White"
    assert by_code[401].commodity_name == "Corn"
    assert by_code[801].commodity_name == "Soybeans"
    assert by_code[1404] == Commodity(
        commodity_code=1404, commodity_name="All Upland Cotton", unit_id=UnitId.RUNNING_BALES
    )
    assert (min(by_code), max(by_code)) == (101, 1702)
    assert {c.unit_id for c in commodities} <= {member.value for member in UnitId}
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/commodities"]


async def test_get_countries(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture("ESRData_GetCountries", "all")
    countries = await api.ESRData_GetCountries()
    assert len(countries) == 211
    by_code = {c.country_code: c for c in countries}
    assert by_code[1220] == Country(
        country_code=1220,
        country_name="CANADA  ",
        country_description="CANADA" + " " * 25,
        region_id=11,
        genc_code="CAN",
    ), "names verbatim, upstream's padding kept"
    assert by_code[1].country_description == "EUROPEAN UNION - 27"
    assert by_code[1].genc_code is None
    assert by_code[9990].region_id == 99
    assert sum(c.genc_code is None for c in countries) == 50
    assert (min(by_code), max(by_code)) == (1, 9990)
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/countries"]


async def test_get_regions(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture("ESRData_GetRegions", "all")
    regions = await api.ESRData_GetRegions()
    assert len(regions) == 12
    assert regions[0] == Region(region_id=10, region_name="AFRICA")
    assert {r.region_id: r.region_name for r in regions}[99] == "UNKNOWN"
    assert sorted(r.region_id for r in regions) == [*range(1, 12), 99]
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/regions"]


async def test_every_country_names_a_listed_region(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    replay_fixture("ESRData_GetCountries", "all")
    replay_fixture("ESRData_GetRegions", "all")
    regions = {r.region_id for r in await api.ESRData_GetRegions()}
    assert {c.region_id for c in await api.ESRData_GetCountries()} == regions


async def test_get_units_of_measure(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture("ESRData_GetUnitsOfMeasure", "all")
    units = await api.ESRData_GetUnitsOfMeasure()
    assert units == [
        UnitOfMeasure(unit_id=1, unit_names="Metric Tons"),
        UnitOfMeasure(unit_id=2, unit_names="Running Bales"),
        UnitOfMeasure(unit_id=3, unit_names="Pieces"),
        UnitOfMeasure(unit_id=4, unit_names="NUMBER"),
        UnitOfMeasure(unit_id=5, unit_names="Pounds"),
    ]
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/unitsOfMeasure"]


async def test_get_data_release_info(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture("ESRData_GetDataReleaseInfo", "all")
    releases = await api.ESRData_GetDataReleaseInfo()
    assert len(releases) == 44
    wheat = next(r for r in releases if r.commodity_code == 104)
    assert wheat == DataReleaseInfo(
        commodity_code=104,
        market_year_start=date(2026, 6, 1),
        market_year_end=date(2027, 5, 31),
        market_year=2027,
        release_time_stamp=datetime(2026, 10, 22, 8, 30, 42, 670000),
    )
    assert wheat.release_time_stamp.tzinfo is None, "no zone invented"
    assert {r.release_time_stamp for r in releases} == {datetime(2026, 10, 22, 8, 30, 42, 670000)}
    by_code = {r.commodity_code: r for r in releases}
    # the market year is named by its end year and differs per commodity
    assert (by_code[401].market_year_start, by_code[401].market_year_end) == (
        date(2026, 9, 1),
        date(2027, 8, 31),
    )
    assert by_code[1404].market_year_start == date(2026, 8, 1)
    assert (by_code[1701].market_year, by_code[1701].market_year_start) == (2026, date(2026, 1, 1))
    assert all(r.market_year == r.market_year_end.year for r in releases)
    assert sent_urls(route) == [f"{BASE_URL}/api/esr/datareleasedates"]


async def test_the_release_list_names_every_commodity(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    replay_fixture("ESRData_GetDataReleaseInfo", "all")
    replay_fixture("ESRData_GetCommodities", "all")
    released = {r.commodity_code for r in await api.ESRData_GetDataReleaseInfo()}
    assert released == {c.commodity_code for c in await api.ESRData_GetCommodities()}


async def test_get_country_data(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    route = replay_fixture("ESRData_GetCountryData", "wheat_white_canada_2024")
    records = await api.ESRData_GetCountryData(104, 1220, 2024)
    assert len(records) == 54
    assert records[0] == CommodityData(
        commodity_code=104,
        country_code=1220,
        weekly_exports=Decimal(0),
        accumulated_exports=Decimal(0),
        outstanding_sales=Decimal(311),
        gross_new_sales=Decimal(311),
        current_my_net_sales=Decimal(311),
        current_my_total_commitment=Decimal(311),
        next_my_outstanding_sales=Decimal(0),
        next_my_net_sales=Decimal(0),
        unit_id=UnitId.METRIC_TONS,
        week_ending_date=date(2023, 6, 1),
    )
    assert records[-1].week_ending_date == date(2024, 6, 6)
    assert records[-1].accumulated_exports == Decimal(16217)
    assert [r.week_ending_date for r in records] == sorted(r.week_ending_date for r in records)
    assert sent_urls(route) == [
        f"{BASE_URL}/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/2024"
    ]


async def test_get_all_countries_data(replay_fixture: Callable[[str, str], respx.Route]) -> None:
    """``allCountries``: one record per destination and week, no paging. Cottonseed 2024:
    498 records for 11 destinations, 139,119 bytes of JSON."""
    route = replay_fixture("ESRData_GetAllCountriesData", "cottonseed_2024")
    records = await api.ESRData_GetAllCountriesData(1201, 2024)
    assert len(records) == 498
    destinations = {r.country_code for r in records}
    assert len(destinations) == 11
    assert {1220, 2010, 5880} <= destinations
    assert {r.commodity_code for r in records} == {1201}
    assert {r.unit_id for r in records} == {UnitId.METRIC_TONS}
    assert min(r.current_my_net_sales for r in records) == Decimal(-1615), "net sales can be < 0"
    # cottonseed's market year 2024 runs August 2023 to July 2024
    weeks = {r.week_ending_date for r in records}
    assert (min(weeks), max(weeks), len(weeks)) == (date(2023, 8, 3), date(2024, 8, 1), 53)
    assert sent_urls(route) == [
        f"{BASE_URL}/api/esr/exports/commodityCode/1201/allCountries/marketYear/2024"
    ]


async def test_valid_codes_without_exports_are_an_empty_list(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    route = replay_fixture("ESRData_GetAllCountriesData", "rye_2024")
    assert await api.ESRData_GetAllCountriesData(501, 2024) == []
    assert route.call_count == 1


async def test_quantities_are_whole_numbers_as_recorded(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    replay_fixture("ESRData_GetAllCountriesData", "cottonseed_2024")
    records = await api.ESRData_GetAllCountriesData(1201, 2024)
    quantities = [
        value
        for record in records
        for value in record.model_dump().values()
        if isinstance(value, Decimal)
    ]
    assert len(quantities) == 8 * 498
    assert all(value == value.to_integral_value() for value in quantities)


def test_records_serialise_snake_case_with_numbers_and_iso_dates() -> None:
    record = parse(
        CommodityData,
        {
            "commodityCode": 104,
            "countryCode": 1220,
            "weeklyExports": 0,
            "accumulatedExports": 16217,
            "outstandingSales": 0,
            "grossNewSales": 0,
            "currentMYNetSales": -5,
            "currentMYTotalCommitment": 16217,
            "nextMYOutstandingSales": 883,
            "nextMYNetSales": 0,
            "unitId": 1,
            "weekEndingDate": "2024-06-06T00:00:00",
        },
        source="usda-esr",
        endpoint="ESRData_GetCountryData",
    )
    dumped = record.model_dump(mode="json")
    assert dumped["week_ending_date"] == "2024-06-06"
    assert dumped["accumulated_exports"] == 16217
    assert isinstance(dumped["accumulated_exports"], float), "a JSON number (ADR-0008)"
    assert dumped["current_my_net_sales"] == -5
    assert set(dumped) == set(CommodityData.model_fields)


def test_a_week_ending_date_with_a_time_fails_the_answer() -> None:
    """pydantic takes a midnight for a ``date`` and refuses any other time, so a time ESR
    might start sending would fail loudly instead of being dropped."""
    with pytest.raises(ValidationError, match="weekEndingDate"):
        parse(
            CommodityData,
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
                "unitId": 1,
                "weekEndingDate": "2024-06-06T08:30:00",
            },
            source="usda-esr",
            endpoint="ESRData_GetCountryData",
        )
