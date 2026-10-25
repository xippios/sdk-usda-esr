"""Pydantic models mirroring USDA FAS Export Sales Reporting payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. Where upstream spells a field differently,
``Field(validation_alias=...)`` accepts that spelling on input; never ``alias=``, which the
adapters would serialise, handing agents the upstream spelling. Within-source hygiene only:
dates become ``datetime.date``, numbers become numbers, upstream enumerations become
``StrEnum``, and an enumeration of integer ids ``IntEnum``. No cross-source normalisation
(ADR-0003): an upstream concept stays an upstream concept.

These read models stay faithful, documented personal identifiers included (``ssn``,
``iban`` and their like). The projections tasks return leave those out, a write task does
not echo one in ``meta.request``, and fixtures never carry their values (ADR-0017).

The snapshot types every ESR response as ``object`` and defines no schemas
(``definitions`` is empty in ``docs/upstream/openapi/portal-document.json``). The record
shapes below therefore come from the recorded answers of 2026-10-25, each named in its
model's docstring; every field is an assumption from that fixture. No ESR record carries a
personal identifier. Codes and ids are integers, as the snapshot types the path parameters
(``int32``) and as every recorded record carries them; ``unit_id`` stays a plain ``int``,
not ``enums.UnitId``, so that a unit ESR adds before the packaged lists are refreshed does
not fail an answer, and ``UnitId`` members compare equal to it.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field
from xippios.core import UpstreamModel

__all__ = [
    "Commodity",
    "CommodityData",
    "Country",
    "DataReleaseInfo",
    "Region",
    "UnitOfMeasure",
]


class Commodity(UpstreamModel):
    """One record of ``ESRData_GetCommodities`` (``GET /api/esr/commodities``).

    Shape from ``tests/fixtures/ESRData_GetCommodities/all.json`` (44 records, codes 101
    to 1702).

    Attributes:
        commodity_code: ``commodityCode``, an integer, e.g. ``104``.
        commodity_name: ``commodityName``, e.g. ``"Wheat - White"``.
        unit_id: ``unitId``, the unit ESR reports the commodity in, e.g. ``1`` (Metric
            Tons), ``2`` (Running Bales) for cotton; ``enums.UnitId`` names it.
    """

    commodity_code: int = Field(validation_alias="commodityCode")
    commodity_name: str = Field(validation_alias="commodityName")
    unit_id: int = Field(validation_alias="unitId")


class Country(UpstreamModel):
    """One record of ``ESRData_GetCountries`` (``GET /api/esr/countries``).

    Shape from ``tests/fixtures/ESRData_GetCountries/all.json`` (211 records, codes 1 to
    9990, 50 of them without a GENC code). Both names are kept verbatim, padding included:
    upstream pads every ``countryName`` but ``"UNKNOWN"`` with spaces to eight characters,
    and every ``countryDescription`` but those of ``1`` and ``9990`` to 31.

    Attributes:
        country_code: ``countryCode``, ESR's integer code (not ISO), e.g. ``1220``
            (Canada); ``1`` is the European Union aggregate, ``9990`` unknown.
        country_name: ``countryName``, ESR's short name, e.g. ``"CANADA  "``.
        country_description: ``countryDescription``, the full name, e.g.
            ``"CANADA                         "``.
        region_id: ``regionId``, a region of ``ESRData_GetRegions``, e.g. ``11``
            (Western Hemisphere).
        genc_code: ``gencCode``, three characters, e.g. ``"CAN"``; ``None`` where upstream
            sends ``null`` (the European Union aggregate, ``1``, among others).
    """

    country_code: int = Field(validation_alias="countryCode")
    country_name: str = Field(validation_alias="countryName")
    country_description: str = Field(validation_alias="countryDescription")
    region_id: int = Field(validation_alias="regionId")
    genc_code: str | None = Field(validation_alias="gencCode")


class Region(UpstreamModel):
    """One record of ``ESRData_GetRegions`` (``GET /api/esr/regions``).

    Shape from ``tests/fixtures/ESRData_GetRegions/all.json`` (12 records, ids 1 to 11 and
    99, in upstream's alphabetical order of names).

    Attributes:
        region_id: ``regionId``, an integer, e.g. ``11``.
        region_name: ``regionName``, e.g. ``"WESTERN HEMISPHERE"``; ``99`` is
            ``"UNKNOWN"``.
    """

    region_id: int = Field(validation_alias="regionId")
    region_name: str = Field(validation_alias="regionName")


class UnitOfMeasure(UpstreamModel):
    """One record of ``ESRData_GetUnitsOfMeasure`` (``GET /api/esr/unitsOfMeasure``).

    Shape from ``tests/fixtures/ESRData_GetUnitsOfMeasure/all.json`` (5 records). The name
    field is plural upstream, ``unitNames``, and stays so here.

    Attributes:
        unit_id: ``unitId``, an integer, e.g. ``1``.
        unit_names: ``unitNames``, e.g. ``"Metric Tons"``, ``"Running Bales"``.
    """

    unit_id: int = Field(validation_alias="unitId")
    unit_names: str = Field(validation_alias="unitNames")


class DataReleaseInfo(UpstreamModel):
    """One record of ``ESRData_GetDataReleaseInfo`` (``GET /api/esr/datareleasedates``).

    Shape from ``tests/fixtures/ESRData_GetDataReleaseInfo/all.json``: 44 records, one per
    commodity, each naming the commodity's current market year and the time of the last
    release of its export data. A market year is named by the year it ends in: wheat's
    ``marketYear`` 2027 runs from 2026-06-01 to 2027-05-31. Market years differ per
    commodity, as this list shows: the wheat classes, barley, oats and rye run June to
    May; corn, sorghum and soybeans September to August; cotton, cottonseed and rice
    August to July; soybean meal and oil October to September; hides, skins, beef and pork
    the calendar year. Nothing is re-based.

    Upstream sends the start and end as ``"2026-06-01T00:00:00"``, a midnight with no zone,
    parsed to ``date`` (pydantic accepts a zero time for a date and refuses any other, so
    a time upstream starts sending would fail the answer rather than be dropped).
    ``releaseTimeStamp`` (``"2026-10-22T08:30:42.67"``) is a naive ``datetime``: the
    snapshot names no time zone, so none is invented, and it never becomes
    ``meta.published_at``.

    Attributes:
        commodity_code: ``commodityCode``, e.g. ``104`` (Wheat - White).
        market_year_start: ``marketYearStart``, first day of the market year, e.g.
            ``date(2026, 6, 1)``.
        market_year_end: ``marketYearEnd``, last day, e.g. ``date(2027, 5, 31)``.
        market_year: ``marketYear``, ESR's market year, named by its end year, e.g.
            ``2027``.
        release_time_stamp: ``releaseTimeStamp``, the last release of the commodity's
            export data, naive, e.g. ``datetime(2026, 10, 22, 8, 30, 42, 670000)``.
    """

    commodity_code: int = Field(validation_alias="commodityCode")
    market_year_start: date = Field(validation_alias="marketYearStart")
    market_year_end: date = Field(validation_alias="marketYearEnd")
    market_year: int = Field(validation_alias="marketYear")
    release_time_stamp: datetime = Field(validation_alias="releaseTimeStamp")


class CommodityData(UpstreamModel):
    """One weekly export record of ``ESRData_GetCountryData`` and ``ESRData_GetAllCountriesData``.

    The snapshot calls these "Commodity Data records" of the "Commodity Data End point"
    (the summaries of the commodities, countries and units operations) and "US Export
    records" (the summaries of the two exports operations); the model takes the first
    name. Both operations answer the same record: one per destination country and week of
    the market year, in upstream order. Shape from the fixtures
    ``ESRData_GetCountryData/wheat_white_canada_2024`` (54 records) and
    ``ESRData_GetAllCountriesData/cottonseed_2024`` (498 records, 11 destinations).

    The eight quantities arrive as JSON integers in the unit ``unit_id`` names (metric
    tons for wheat) and become ``Decimal`` (ADR-0008, the package's decision): every
    recorded value is a whole number, and a ``Decimal`` keeps any fraction upstream may
    send; the adapters serialise them as JSON numbers. The net sales can be negative
    (``currentMYNetSales`` down to -1615 in the cottonseed recording). Their names and
    meanings are ESR's and are not explained by the snapshot; nothing is computed,
    converted or re-based here.

    Attributes:
        commodity_code: ``commodityCode``, e.g. ``104`` (Wheat - White).
        country_code: ``countryCode``, ESR's destination code (not ISO), e.g. ``1220``
            (Canada).
        weekly_exports: ``weeklyExports``, e.g. ``Decimal("0")``.
        accumulated_exports: ``accumulatedExports``, e.g. ``Decimal("16217")``.
        outstanding_sales: ``outstandingSales``, e.g. ``Decimal("311")``.
        gross_new_sales: ``grossNewSales``, e.g. ``Decimal("311")``.
        current_my_net_sales: ``currentMYNetSales``, e.g. ``Decimal("311")``.
        current_my_total_commitment: ``currentMYTotalCommitment``, e.g.
            ``Decimal("16217")``.
        next_my_outstanding_sales: ``nextMYOutstandingSales``, e.g. ``Decimal("883")``.
        next_my_net_sales: ``nextMYNetSales``, e.g. ``Decimal("0")``.
        unit_id: ``unitId``, the unit of the quantities, e.g. ``1`` (Metric Tons); plain
            ``int`` on purpose, named by ``enums.UnitId``.
        week_ending_date: ``weekEndingDate``, the last day of the reporting week, e.g.
            ``date(2023, 6, 1)``; upstream sends ``"2023-06-01T00:00:00"``, a midnight
            parsed to ``date`` as in ``DataReleaseInfo``.
    """

    commodity_code: int = Field(validation_alias="commodityCode")
    country_code: int = Field(validation_alias="countryCode")
    weekly_exports: Decimal = Field(validation_alias="weeklyExports")
    accumulated_exports: Decimal = Field(validation_alias="accumulatedExports")
    outstanding_sales: Decimal = Field(validation_alias="outstandingSales")
    gross_new_sales: Decimal = Field(validation_alias="grossNewSales")
    current_my_net_sales: Decimal = Field(validation_alias="currentMYNetSales")
    current_my_total_commitment: Decimal = Field(validation_alias="currentMYTotalCommitment")
    next_my_outstanding_sales: Decimal = Field(validation_alias="nextMYOutstandingSales")
    next_my_net_sales: Decimal = Field(validation_alias="nextMYNetSales")
    unit_id: int = Field(validation_alias="unitId")
    week_ending_date: date = Field(validation_alias="weekEndingDate")
