"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Every list in ``LISTS`` or ``ID_LISTS`` is fetched through the layer-1 wrappers in
``api/``, never through a task that might answer from the package, and written to
``reference/<name>.json`` with the fetch date, an id list as upstream's records under
upstream's field names; then ``enums.py`` is regenerated as core renders it, ASCII-only
and ruff-clean, with no formatting step after it (ADR-0008). A value list in ``LISTS``
becomes one ``StrEnum`` through ``xippios.core.reference.render_str_enums``; a list of
integer ids and names in ``ID_LISTS`` becomes one ``IntEnum`` through ``id_name_pairs``
and ``render_int_enums``, so that a member compares equal to the id in upstream's data
(conventions §3). Each renderer writes a whole module, so ``enums.py`` holds one kind:
fill one of the two.

Only lists that are the same for every caller are packaged; a multi-tenant source
packages no tenant data (ADR-0014). Run from the repository root, with whatever the list
endpoints need in the environment (a key only where they take one)::

    uv run python scripts/refresh_reference.py

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

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/usda/esr"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"

LISTS: dict[str, Callable[[], Coroutine[Any, Any, list[str]]]] = {
    # name of the list, as upstream calls it, to an async fetcher through api/, e.g.
    # "country_code": lambda: api.list_countries(),
}
"""Value lists, one ``StrEnum`` each; keep ``params.PACKAGED_LISTS`` in step with the keys."""

ID_LISTS: dict[str, tuple[str, str, Callable[[], Coroutine[Any, Any, Sequence[UpstreamModel]]]]] = {
    # name of the list to (id field, name field, async fetcher of its records through api/),
    # the fields as upstream names them, e.g.
    # "unit_id": ("unitId", "unitDescription", lambda: api.list_units()),
}
"""Lists of integer ids and names, one ``IntEnum`` each (conventions §3).

Packaged as upstream's records under upstream's field names (``upstream_record``), as a
table keeps upstream's column names; ``params.packaged_values`` reads value lists only, so
these stay out of ``params.PACKAGED_LISTS``.
"""


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


def write(name: str, fetched: str, key: str, rows: Sequence[object]) -> None:
    """Write ``reference/<name>.json``: the list's name, the fetch date and ``rows`` as ``key``."""
    path = REFERENCE / f"{name}.json"
    payload = {"param": name, "fetched": fetched, key: list(rows)}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
    """``enums.py`` as core renders it: one ``IntEnum`` per id list, else one ``StrEnum`` each."""
    if pairs:
        return render_int_enums(pairs, fetched=fetched, generator=GENERATOR)
    return render_str_enums(values, fetched=fetched, generator=GENERATOR)


def refresh() -> None:
    """Fetch every list, write its file and regenerate ``enums.py``."""
    today = datetime.now(UTC).date().isoformat()
    REFERENCE.mkdir(exist_ok=True)
    values: dict[str, list[str]] = {}
    for name, fetch in LISTS.items():
        values[name] = sync(fetch)()
        write(name, today, "values", values[name])
    pairs: dict[str, list[tuple[int, str]]] = {}
    for name, (id_field, name_field, fetch_records) in ID_LISTS.items():
        records = [upstream_record(record) for record in sync(fetch_records)()]
        write(name, today, "records", records)
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
