"""``GET /api/esr/unitsOfMeasure``: every ESR unit of measure with its id and name.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``ESRData_GetUnitsOfMeasure``: no parameters, the response typed only as ``object``;
upstream: "Use it to associate Unit Of Measure Name with Commodity Data redords obtained
by querying Commodity Data End point". The record shape is the recorded one,
``tests/fixtures/get_units_of_measure/all.json``, parsed into
``models.UnitOfMeasure``. Error shapes are mapped once in
``xippios.usda.esr._client.classify``.
"""

from xippios.core import parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import UnitOfMeasure

__all__ = ["get_units_of_measure"]


async def get_units_of_measure() -> list[UnitOfMeasure]:
    """Call ``ESRData_GetUnitsOfMeasure``.

    Returns:
        Every ESR unit, in upstream order, one ``UnitOfMeasure`` per record, e.g.
            ``UnitOfMeasure(unit_id=1, unit_names="Metric Tons")``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/esr/unitsOfMeasure")
    return parse(list[UnitOfMeasure], raw, source=SOURCE, endpoint="ESRData_GetUnitsOfMeasure")
