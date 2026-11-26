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

from typing import NamedTuple

from xippios.core import Answer, parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import DataReleaseInfo

__all__ = ["ReleaseList", "get_data_release_info"]


class ReleaseList(NamedTuple):
    """The release list as read: the records, and each release time as upstream sent it.

    The record reads ``releaseTimeStamp`` into its one parsed field and keeps no text beside
    it (https://github.com/xippios/sdk-usda-esr/issues/60, part 3), while ``meta.vintage`` of
    ``get_release_dates`` is upstream's text of the newest release, so the wrapper hands the
    task the text apart from the records, read from the decoded answer.

    Attributes:
        records: One ``DataReleaseInfo`` per record upstream sends, one per commodity as
            recorded, in upstream order.
        printed: Each record's ``releaseTimeStamp`` exactly as upstream sent it, at the
            record's place in ``records``, e.g. ``["2026-10-22T08:30:42.67", ...]``.
    """

    records: list[DataReleaseInfo]
    printed: list[str]


async def get_data_release_info() -> Answer[ReleaseList]:
    """Call ``ESRData_GetDataReleaseInfo``.

    Reads the decoded answer with ``get_answer`` and parses its records itself, so that each
    ``releaseTimeStamp`` reaches the task as upstream sent it, and returns
    ``Answer(value, answer.retrieved_at)``, the form of core's ``Answer`` for a value a
    wrapper derives from the payload.

    Returns:
        The ``Answer``, when it was retrieved and, as its payload, the ``ReleaseList``: one
            ``DataReleaseInfo`` per commodity, in upstream order, its current market year and
            the time of its last release, and each release time as upstream sent it.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
        ValidationError: The answer is not a list of release records.
    """
    endpoint = "ESRData_GetDataReleaseInfo"
    answer = await client.get_answer("/api/esr/datareleasedates")
    records = parse(list[DataReleaseInfo], answer.payload, source=SOURCE, endpoint=endpoint)
    printed: list[str] = [sent["releaseTimeStamp"] for sent in answer.payload]
    return Answer(ReleaseList(records, printed), answer.retrieved_at)
