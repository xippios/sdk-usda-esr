"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Every list in ``LISTS``, ``ID_LISTS`` or ``TABLES`` is fetched through its layer-1 wrapper
in ``api/``, never through a task that might answer from the package, and written to
``reference/<name>.json`` with the operation it came from and the fetch date; then
``enums.py`` is regenerated as core renders it, ASCII-only and ruff-clean, with no
formatting step after it (ADR-0008). A value list in ``LISTS`` would become one
``StrEnum`` through ``xippios.core.reference.render_str_enums``; a list of integer ids
and names in ``ID_LISTS`` becomes one ``IntEnum`` through ``id_name_pairs`` and
``render_int_enums``, so that a member compares equal to the id in upstream's data
(conventions §3). Each renderer writes a whole module, so ``enums.py`` holds one kind:
fill one of the two. ``TABLES`` is this package's own, as sdk-usda-psd's: record lists
packaged without an enum.

ESR publishes four lists, all of them records, packaged under upstream's field names
(``upstream_record``): ``unitsOfMeasure`` is an id list, which makes ``UnitId``;
``commodities``, ``countries`` and ``regions`` stay tables, not enums. ESR has no value
list, so ``LISTS`` stays empty. The list endpoints take the api.data.gov key, so
``DATA_GOV_API_KEY`` must be in the environment; run from the repository root::

    uv run python scripts/refresh_reference.py

Four requests against api.data.gov's hourly quota, shared with every package using the
key. Then update the dates in ``reference/README.md``. Only lists that are the same for
every caller are packaged; a multi-tenant source packages no tenant data (ADR-0014),
which ESR is not.

``--render-only`` regenerates ``enums.py`` from the packaged ``reference/*.json`` alone,
without a request and without a key: after a core release changes the renderers
(conventions §15, item 6), it changes ``enums.py`` and nothing else.
"""

import argparse
import json
from collections.abc import Callable, Coroutine, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xippios.core import UpstreamModel, sync
from xippios.core.reference import id_name_pairs, render_int_enums, render_str_enums

from xippios.usda.esr import api
from xippios.usda.esr.params import PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/usda/esr"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"

Fetcher = Callable[[], Coroutine[Any, Any, Sequence[UpstreamModel]]]
"""An endpoint wrapper in ``api/`` that returns a list's records, named after its operation."""

LISTS: dict[str, Callable[[], Coroutine[Any, Any, list[str]]]] = {}
"""Value lists, one ``StrEnum`` each: ESR publishes none, its lists are records."""

ID_LISTS: dict[str, tuple[str, str, Fetcher]] = {
    "unitsOfMeasure": ("unitId", "unitNames", api.ESRData_GetUnitsOfMeasure),
}
"""Lists of integer ids and names, one ``IntEnum`` each (conventions §3), in module order.

List name, as the upstream path names it, to (id field, name field, wrapper), the fields
as upstream names them (``unitNames`` is plural upstream). Each enum is keyed by its id
field and named after it, so ``unitId`` makes ``UnitId``, whose docstring reads "Values of
``unitId``".
"""

TABLES: dict[str, Fetcher] = {
    "commodities": api.ESRData_GetCommodities,
    "countries": api.ESRData_GetCountries,
    "regions": api.ESRData_GetRegions,
}
"""Record lists packaged as tables, with no enum: commodity, country and region codes.

List name, as the upstream path names it, to its wrapper. Packaged like an id list, as
upstream's records under upstream's field names, which ``params`` reads; the three lists
together with ``ID_LISTS`` are ``params.PACKAGED_LISTS``.
"""


def operation(fetch: Callable[[], object]) -> str:
    """The upstream operation a wrapper calls: its name, as ``api/`` names every wrapper."""
    return fetch.__name__


def upstream_record(record: UpstreamModel) -> dict[str, Any]:
    """``record`` as JSON under upstream's field names, for ``reference/<name>.json``.

    A field's upstream name is its ``Field(validation_alias=...)`` where the model has a
    string one, else the field's own name. The models set no serialisation alias
    (``models.py``), so ``model_dump(by_alias=True)`` would not restore upstream's names;
    values are dumped as JSON, a ``Decimal`` as a number, a date as ISO text.
    """
    upstream = {
        name: info.validation_alias if isinstance(info.validation_alias, str) else name
        for name, info in type(record).model_fields.items()
    }
    dumped = record.model_dump(mode="json")
    return {upstream.get(name, name): value for name, value in dumped.items()}


def write(name: str, endpoint: str, fetched: str, key: str, rows: Sequence[object]) -> None:
    """Write ``reference/<name>.json``: the list, its operation, the fetch date, ``rows``."""
    path = REFERENCE / f"{name}.json"
    payload = {"param": name, "endpoint": endpoint, "fetched": fetched, key: list(rows)}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(rows)} {key}")  # noqa: T201


def read(name: str) -> dict[str, Any]:
    """The packaged ``reference/<name>.json``, as ``write`` wrote it."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def render(
    values: Mapping[str, Sequence[str]],
    pairs: Mapping[str, Sequence[tuple[int, str]]],
    fetched: str | None,
) -> str:
    """``enums.py`` as core renders it: one ``IntEnum`` per id list, else one ``StrEnum`` each.

    Args:
        values: Value list name to its values, ``{}`` for ESR.
        pairs: Id list name to its ``(id, name)`` pairs, e.g.
            ``{"unitsOfMeasure": [(1, "Metric Tons"), ...]}``.
        fetched: The fetch date each class docstring names, e.g. ``"2026-10-25"``.
    """
    if pairs:
        fields = {name: ID_LISTS[name][0] for name in pairs}
        return render_int_enums(
            {fields[name]: rows for name, rows in pairs.items()},
            class_names={field: field[:1].upper() + field[1:] for field in fields.values()},
            fetched=fetched,
            generator=GENERATOR,
        )
    return render_str_enums(values, fetched=fetched, generator=GENERATOR)


def refresh() -> None:
    """Fetch every list, write its file and regenerate ``enums.py``."""
    if {*LISTS, *ID_LISTS, *TABLES} != set(PACKAGED_LISTS):
        raise SystemExit("LISTS, ID_LISTS and TABLES name other lists than params.PACKAGED_LISTS")
    today = datetime.now(UTC).date().isoformat()
    REFERENCE.mkdir(exist_ok=True)
    values: dict[str, list[str]] = {}
    for name, fetch in LISTS.items():
        values[name] = sync(fetch)()
        write(name, operation(fetch), today, "values", values[name])
    for name, fetch_records in TABLES.items():
        records = [upstream_record(record) for record in sync(fetch_records)()]
        write(name, operation(fetch_records), today, "records", records)
    pairs: dict[str, list[tuple[int, str]]] = {}
    for name, (id_field, name_field, fetch_records) in ID_LISTS.items():
        records = [upstream_record(record) for record in sync(fetch_records)()]
        write(name, operation(fetch_records), today, "records", records)
        pairs[name] = id_name_pairs(records, id_field=id_field, name_field=name_field)
    ENUMS.write_text(render(values, pairs, today), encoding="utf-8")
    print(f"{ENUMS.name}: {len(values) + len(pairs)} enums")  # noqa: T201


def render_only() -> None:
    """Regenerate ``enums.py`` from the packaged files, without a request."""
    dates: set[str] = set()
    values: dict[str, list[str]] = {}
    for name in LISTS:
        payload = read(name)
        values[name] = payload["values"]
        dates.add(payload["fetched"])
    pairs: dict[str, list[tuple[int, str]]] = {}
    for name, (id_field, name_field, _) in ID_LISTS.items():
        payload = read(name)
        pairs[name] = id_name_pairs(payload["records"], id_field=id_field, name_field=name_field)
        dates.add(payload["fetched"])
    if len(dates) > 1:
        raise SystemExit(f"the packaged lists were fetched on different days: {sorted(dates)}")
    ENUMS.write_text(render(values, pairs, dates.pop() if dates else None), encoding="utf-8")
    print(f"{ENUMS.name}: {len(values) + len(pairs)} enums, from the packaged files")  # noqa: T201


def main() -> None:
    """Refresh from upstream, or with ``--render-only`` regenerate ``enums.py`` alone."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request or a key",
    )
    args = parser.parse_args()
    if LISTS and ID_LISTS:
        raise SystemExit("enums.py holds one kind of enum: fill LISTS or ID_LISTS, not both")
    if args.render_only:
        render_only()
    else:
        refresh()


if __name__ == "__main__":
    main()
