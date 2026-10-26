"""``GET /api/esr/datareleasedates``: the last release of each commodity's export data.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``ESRData_GetDataReleaseInfo``: no parameters, the response typed only as ``object``.
Upstream: "there could be revision on the Export numbers for multiple years on a given
commodity, and so this API endpoint returns set of records containing data release dates
at a commodity level. Use this information to query for only the Export data that has
changed since last invocation of this API End point". The record shape is the recorded
one (``models.DataReleaseInfo``): one per commodity, 44 records. Error shapes are mapped
once in ``xippios.usda.esr._client.classify``.
"""

from xippios.core import parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import DataReleaseInfo

__all__ = ["ESRData_GetDataReleaseInfo"]


async def ESRData_GetDataReleaseInfo() -> list[DataReleaseInfo]:
    """Call ``ESRData_GetDataReleaseInfo``.

    Returns:
        One ``DataReleaseInfo`` per commodity, in upstream order: its current market year
        and the time of its last release.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/esr/datareleasedates")
    return parse(list[DataReleaseInfo], raw, source=SOURCE, endpoint="ESRData_GetDataReleaseInfo")
