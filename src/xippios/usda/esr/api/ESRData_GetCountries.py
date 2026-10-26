"""``GET /api/esr/countries``: every ESR destination country with its code and region.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``ESRData_GetCountries``: no parameters, the response typed only as ``object``. The
record shape is the recorded one, ``tests/fixtures/ESRData_GetCountries/all.json``,
parsed into ``models.Country``. Error shapes are mapped once in
``xippios.usda.esr._client.classify``.
"""

from xippios.core import parse

from xippios.usda.esr._client import SOURCE, client
from xippios.usda.esr.models import Country

__all__ = ["ESRData_GetCountries"]


async def ESRData_GetCountries() -> list[Country]:
    """Call ``ESRData_GetCountries``.

    Returns:
        Every ESR country, in upstream order, one ``Country`` per record, names verbatim
        with upstream's padding, e.g. ``Country(country_code=1220, country_name="CANADA  ",
        ...)``.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/esr/countries")
    return parse(list[Country], raw, source=SOURCE, endpoint="ESRData_GetCountries")
