"""Weekly US export records of one commodity to every applicable country in one market year.

``GET /api/esr/exports/commodityCode/{commodityCode}/allCountries/marketYear/{marketYear}``.
Reference: ``docs/upstream/openapi/portal-document.json``, operation
``ESRData_GetAllCountriesData``: path parameters ``commodityCode`` and ``marketYear``,
each an ``int32``, ``allCountries`` a literal path element; the response typed only as
``object``. The record shape is the recorded one (``models.CommodityData``).

No paging: one record per destination and week, all in one answer. Recorded 2026-10-25:
cottonseed, market year 2024, 498 records for 11 destinations, 139,119 bytes of JSON
(``cottonseed_2024``). Recorded 2026-10-28: wheat white, market year 2027, 385 records for
22 destinations over 20 weeks, 108,343 bytes, with a ``9990`` (UNKNOWN) row in every week
(``wheat_white_2027``). An answer can be larger: wheat HRW 2024 was 1,136 records for 28
destinations, 319,532 bytes, and wheat white 2024 1,012 records for 22 destinations, 284,590
bytes, ``9990`` in all 54 weeks (their probes are noted in ``docs/upstream/OBSERVED.md``).
Rye, market year 2024, answers HTTP 200 with ``[]`` (``rye_2024``). Market year 1900
answers HTTP 404 with an empty ``text/plain`` body, as the one-country form does
(``year_1900``), which ``_client.classify`` maps to the shared package's ``NoDataForYear``.
"""

from xippios.core import Answer

from xippios.usda.esr._client import client
from xippios.usda.esr.models import CommodityData

__all__ = ["get_all_countries_data"]


async def get_all_countries_data(
    commodity_code: int, market_year: int
) -> Answer[list[CommodityData]]:
    """Call ``ESRData_GetAllCountriesData``.

    Args:
        commodity_code: ``commodityCode``, e.g. ``1201`` (Cottonseed).
        market_year: ``marketYear``, named by its end year, e.g. ``2024``.

    Returns:
        The ``Answer``, when it was retrieved and, as its payload, one ``CommodityData`` per
            destination and week, in upstream order; ``[]`` when upstream has none.

    Raises:
        NoDataForYear: Upstream answered HTTP 404 with an empty body (no such market year).
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/esr/exports/commodityCode/{commodity_code:d}/allCountries/marketYear/{market_year:d}"
    )
    return await client.get_answer(
        path, parse=list[CommodityData], endpoint="ESRData_GetAllCountriesData"
    )
