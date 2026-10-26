"""Endpoint wrappers for USDA FAS Export Sales Reporting.

Layer 1 of ADR-0001: one module per upstream operation, named after it. A wrapper
takes the parameters as upstream names them (snake_cased), calls
``xippios.usda.esr._client.client`` and returns models from ``models.py`` that
mirror the payload. No composition and no defaults beyond upstream's own. The reference
is the snapshot in ``docs/upstream/``; modules and functions carry the snapshot's
``operationId`` verbatim, e.g. ``ESRData_GetCommodities``. Every path parameter is an
``int32`` in the snapshot and an ``int`` here, rendered into the path as decimal digits.
"""

from xippios.usda.esr.api.ESRData_GetAllCountriesData import ESRData_GetAllCountriesData
from xippios.usda.esr.api.ESRData_GetCommodities import ESRData_GetCommodities
from xippios.usda.esr.api.ESRData_GetCountries import ESRData_GetCountries
from xippios.usda.esr.api.ESRData_GetCountryData import ESRData_GetCountryData
from xippios.usda.esr.api.ESRData_GetDataReleaseInfo import ESRData_GetDataReleaseInfo
from xippios.usda.esr.api.ESRData_GetRegions import ESRData_GetRegions
from xippios.usda.esr.api.ESRData_GetUnitsOfMeasure import ESRData_GetUnitsOfMeasure

__all__ = [
    "ESRData_GetAllCountriesData",
    "ESRData_GetCommodities",
    "ESRData_GetCountries",
    "ESRData_GetCountryData",
    "ESRData_GetDataReleaseInfo",
    "ESRData_GetRegions",
    "ESRData_GetUnitsOfMeasure",
]
