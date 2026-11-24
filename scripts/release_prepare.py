#!/usr/bin/env python3
"""Prepare a release in the tree: write its section of `CHANGELOG.md`, set its version and write its lock.

    python3 -I scripts/release_prepare.py <version>                    the section dated by the UTC day
    python3 -I scripts/release_prepare.py <version> --date YYYY-MM-DD  dated by that day, and the section of the
                                                                       version whose tag is not set dated again

The section is the one that `changelog_assemble.py` beside this script writes from the fragments under `changelog/`,
which it removes. The version is set where a manifest names one: `version` of the `[project]` table of
`pyproject.toml`, on a line of its own that starts with the key, and the top-level `version` of `composer.json` where
it carries one. A table ends at the next line that opens with a bracket, as a header does indented or not, and a
`[project]` that holds no such line and no `version` under `dynamic` before it is refused.

The lock follows: `uv.lock` beside `pyproject.toml` takes the version as the package of the repository itself, the one
whose source is `.`, on its `version` line alone, so the script builds nothing and reaches no index. A lock that holds
no such package is refused, and `uv lock` writes it first. `composer.lock` is left as it stands, and each file keeps
its line ends.

A repository whose manifests name no version, `dynamic` in `[project]` among them, or that holds none, keeps its
version in its tag `v<version>`, and the script says so.

It runs again with the same result: on the tree it prepared it writes nothing; a section of the version whose tag is
not set takes the fragments that came since, with the base of its branch, while the version and the lock stand; and a
run with another `--date` changes the heading alone. Every file is read and every refusal made before the first is
written. It commits nothing and pushes nothing.

It prints one line per item: the lines of the assembler, the heading with the bullets of each group, a `folded:` and a
`removed:` line each, then one line per file whose version it set. It exits 0 when the tree holds the release, written
now or before; 1 when it wrote nothing, the reason on one line, the assembler's refusals among them; and 2 on a command
line it does not take. It needs the standard library alone, and git through the assembler, so people, CI and a
repository's tools run the same script. A repository carries it byte for byte as its template renders it, beside the
assembler, and edits no copy: the template's next release brings the next version.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

ASSEMBLER = "changelog_assemble.py"  # beside this script, which writes the section
MODULE = "changelog_assemble"  # the name the assembler is loaded under
PYPROJECT, UV_LOCK, COMPOSER = "pyproject.toml", "uv.lock", "composer.json"
HEADER = re.compile(r"^[ \t]*\[", re.M)  # a line that may open a table's header in TOML, indented or not
PROJECT = re.compile(r"^[ \t]*\[[ \t]*project[ \t]*\][ \t]*(?:#[^\r\n]*)?\r?$", re.M)
PACKAGE = re.compile(r"^\[\[package\]\][ \t]*\r?$", re.M)  # a package of `uv.lock`
DYNAMIC = re.compile(r"^dynamic[ \t]*=[ \t]*\[([^\]]*)\]", re.M)  # the keys of `[project]` its build writes
DYNAMIC_VERSION = re.compile(r"""["']version["']""")
NAME_LINE = re.compile(r"""^name[ \t]*=[ \t]*(["'])([^"'\n]*)\1""", re.M)
VERSION_LINE = re.compile(r"""^version[ \t]*=[ \t]*(["'])([^"'\n]*)\1""", re.M)
OWN_SOURCE = re.compile(r'^source[ \t]*=[ \t]*\{[ \t]*(?:editable|virtual)[ \t]*=[ \t]*"\."[ \t]*\}', re.M)
JSON_VERSION = re.compile(r'^[ \t]*"version"[ \t]*:[ \t]*"([^"\n]*)"', re.M)
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PrepareError(Exception):
    """Nothing written: why the tree takes no release of the version."""


@functools.cache
def assembler() -> ModuleType:
    """The assembler beside this script, loaded by its path, since an isolated Python puts no folder on the path,
    and with no bytecode written beside it, which a template's render would carry. PrepareError where it is
    missing."""
    path = Path(__file__).resolve().with_name(ASSEMBLER)
    spec = importlib.util.spec_from_file_location(MODULE, path)
    if not path.is_file() or spec is None or spec.loader is None:
        raise PrepareError(f"no {ASSEMBLER} beside {Path(__file__).name}, which writes the section by it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE] = module  # its dataclasses read their module
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


def normalized(name: str) -> str:
    """A package's name as a lock compares it: lower case, each run of `-`, `_` and `.` one `-`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def table(text: str, header: re.Pattern[str]) -> tuple[int, int] | None:
    """The slice of a TOML table's own keys: after the header `header` finds, up to the next line that opens with a
    bracket, as a header does indented or not, or the end."""
    m = header.search(text)
    if not m:
        return None
    rest = HEADER.search(text, m.end())
    return m.end(), rest.start() if rest else len(text)


def project(text: str, version: str) -> tuple[str, str, str] | None:
    """(name, version before, text with `version`) of a `pyproject.toml` whose `[project]` names its version, None
    where `version` stands under its `dynamic`, a version that the build reads from elsewhere, or where the file holds
    no `[project]`. PrepareError where `[project]` holds neither, a version on an indented line or after a line that
    opens with a bracket, a header of another table or a line of a multi-line string, among them."""
    span = table(text, PROJECT)
    if span is None:
        return None
    start, end = span
    body = text[start:end]
    line, name = VERSION_LINE.search(body), NAME_LINE.search(body)
    if line is None:
        dynamic = DYNAMIC.search(body)
        if dynamic and DYNAMIC_VERSION.search(dynamic.group(1)):
            return None
        raise PrepareError(
            f"{PYPROJECT}: [project] holds no `version` line at the start of a line, which this script sets, and no "
            "`version` under `dynamic`"
        )
    if name is None:
        raise PrepareError(f"{PYPROJECT}: no name in [project], by which {UV_LOCK} holds the package")
    at = start + line.start(2)
    return name.group(2), line.group(2), text[:at] + version + text[start + line.end(2) :]


def locked(text: str, name: str, version: str) -> tuple[str, str, str]:
    """(the name as the lock writes it, version before, text with `version`) of a `uv.lock` whose package `name`, the
    repository's own, at `.`, takes the version on its `version` line alone; PrepareError where it holds none."""
    for m in PACKAGE.finditer(text):
        rest = HEADER.search(text, m.end())
        end = rest.start() if rest else len(text)
        head = text[m.end() : end]
        named, line = NAME_LINE.search(head), VERSION_LINE.search(head)
        if named and line and normalized(named.group(2)) == normalized(name) and OWN_SOURCE.search(head):
            at = m.end() + line.start(2)
            return named.group(2), line.group(2), text[:at] + version + text[m.end() + line.end(2) :]
    raise PrepareError(f"{UV_LOCK} holds no package {name} whose source is `.`: write it with `uv lock` first")


def composed(text: str, version: str) -> tuple[str, str] | None:
    """(version before, text with `version`) of a `composer.json` that carries a top-level `version`, on its line
    alone, the line whose change sets that `version` and nothing else, as the text read again shows; None where it
    carries none, its tag being its version. PrepareError where it is no JSON object or its version stands on no line
    of its own."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise PrepareError(f"{COMPOSER}: {e}") from None
    if not isinstance(data, dict):
        raise PrepareError(f"{COMPOSER}: not an object")
    if "version" not in data:
        return None
    for m in JSON_VERSION.finditer(text):
        written = text[: m.start(1)] + version + text[m.end(1) :]
        if m.group(1) == data["version"] and json.loads(written) == {**data, "version": version}:
            return m.group(1), written
    raise PrepareError(f"{COMPOSER}: its version stands on no line of its own, which this script sets")


def kept(path: Path) -> str:
    """A file's text with its line ends as they stand, which a text read would turn into `\\n`, so that the release
    writes back the line of the version alone."""
    return path.read_bytes().decode("utf-8")


def versions(tree: Path, version: str) -> list[tuple[Path, str, str]]:
    """Each file the version is set in, with its text as the release writes it and its line, read before anything is
    written: `pyproject.toml` and the lock beside it, then `composer.json`; [] where no manifest names a version."""
    out: list[tuple[Path, str, str]] = []

    def line(path: Path, label: str, before: str) -> str:
        return f"{path.name}: {label} {version} · " + (f"from {before}" if before != version else "as it stood")

    manifest = tree / PYPROJECT
    found = project(kept(manifest), version) if manifest.is_file() else None
    if found is not None:
        name, before, text = found
        out.append((manifest, text, line(manifest, "version", before)))
        lock = tree / UV_LOCK
        if lock.is_file():
            written, held, text = locked(kept(lock), name, version)
            out.append((lock, text, line(lock, written, held)))
    composer = tree / COMPOSER
    carried = composed(kept(composer), version) if composer.is_file() else None
    if carried is not None:
        before, text = carried
        out.append((composer, text, line(composer, "version", before)))
    return out


def standing(tree: Path, version: str, date: str, redate: bool) -> list[str]:
    """The line of a section of the version that a run before wrote, where it stands as this run would write it: its
    tag not set, nothing come since that it would take, and no other date asked for; [] where the assembler runs."""
    changes = assembler()
    text = changes.read(tree)
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*", text, re.M)
    if m is None or changes.tagged(tree, version) != "" or changes.notes(tree):
        return []
    if redate and changes.dated(text, version) != date:
        return []
    return [f"{changes.FILE}: {m.group(0)} · as it stood"]


def prepare(tree: Path, version: str, date: str, redate: bool = False) -> list[str]:
    """Prepare the release of `version` in the tree, its section dated `date`, and give its lines: the section by the
    assembler, then the version of each manifest that names one and of the lock. `redate`, a date given on the command
    line, dates the section of the version whose tag is not set again. PrepareError, nothing written, says why not."""
    tree = Path(tree)
    changes = assembler()
    try:
        files = versions(tree, version)
        lines = standing(tree, version, date, redate) or changes.said(
            changes.assemble(tree, version, date, redate=redate)
        )
    except changes.ChangelogError as e:
        raise PrepareError(str(e)) from None
    for path, text, _ in files:
        if kept(path) != text:
            path.write_bytes(text.encode("utf-8"))
    if not files:
        return [*lines, f"the version stands in the tag v{version}: no manifest names one"]
    return [*lines, *(line for _, _, line in files)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Prepare a release: its section of CHANGELOG.md, its version in the manifest and in the lock."
    )
    ap.add_argument("version", help="the version released, X.Y.Z")
    ap.add_argument(
        "--date",
        help="the section's date, YYYY-MM-DD, the UTC day by default; given, it dates the section of a version whose "
        "tag is not set again",
    )
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the repository")
    a = ap.parse_args(argv)
    if not VERSION.match(a.version):
        ap.error(f"the version is X.Y.Z, not {a.version!r}")
    if a.date is not None and not DAY.match(a.date):
        ap.error(f"--date is YYYY-MM-DD, not {a.date!r}")
    try:
        lines = prepare(a.root, a.version, a.date or assembler().today(), redate=a.date is not None)
    except PrepareError as e:
        print(e)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
