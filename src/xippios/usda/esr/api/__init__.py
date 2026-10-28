"""Endpoint wrappers for USDA FAS Export Sales Reporting.

Layer 1 of ADR-0001: one module per upstream operation, named after it. A wrapper
takes the parameters as upstream names them (snake_cased), calls
``xippios.usda.esr._client.client`` and returns models from ``models.py`` that
mirror the payload. No composition and no defaults beyond upstream's own. The reference
is the snapshot in ``docs/upstream/``; modules and functions carry the snapshot's
``operationId`` in snake case without the ``ESRData_`` prefix every operation of the API
shares (conventions §2), e.g. ``ESRData_GetCommodities`` is ``get_commodities`` in
``api/get_commodities.py``. The verbatim id stays in the first line of the wrapper's
docstring and in the ``endpoint=`` it passes, so ``meta.endpoint`` keeps upstream's name.
Every path parameter is an ``int32`` in the snapshot and an ``int`` here, rendered into
the path as decimal digits.
"""

from xippios.usda.esr.api.get_all_countries_data import get_all_countries_data
from xippios.usda.esr.api.get_commodities import get_commodities
from xippios.usda.esr.api.get_countries import get_countries
from xippios.usda.esr.api.get_country_data import get_country_data
from xippios.usda.esr.api.get_data_release_info import get_data_release_info
from xippios.usda.esr.api.get_regions import get_regions
from xippios.usda.esr.api.get_units_of_measure import get_units_of_measure

__all__ = [
    "get_all_countries_data",
    "get_commodities",
    "get_countries",
    "get_country_data",
    "get_data_release_info",
    "get_regions",
    "get_units_of_measure",
]
