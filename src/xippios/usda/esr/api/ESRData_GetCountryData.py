"""Weekly US export records of one commodity to one country in one market year.

``GET /api/esr/exports/commodityCode/{commodityCode}/countryCode/{countryCode}``
``/marketYear/{marketYear}``. Reference:
``docs/upstream/openapi/portal-document.json``, operation ``ESRData_GetCountryData``:
three path parameters, ``commodityCode``, ``countryCode`` and ``marketYear``, each an
``int32``; the response typed only as ``object``. The record shape is the recorded one
(``models.CommodityData``).

Recorded answers (2026-10-25): wheat white to Canada, market year 2024, is 54 weekly
records (``wheat_white_canada_2024``); an unknown commodity or country code is HTTP 200
with ``[]`` (``unknown_commodity``, 999; ``unknown_country``, 9999), and so is a market
year in the future (``year_2099``); market year 1900 is HTTP 404 with an empty
``text/plain`` body (``year_1900``), which ``_client.classify`` maps to
``errors.NoDataForYear``; a path value that is not an integer is HTTP 400
(``not_an_integer``), never sent here since every parameter is an ``int``.
"""

from xippios.core import parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import CommodityData

__all__ = ["ESRData_GetCountryData"]


async def ESRData_GetCountryData(
    commodity_code: int, country_code: int, market_year: int
) -> list[CommodityData]:
    """Call ``ESRData_GetCountryData``.

    Args:
        commodity_code: ``commodityCode``, e.g. ``104`` (Wheat - White).
        country_code: ``countryCode``, ESR's code, e.g. ``1220`` (Canada).
        market_year: ``marketYear``, named by its end year, e.g. ``2024``.

    Returns:
        One ``CommodityData`` per week, in upstream order; ``[]`` when upstream has none.

    Raises:
        NoDataForYear: Upstream answered HTTP 404 with an empty body (no such market year).
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/esr/exports/commodityCode/{commodity_code:d}"
        f"/countryCode/{country_code:d}/marketYear/{market_year:d}"
    )
    raw = await client.get_json(path)
    return parse(list[CommodityData], raw, source=SOURCE, endpoint="ESRData_GetCountryData")
