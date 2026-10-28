"""``GET /api/esr/regions``: every ESR region with its id and name.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``ESRData_GetRegions``: no parameters, the response typed only as ``object``; upstream:
"Use it to associate Region Name with Country records obtained by querying Country end
point". The record shape is the recorded one, ``tests/fixtures/get_regions/all.json``,
parsed into ``models.Region``. Error shapes are mapped once in
``xippios.usda.esr._client.classify``.
"""

from xippios.core import parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import Region

__all__ = ["get_regions"]


async def get_regions() -> list[Region]:
    """Call ``ESRData_GetRegions``.

    Returns:
        Every ESR region, in upstream order, one ``Region`` per record, e.g.
            ``Region(region_id=11, region_name="WESTERN HEMISPHERE")``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/esr/regions")
    return parse(list[Region], raw, source=SOURCE, endpoint="ESRData_GetRegions")
