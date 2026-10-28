"""``GET /api/esr/commodities``: every ESR commodity with its code and unit.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``ESRData_GetCommodities``: no parameters, the response typed only as ``object``. The
record shape is the recorded one, ``tests/fixtures/get_commodities/all.json``,
parsed into ``models.Commodity``. Error shapes are mapped once in
``xippios.usda.esr._client.classify``.
"""

from xippios.core import parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import Commodity

__all__ = ["get_commodities"]


async def get_commodities() -> list[Commodity]:
    """Call ``ESRData_GetCommodities``.

    Returns:
        Every ESR commodity, in upstream order, one ``Commodity`` per record, e.g.
            ``Commodity(commodity_code=104, commodity_name="Wheat - White", unit_id=1)``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/esr/commodities")
    return parse(list[Commodity], raw, source=SOURCE, endpoint="ESRData_GetCommodities")
