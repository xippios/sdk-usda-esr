"""Pydantic models mirroring USDA FAS Export Sales Reporting payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. Where upstream spells a field differently,
``Field(validation_alias=...)`` accepts that spelling on input; never ``alias=``, which the
adapters would serialise, handing agents the upstream spelling. Within-source hygiene only:
dates become ``datetime.date``, numbers become numbers, upstream enumerations become
``StrEnum``, and an enumeration of integer ids ``IntEnum``. No cross-source normalisation
(ADR-0003): an upstream concept stays an upstream concept.

These read models stay faithful, documented personal identifiers included (``ssn``,
``iban`` and their like). The projections tasks return leave those out, a write task does
not echo one in ``meta.request``, and fixtures never carry their values (ADR-0017).

Example::

    from decimal import Decimal

    from pydantic import Field

    from xippios.core import UpstreamModel


    class Record(UpstreamModel):
        name: str
        year: int
        value: Decimal = Field(validation_alias="Value")
"""

__all__: list[str] = []
