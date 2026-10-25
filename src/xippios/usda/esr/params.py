"""Packaged value lists for USDA FAS Export Sales Reporting (conventions §3).

Small, stable upstream lists ship inside the package under ``reference/`` so lookups
need no network call; ``scripts/refresh_reference.py`` writes them and the matching
``StrEnum`` classes in ``enums.py``, never by hand. ``reference/README.md`` carries the
provenance of every file.
"""

from datetime import date

from xippios.core import UpstreamModel, load_json

__all__ = ["PACKAGED_LISTS", "PackagedValues", "packaged_values"]

PACKAGE = "xippios.usda.esr"

PACKAGED_LISTS: tuple[str, ...] = ()
"""Names of the lists that ship inside the package; keep in step with the refresh script."""


class PackagedValues(UpstreamModel):
    """One packaged value list: ``reference/<name>.json``.

    Attributes:
        param: The upstream list the values belong to.
        fetched: Day the list was fetched.
        values: The values, as upstream lists them.
    """

    param: str
    fetched: date
    values: list[str]


def packaged_values(name: str) -> PackagedValues | None:
    """The packaged list ``name``, or ``None`` when it is not packaged."""
    if name not in PACKAGED_LISTS:
        return None
    return PackagedValues.model_validate(load_json(PACKAGE, f"{name}.json"))
