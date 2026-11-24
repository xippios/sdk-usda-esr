#!/usr/bin/env python3
"""Write the section of a release into `CHANGELOG.md` from the fragments under `changelog/`, and remove them.

    python3 -I scripts/changelog_assemble.py <version>                    writes `## [<version>] - <the UTC day>`
    python3 -I scripts/changelog_assemble.py <version> --date YYYY-MM-DD  dates it by that day, and dates again the
                                                                         section of a version whose tag is not set
    python3 -I scripts/changelog_assemble.py --notes                      writes nothing, and prints the next section

A fragment is one change, `changelog/<group>-<slug>.md`, `<group>` one of added, changed, fixed, removed, security and
breaking, holding its bullet as it will stand in the section. A note is a line under the bullet, indented by two
spaces: `- Hand-apply: <text>` for what a repository that takes the change applies by hand, which stays under its
bullet, and `- Restates: changelog/<group>-<slug>.md` for a change that restates another of the same release, which is
folded into it: the bullet of the last of a chain keeps its group, its place and its text, and takes the citations it
lacks and a restated Hand-apply note where it has none. `changelog/README.md` and a hidden file are no fragments.

The section holds the groups in that order and only those with entries, in each the fragments newest first by the
commit that added them, one not committed yet before all, then what a `## [Unreleased]` section held, which the section
replaces; without one it stands above the last release. The section of a version that `CHANGELOG.md` holds already
takes the fragments while the tag `v<version>` is not set, first in each group, and is refused once it is. A repository
without `changelog/` keeps its `## [Unreleased]` section on top, empty, and its entries go under the version.

It prints one line per item: the heading with the bullets of each group, a `folded:` line per restated bullet and a
`removed:` line per fragment. It exits 0 when it wrote the section or printed the notes; 1 when it wrote nothing, the
reason on one line: no `CHANGELOG.md`, nothing to release, a file under `changelog/` that is no fragment, a restatement
it cannot fold or a version released already; and 2 on a command line it does not take. It needs the standard library
and git alone, so people, CI and a repository's tools run the same script. A repository carries it byte for byte as
its template renders it and edits no copy: the template's next release brings the next version.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

FILE = "CHANGELOG.md"
DIRECTORY = "changelog"
README = "README.md"  # the folder's own note, never a fragment: it keeps the folder between releases
GROUPS = ("added", "changed", "fixed", "removed", "security", "breaking")  # in this order, `breaking` after `security`
NAME = re.compile(rf"^(?:{'|'.join(GROUPS)})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
SHAPE = f"<group>-<slug>.md, <group> one of {', '.join(GROUPS)}"
UNRELEASED = re.compile(r"^## \[Unreleased\][ \t]*\n", re.M)
HEADING = re.compile(r"^## \[", re.M)
GROUP = re.compile(r"^### (\S.*?)[ \t]*$", re.M)
BULLET = re.compile(r"^- ", re.M)
LINKS = re.compile(r"^\[[^\]\n]+\]:[ \t]", re.M)  # the link references that close a Keep a Changelog file
NEWEST = sys.maxsize  # a fragment no commit added yet comes before every committed one
# A fragment's notes, each a line under its bullet `  - <kind>: <text>`: Hand-apply stays under the bullet in the
# section, Restates names the fragment of the same release that the bullet restates, which is folded into it.
HAND_APPLY, RESTATES = "Hand-apply", "Restates"
NOTE = re.compile(r"^  - ([^\s:][^:]*):(?:[ \t]+(.*))?$")
NOTE_FORM = "`  - Hand-apply: <text>` or `  - Restates: changelog/<group>-<slug>.md`"
# what a bullet is read without, each blanked to its length so an offset still names its line
BLANKED = re.compile(r"``.+?``|`[^`\n]+`|\"[^\"\n]*\"|“[^”\n]*”|\b(?:e\.g|i\.e)\.")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMEOUT = 60


class ChangelogError(Exception):
    """No CHANGELOG to write, a file under `changelog/` that is no fragment, a version released already, a section of
    another shape than Keep a Changelog's, nothing to release."""


@dataclass(frozen=True)
class Fragment:
    name: str  # the file's name under `changelog/`
    group: str
    text: str  # its bullet, stripped


@dataclass
class Released:
    heading: str  # `## [<version>] - <date>`
    counts: dict[str, int] = field(default_factory=dict)  # the bullets of each group, by its heading
    removed: list[str] = field(default_factory=list)  # the fragments removed, `changelog/<name>`, sorted
    folded: list[tuple[str, str]] = field(default_factory=list)  # (restated, successor), `changelog/<name>` each
    redated: str = ""  # the date the section had, where the release dated it again


@dataclass
class Parsed:
    """A fragment's text line by line: its bullet's lines, the notes under it and the lines that are neither."""

    first: int = 0  # the bullet's line in the file, from 1; 0 for a text without one
    bullet: list[str] = field(default_factory=list)  # from `- ` to its last continued line, as written
    notes: list[list[Any]] = field(default_factory=list)  # [line, kind, text], a note's continued lines joined
    stray: list[tuple[int, str]] = field(default_factory=list)  # (line, why it is neither)


def parsed(text: str) -> Parsed:
    """The lines of a fragment: the first that is not blank opens the bullet; a line indented by two spaces continues
    it until the first note, `  - <kind>: <text>`, and a line indented by four continues that note; a blank line
    between them, a second bullet or any other line is stray, named with its line."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip()), len(lines))
    end = len(lines)
    while end > start and not lines[end - 1].strip():
        end -= 1
    out = Parsed(first=start + 1 if start < end else 0)
    for i in range(start, end):
        line, number = lines[i], i + 1
        note = NOTE.match(line)
        if i == start:
            out.bullet.append(line)
        elif not line.strip():
            out.stray.append((number, "a blank line inside the fragment: the bullet and its notes stand line by line"))
        elif note:
            out.notes.append([number, note.group(1).strip(), (note.group(2) or "").strip()])
        elif out.notes and line.startswith("    ") and not line.lstrip().startswith("- "):
            out.notes[-1][2] = f"{out.notes[-1][2]} {line.strip()}".strip()
        elif not out.notes and line.startswith("  ") and not line.lstrip().startswith("- "):
            out.bullet.append(line)
        elif line.startswith("- "):
            out.stray.append((number, "a second bullet: a fragment holds one change"))
        elif out.notes:  # a note stands on one line or continues by four spaces
            out.stray.append((number, f"a line after a note continues it, indented by four spaces, or is another "
                                      f"note, {NOTE_FORM}"))  # fmt: skip
        else:
            out.stray.append((number, f"neither the bullet, its lines indented by two spaces, nor a note, {NOTE_FORM}"))
    return out


def blanked(text: str) -> str:
    """`text` with its code spans, quotations and `e.g.` blanked to their length, so their dots, semicolons and
    parentheses count for nothing and an offset still names its line."""
    return BLANKED.sub(lambda m: "x" * len(m.group(0)), text)


def closing(blank: str) -> tuple[int, int] | None:
    """(open, close) of the parentheses that end a blanked bullet, None when it ends otherwise."""
    end = len(blank.rstrip())
    if not end or blank[end - 1] != ")":
        return None
    depth = 0
    for i in range(end - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(blank[i], 0)
        if depth == 0:
            return i, end - 1
    return None


def citations(bullet: str) -> list[str]:
    """The citations in the parentheses that end a bullet, in their order; [] when none end it."""
    found = closing(blanked(bullet))
    if found is None:
        return []
    return [item.strip() for item in bullet[found[0] + 1 : found[1]].split(",") if item.strip()]


def restated(text: str) -> list[str]:
    """The fragments a fragment's Restates notes name, `changelog/` dropped, in their order."""
    prefix = f"{DIRECTORY}/"
    return [value[len(prefix) :] if value.startswith(prefix) else value
            for _, kind, value in parsed(text).notes if kind == RESTATES]  # fmt: skip


def merged(text: str, others: list[str]) -> str:
    """A successor's text with the bullets it restates folded in: its bullet as written, the citations of `others`
    it lacks added in their order inside its closing parentheses, then its notes but Restates, each on one line. One
    change keeps one Hand-apply note: the successor's stands, and the first of `others` gives its own only where the
    successor has none."""
    lines = parsed(text)
    bullet = "\n".join(lines.bullet)
    own = citations(bullet)
    more = [c for other in others for c in citations("\n".join(parsed(other).bullet))]
    added = list(dict.fromkeys(c for c in more if c not in own))
    if added:
        ends = closing(blanked(bullet))
        if ends is None:
            bullet = f"{bullet.rstrip()} ({', '.join(added)})"
        else:
            bullet = f"{bullet[: ends[1]]}, {', '.join(added)}{bullet[ends[1] :]}"
    notes = [(kind, value) for _, kind, value in lines.notes if kind != RESTATES]
    if not any(kind == HAND_APPLY for kind, _ in notes):
        restated_notes = [value for other in others for _, kind, value in parsed(other).notes if kind == HAND_APPLY]
        notes += [(HAND_APPLY, value) for value in restated_notes[:1]]
    return "\n".join([bullet, *(f"  - {kind}: {value}" for kind, value in notes)])


def folded(found: list[Fragment]) -> tuple[list[Fragment], list[tuple[str, str]]]:
    """The fragments as the section takes them: a bullet that another of the release restates,
    `  - Restates: changelog/<name>`, is folded into its successor, the last of a chain, which keeps its group, its
    place and its text and takes the citations it lacks and a restated Hand-apply note where it has none; and
    (restated, successor) for each fold, `changelog/<name>` each, in the order of the fragments. ChangelogError names
    a Restates of a fragment the release does not hold, a fragment two others restate, and restatements in a
    circle."""
    names = {f.name: f for f in found}
    successor: dict[str, str] = {}
    wrong: list[str] = []
    for f in found:
        for target in restated(f.text):
            if target == f.name or target not in names:
                wrong.append(f"{DIRECTORY}/{f.name} restates {DIRECTORY}/{target}, which is no other fragment under "
                             f"{DIRECTORY}/: fold the bullet into it by hand and drop its Restates note")  # fmt: skip
            elif target in successor:
                wrong.append(f"{DIRECTORY}/{target} is restated by both {DIRECTORY}/{successor[target]} and "
                             f"{DIRECTORY}/{f.name}: one bullet restates it")  # fmt: skip
            else:
                successor[target] = f.name
    last: dict[str, str] = {}
    for name in successor:
        seen, at = {name}, successor[name]
        while at in successor and at not in seen:
            seen.add(at)
            at = successor[at]
        if at in successor:
            wrong.append(f"{DIRECTORY}/{name} is restated in a circle: one bullet of the circle restates the others")
        else:
            last[name] = at
    if wrong:
        raise ChangelogError("; ".join(dict.fromkeys(wrong)))
    if not successor:
        return found, []
    out = []
    for f in found:
        if f.name in last:
            continue
        others = [g.text for g in found if last.get(g.name) == f.name]
        out.append(Fragment(f.name, f.group, merged(f.text, others)) if others or restated(f.text) else f)
    folds = [(f"{DIRECTORY}/{f.name}", f"{DIRECTORY}/{last[f.name]}") for f in found if f.name in last]
    return out, folds


def keeps(tree: Path) -> bool:
    """The repository keeps its next release's entries as fragments."""
    return (Path(tree) / DIRECTORY).is_dir()


def skipped(name: str) -> bool:
    """The folder's README and a hidden file such as `.gitkeep`: never a fragment, never refused."""
    return name == README or name.startswith(".")


def problem(name: str, text: str) -> str | None:
    """Why the file `changelog/<name>` is no fragment, None when it is one."""
    if not NAME.match(name):
        return f"{DIRECTORY}/{name} is not named {SHAPE}"
    if not text.strip().startswith("- "):
        return f"{DIRECTORY}/{name} holds no bullet: its text starts with `- `, as it will stand in the section"
    return None


def added_at(tree: Path) -> dict[str, int]:
    """The commit time of the commit that last added each file under `changelog/`, by its name; empty outside git.
    `--no-renames`: a fragment renamed is added under its new name."""
    try:
        r = subprocess.run(
            ["git", "-C", str(tree), "log", "--diff-filter=A", "--no-renames", "--format=%ct", "--name-only", "--",
             DIRECTORY],
            capture_output=True, text=True, timeout=TIMEOUT,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return {}
    if r.returncode != 0:
        return {}
    out: dict[str, int] = {}
    when = 0
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            when = int(line)
        elif line:
            out.setdefault(line.rsplit("/", 1)[-1], when)  # the log runs newest first
    return out


def fragments(tree: Path) -> list[Fragment]:
    """The fragments of a tree, newest first by the commit that added each, one not committed yet before all, the
    name breaking a tie; ChangelogError names every file under `changelog/` that is no fragment."""
    folder = Path(tree) / DIRECTORY
    if not folder.is_dir():
        return []
    found: list[Fragment] = []
    wrong: list[str] = []
    for path in sorted(folder.iterdir()):
        if skipped(path.name):
            continue
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        why = problem(path.name, text) if path.is_file() else f"{DIRECTORY}/{path.name} is a directory"
        if why:
            wrong.append(why)
        else:
            found.append(Fragment(path.name, path.name.split("-", 1)[0], text.strip()))
    if wrong:
        raise ChangelogError("; ".join(wrong))
    added = added_at(tree) if found else {}
    return sorted(found, key=lambda f: (-added.get(f.name, NEWEST), f.name))


def unreleased(text: str) -> str | None:
    """The body of the `## [Unreleased]` section of a CHANGELOG, None when there is no such heading."""
    m = UNRELEASED.search(text)
    if not m:
        return None
    rest = HEADING.search(text, m.end())
    return text[m.end() : rest.start() if rest else len(text)]


def groups(body: str) -> tuple[str, dict[str, tuple[str, str]]]:
    """A section's body: its text before the first group, and each group's (heading, text) by the heading in lower
    case, in the order they stand; a group named twice is one."""
    heads = list(GROUP.finditer(body))
    lead = body[: heads[0].start()] if heads else body
    out: dict[str, tuple[str, str]] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        text = body[m.end() : end].strip()
        key = m.group(1).lower()
        heading, held = out.get(key, (m.group(1), ""))
        out[key] = (heading, "\n".join(t for t in (held, text) if t))
    return lead.strip(), out


def assembled(body: str, found: list[Fragment]) -> tuple[str, dict[str, int]]:
    """The body of the release's section and the bullets of each group: the loose entries `## [Unreleased]` held
    first, then the groups of `GROUPS` in their order, each its fragments and then what the section held, then the
    groups the section held outside them, as written; a restated bullet folded into its successor (`folded`)."""
    found = folded(found)[0]
    lead, held = groups(body)
    order = [*GROUPS, *(key for key in held if key not in GROUPS)]
    parts = [lead] if lead else []
    counts: dict[str, int] = {}
    for key in order:
        heading = held[key][0] if key in held else key.capitalize()
        items = [f.text for f in found if f.group == key] + ([held[key][1]] if held.get(key, ("", ""))[1] else [])
        if items:
            text = "\n".join(items)
            parts += [f"### {heading}", text]
            counts[heading] = len(BULLET.findall(text))
    return "\n\n".join(parts), counts


def read(tree: Path) -> str:
    path = Path(tree) / FILE
    if not path.is_file():
        raise ChangelogError(f"no {FILE}")
    return path.read_text(encoding="utf-8")


def write(tree: Path, text: str) -> None:
    (Path(tree) / FILE).write_text(text, encoding="utf-8")


def notes(tree: Path) -> str:
    """The body of the next release's section as the release writes it, stripped; "" when there is nothing to
    release. ChangelogError: no CHANGELOG, a file under `changelog/` that is no fragment, or, in a repository without
    the folder, no `## [Unreleased]` section."""
    text = read(tree)
    body = unreleased(text)
    if not keeps(tree):
        if body is None:
            raise ChangelogError(f"no `## [Unreleased]` section in {FILE}")
        return body.strip()
    return assembled(body or "", fragments(tree))[0].strip()


def nothing(tree: Path) -> str:
    """Why there is nothing to release, when `notes` is empty."""
    if keeps(tree):
        return f"nothing to release: no fragment under {DIRECTORY}/"
    return "nothing to release: the Unreleased section is empty"


def tagged(tree: Path, version: str) -> str | None:
    """The release's tag `v<version>` where the tree's repository holds it, the one tag a release writes, a bare
    `<version>` none; "" when it holds none, None when git could not read its tags."""
    tag = f"v{version}"
    try:
        r = subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
            capture_output=True, text=True, timeout=TIMEOUT,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode == 0:
        return tag
    return "" if r.returncode == 1 else None  # else no repository, or no git


def late(tree: Path, text: str, version: str, found: list[Fragment]) -> Released:
    """Add the fragments to the section of a version whose tag is not set, a release whose branch took the fragment of
    a change merged after the section was written: first in each group, a group the section lacked in its order, the
    heading and what the section held kept; then remove them."""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*", text, re.M)
    assert m is not None  # `release` found it
    ends = [hit.start() for hit in (HEADING.search(text, m.end()), LINKS.search(text, m.end())) if hit]
    end = min(ends, default=len(text))
    section, counts = assembled(text[m.end() : end], found)
    rest = text[end:]
    text = text[: m.start()] + f"{m.group(0)}\n\n{section}\n" + (f"\n{rest}" if rest else "")
    write(tree, text)
    for f in found:
        (Path(tree) / DIRECTORY / f.name).unlink()
    return Released(m.group(0), counts, sorted(f"{DIRECTORY}/{f.name}" for f in found), folded(found)[1])


def dated(text: str, version: str) -> str | None:
    """The date of the version's heading, `## [<version>] - <date>`, in a CHANGELOG's text, which a release's tag takes
    with the section. None for an undated section, one in development, and for a version the text lacks."""
    m = re.search(rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})\b", text, re.M)
    return m.group(1) if m else None


def release(tree: Path, version: str, date: str, redate: bool = False) -> Released:
    """Write `## [<version>] - <date>` into the tree's CHANGELOG and remove the fragments it took. With fragments the
    section replaces `## [Unreleased]`, or stands above the last release; without the folder `## [Unreleased]` stays
    on top, empty, and its entries go under the version as they stood. A section of the version that stands already
    takes the fragments while its tag is not set (`late`), and is refused once it is, or when git cannot read the
    tags, or in a repository without the folder. With `redate`, a date given on the command line, that untagged
    section takes `date`, with no fragment as well, since a release that waited past its heading's UTC day would tag a
    section dated a day before its tag. Nothing is written when ChangelogError says why not."""
    tree = Path(tree)
    text = read(tree)
    heading = f"## [{version}] - {date}"
    if re.search(rf"^## \[{re.escape(version)}\]", text, re.M):
        already = f"{FILE} has a section [{version}] already"
        if not keeps(tree):
            raise ChangelogError(already)
        tag = tagged(tree, version)
        if tag is None:
            raise ChangelogError(f"{already}, and git did not read its tag")
        if tag:
            raise ChangelogError(f"{already}, tagged {tag}")
        found = fragments(tree)
        was = dated(text, version) or ""
        if redate and was != date:
            text = re.sub(rf"^## \[{re.escape(version)}\][^\n]*", lambda _: heading, text, count=1, flags=re.M)
            if not found:
                write(tree, text)
                return Released(heading, redated=was or "undated")
            return replace(late(tree, text, version, found), redated=was or "undated")
        if not found:
            raise ChangelogError(f"{FILE} has the section [{version}], untagged, and no fragment under {DIRECTORY}/")
        return late(tree, text, version, found)
    body = unreleased(text)
    if not keeps(tree):
        if body is None:
            raise ChangelogError(f"no `## [Unreleased]` section in {FILE}")
        write(tree, UNRELEASED.sub(f"## [Unreleased]\n\n{heading}\n", text, 1))
        return Released(heading, assembled(body, [])[1])
    found = fragments(tree)
    section, counts = assembled(body or "", found)
    new = f"{heading}\n\n{section}\n" if section else f"{heading}\n"
    m = UNRELEASED.search(text)
    start = m.start() if m else None
    rest = HEADING.search(text, m.end() if m else 0)
    if start is None:  # above the last release, else at the end
        start = rest.start() if rest else None
    if start is None:
        text = text.rstrip("\n") + "\n\n" + new
    else:
        text = text[:start] + new + ("\n" + text[rest.start() :] if rest else "")
    write(tree, text)
    for f in found:
        (tree / DIRECTORY / f.name).unlink()
    return Released(heading, counts, sorted(f"{DIRECTORY}/{f.name}" for f in found), folded(found)[1])


def assemble(tree: Path, version: str, date: str, redate: bool = False) -> Released:
    """The command: `release`, and ChangelogError, nothing written, where there is nothing to release. A date given on
    the command line, `redate`, dates the untagged section of the version again with no fragment as well."""
    tree = Path(tree)
    again = redate and re.search(rf"^## \[{re.escape(version)}\]", read(tree), re.M)
    if not again and not notes(tree):
        raise ChangelogError(nothing(tree))
    return release(tree, version, date, redate=redate)


def said(released: Released) -> list[str]:
    """The lines of a release written: the heading with the bullets of each group and the date it had where it was
    dated again, then a `folded:` line per restated bullet and a `removed:` line per fragment."""
    counts = ", ".join(f"{group} {n}" for group, n in released.counts.items())
    redated = f" · dated again from {released.redated}" if released.redated else ""
    head = f"{FILE}: {released.heading}" + (f" · {counts}" if counts else "") + redated
    return [
        head,
        *(f"folded: {restated} into {successor}" for restated, successor in released.folded),
        *(f"removed: {path}" for path in released.removed),
    ]


def today() -> str:
    """The UTC day: a release's tag reads its heading's date as a UTC day, never the machine's local day."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017 (Python before 3.11 runs it too)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the section of a release into CHANGELOG.md from the fragments under changelog/."
    )
    ap.add_argument("version", nargs="?", help="the version released, X.Y.Z")
    ap.add_argument(
        "--date",
        help="the section's date, YYYY-MM-DD, the UTC day by default; given, it dates the section of a version whose "
        "tag is not set again",
    )
    ap.add_argument("--notes", action="store_true", help="write nothing; print the body of the next section")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the repository")
    a = ap.parse_args(argv)
    if a.notes and (a.version is not None or a.date is not None):
        ap.error("--notes takes no version and no --date")
    if not a.notes and a.version is None:
        ap.error("the version is required, X.Y.Z")
    if a.version is not None and not VERSION.match(a.version):
        ap.error(f"the version is X.Y.Z, not {a.version!r}")
    if a.date is not None and not DAY.match(a.date):
        ap.error(f"--date is YYYY-MM-DD, not {a.date!r}")
    root: Path = a.root
    try:
        if a.notes:
            body = notes(root)
            if not body:
                raise ChangelogError(nothing(root))
            print(body)
            return 0
        released = assemble(root, a.version, a.date or today(), redate=a.date is not None)
    except ChangelogError as e:
        print(e)
        return 1
    for line in said(released):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
