"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Every list in ``LISTS``, ``ID_LISTS`` or ``TABLES`` is fetched through its layer-1 wrapper
in ``api/``, never through a task that might answer from the package; once all are
fetched, each is written to ``reference/<name>.json`` by core's ``PackagedList.write``:
the list's name, the upstream operation it came from (the ``operationId`` its entry
names, never the wrapper's name: conventions §2), the UTC time of the fetch to the second
and upstream's records under upstream's field names (``dump_upstream``), a value list as
records of one field named by the list (conventions §3). Then ``enums.py`` is regenerated
from the packaged files by one ``xippios.core.reference.render_enums`` call, a ``StrEnum``
per value list in ``LISTS`` and an ``IntEnum`` per list of integer ids and names in
``ID_LISTS`` (``id_name_pairs``), so that a member compares equal to the id in upstream's
data, each class naming the day its list was fetched and taking core's default name, from
its list or its id field; and formatted with ``ruff format`` and ``ruff check --fix``, as
it is committed (sdk-core ADR-0031, decision 6). ``TABLES``, as in sdk-usda-psd and the
template, are record lists packaged without an enum. Where a member name derives to
nothing, or two collide, name it by hand in ``module``'s call:
``render_enums(member_names=...)``, per list and value (an id for an ``IntEnum``), and a
class name by hand with ``render_enums(class_names=...)``.

ESR publishes four lists, all of them records: ``unitsOfMeasure`` is an id list, which
makes ``UnitId``; ``commodities``, ``countries`` and ``regions`` stay tables, not enums.
ESR has no value list, so ``LISTS`` stays empty. The list endpoints take the api.data.gov
key, so ``DATA_GOV_API_KEY`` must be in the environment; run from the repository root::

    uv run python scripts/refresh_reference.py

Four requests against api.data.gov's hourly quota, shared with every package using the
key. Then update the times in ``reference/README.md``. Only lists that are the same for
every caller are packaged; a multi-tenant source packages no tenant data
(sdk-core ADR-0036), which ESR is not.

The package's client sends each request once, ``RetryPolicy(max_attempts=1)``, so a 5xx
or a 429 spends no second call of the key's quota: a run that fails writes nothing and is
run again. After the fetches it prints the requests it sent and the quota left that the
gateway reported in ``QUOTA_HEADER``, a failed run's too, so a run is counted against the
release's budget of keyed calls: each request by its answer, and the one that ends a run in
a transport error, which may have reached the gateway, as a read timeout's does, as sent
too, so the count is never below what the run spent. ``--only <list> [<list> ...]`` fetches the
named lists of ``PACKAGED_LISTS`` alone, writes their files and keeps every other list's
file as it is, as a change that packages a new list does; ``enums.py`` is then regenerated
from all of them, so every list it keeps must be packaged already, which is checked
before the first request.

``--render-only`` regenerates ``enums.py`` from the packaged ``reference/*.json`` alone,
without a request and without a key: after a core release changes the renderer
(conventions §15, item 6), it changes ``enums.py`` and nothing else.
"""

import argparse
import subprocess
import sys
from collections.abc import Callable, Coroutine, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from xippios.core import (
    AsyncClient,
    PackagedList,
    RetryPolicy,
    TransportError,
    UpstreamModel,
    sync,
)
from xippios.core.reference import id_name_pairs, render_enums

from xippios.usda.esr import api
from xippios.usda.esr._client import client
from xippios.usda.esr.params import PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/usda/esr"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"

QUOTA_HEADER: str | None = "x-ratelimit-remaining"
"""The response header in which the gateway reports the requests left in the key's hourly
quota, on every keyed answer (``CLAUDE.md``'s Rate limit row)."""

Fetcher = Callable[[], Coroutine[Any, Any, Sequence[UpstreamModel]]]
"""An endpoint wrapper in ``api/`` that returns a list's records."""

LISTS: dict[str, tuple[str, Callable[[], Coroutine[Any, Any, Sequence[str]]]]] = {}
"""Value lists, one ``StrEnum`` each: ESR publishes none, its lists are records."""

ID_LISTS: dict[str, tuple[str, Fetcher, str, str]] = {
    "unitsOfMeasure": (
        "ESRData_GetUnitsOfMeasure",
        api.get_units_of_measure,
        "unitId",
        "unitNames",
    ),
}
"""Lists of integer ids and names, one ``IntEnum`` each (conventions §3), in module order.

List name, as the upstream path names it, to (upstream operation, wrapper, id field, name
field): the operation verbatim, as the snapshot's ``operationId`` and the wrapper's
``endpoint=`` give it, which the file keeps as its ``endpoint`` and the list task as its
``meta.endpoint``; the fields as upstream names them (``unitNames`` is plural upstream).
Each enum is keyed by its id field and named after it by core's default, so ``unitId``
makes ``UnitId``, whose docstring reads "Values of ``unitId``".
"""

TABLES: dict[str, tuple[str, Fetcher]] = {
    "commodities": ("ESRData_GetCommodities", api.get_commodities),
    "countries": ("ESRData_GetCountries", api.get_countries),
    "regions": ("ESRData_GetRegions", api.get_regions),
}
"""Record lists packaged as tables, with no enum: commodity, country and region codes.

List name, as the upstream path names it, to (upstream operation, wrapper), the operation
verbatim as in ``ID_LISTS``. Packaged like an id list, as upstream's records under
upstream's field names, which ``params`` reads; the three lists together with
``ID_LISTS`` are ``params.PACKAGED_LISTS``.
"""


class Meter:
    """What a run spent: the requests it sent and the quota left that the gateway reported.

    The client's ``observe`` hook, which core calls with every response from the wire. It
    calls the hook the client had first, the gateway's quota policy (sdk-core ADR-0037), and
    keeps the last count that the gateway sent in ``QUOTA_HEADER``. A request is counted by
    its response: with no retry each has one, but for one that fails in transport, which
    ``metered`` counts in ``sent`` and ``unanswered`` when its error ends the run.
    """

    def __init__(self, observe: Callable[[httpx.Response], None] | None) -> None:
        self.sent = 0
        self.unanswered = 0
        self.left: int | None = None
        self._observe = observe

    def __call__(self, response: httpx.Response) -> None:
        """Count ``response`` and keep the quota it reports, after the hook it replaces."""
        if self._observe is not None:
            self._observe(response)
        self.sent += 1
        value = response.headers.get(QUOTA_HEADER) if QUOTA_HEADER else None
        if value is not None and value.isascii() and value.isdigit():
            self.left = int(value)

    def report(self) -> str:
        """The requests sent and the quota left, as the gateway last reported it, one line."""
        left = "not reported" if self.left is None else f"{self.left} ({QUOTA_HEADER})"
        unanswered = (
            f" ({self.unanswered} ended in a transport error, counted as sent)"
            if self.unanswered
            else ""
        )
        return f"requests sent: {self.sent}{unanswered}; quota left: {left}"


@contextmanager
def metered(target: AsyncClient) -> Iterator[Meter]:
    """``target`` for the block: one attempt per request, each counted, then the report.

    ``RetryPolicy(max_attempts=1)`` keeps a 5xx or a 429 from spending a second call of the
    key's quota. A request that fails in transport has no response for ``Meter`` to count,
    and with one attempt its ``TransportError`` ends the block: it is counted as sent, since
    it may have reached the gateway. ``target``'s configuration is restored after the block,
    and the report is printed, a failed run's too.
    """
    configured = target.config
    meter = Meter(configured.observe)
    target.config = replace(configured, retry=RetryPolicy(max_attempts=1), observe=meter)
    try:
        yield meter
    except TransportError:
        meter.sent += 1
        meter.unanswered += 1
        raise
    finally:
        target.config = configured
        print(meter.report())  # noqa: T201


def packaged(name: str, endpoint: str, records: Sequence[dict[str, Any]]) -> PackagedList:
    """The list ``name`` as just fetched from ``endpoint``, for ``reference/<name>.json``."""
    return PackagedList(
        param=name, endpoint=endpoint, fetched=datetime.now(UTC), records=list(records)
    )


def read(name: str) -> PackagedList:
    """The packaged ``reference/<name>.json``, as ``refresh`` wrote it."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    return PackagedList.model_validate_json(path.read_text(encoding="utf-8"))


def module() -> str:
    """``enums.py`` as ``render_enums`` writes it from the packaged files, before ruff."""
    lists: dict[str, Sequence[str] | Sequence[tuple[int, str]]] = {}
    fetched: dict[str, str] = {}
    keys = [*LISTS, *(id_field for _, _, id_field, _ in ID_LISTS.values())]
    if len(set(keys)) < len(keys):
        raise SystemExit("an id field of ID_LISTS names a list of LISTS: one enum each")
    for name in LISTS:
        values = read(name)
        lists[name] = [record[name] for record in values.records]
        fetched[name] = f"{values.fetched:%Y-%m-%d}"
    for name, (_, _, id_field, name_field) in ID_LISTS.items():
        ids = read(name)
        lists[id_field] = id_name_pairs(ids.records, id_field=id_field, name_field=name_field)
        fetched[id_field] = f"{ids.fetched:%Y-%m-%d}"
    return render_enums(lists, fetched=fetched, generator=GENERATOR)


def render() -> None:
    """Regenerate ``enums.py`` from the packaged files and format it as it is committed."""
    ENUMS.write_text(module(), encoding="utf-8")
    sys.stdout.flush()
    for command in (["format"], ["check", "--fix"]):
        run = subprocess.run([sys.executable, "-m", "ruff", *command, str(ENUMS)], cwd=ROOT)
        if run.returncode:
            raise SystemExit(f"ruff {' '.join(command)} left {ENUMS.name} failing")
    print(f"{ENUMS.name}: {len(LISTS) + len(ID_LISTS)} enums")  # noqa: T201


def refresh(only: Sequence[str] = ()) -> None:
    """Fetch every list, then write its file, then regenerate ``enums.py`` from the files.

    ``only``, the lists ``--only`` names, fetches those alone and keeps every other list's
    file, which must be packaged already. Both are checked before the first request, and
    every list is fetched, each request sent once and counted, before the first file is
    written.
    """
    names = [*LISTS, *ID_LISTS, *TABLES]
    if sorted(names) != sorted(PACKAGED_LISTS):
        raise SystemExit("LISTS, ID_LISTS and TABLES name other lists than params.PACKAGED_LISTS")
    if unknown := [name for name in only if name not in names]:
        raise SystemExit(f"--only: no list {', '.join(unknown)} in {', '.join(names)}")
    chosen = set(only or names)
    kept = [name for name in names if name not in chosen]
    if missing := [name for name in kept if not (REFERENCE / f"{name}.json").is_file()]:
        raise SystemExit(f"{', '.join(missing)} is not packaged yet: run without --only")
    with metered(client):
        lists = [
            *(
                packaged(name, endpoint, [{name: value} for value in sync(fetch)()])
                for name, (endpoint, fetch) in LISTS.items()
                if name in chosen
            ),
            *(
                packaged(name, endpoint, [record.dump_upstream() for record in sync(fetch)()])
                for name, (endpoint, fetch, _, _) in ID_LISTS.items()
                if name in chosen
            ),
            *(
                packaged(name, endpoint, [record.dump_upstream() for record in sync(fetch)()])
                for name, (endpoint, fetch) in TABLES.items()
                if name in chosen
            ),
        ]
    REFERENCE.mkdir(exist_ok=True)
    for fetched in lists:
        path = REFERENCE / f"{fetched.param}.json"
        fetched.write(path)
        print(f"{path.name}: {len(fetched.records)} records from {fetched.endpoint}")  # noqa: T201
    render()


def main(argv: Sequence[str] | None = None) -> None:
    """Refresh from upstream, some lists with ``--only``, or ``enums.py`` alone."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request or a key",
    )
    choice.add_argument(
        "--only",
        nargs="+",
        default=[],
        metavar="LIST",
        help="fetch these lists of PACKAGED_LISTS alone and keep every other list's file",
    )
    args = parser.parse_args(argv)
    if args.render_only:
        render()
    else:
        refresh(args.only)


if __name__ == "__main__":
    main()
