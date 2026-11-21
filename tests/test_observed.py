"""``docs/upstream/OBSERVED.md`` as committed: what ESR does that no page of the snapshot states.

sdk-core's conventions §3 keep these notes in one file written by hand, which the capture
script neither writes nor checks and ``FETCHED.md`` lists in a row of its own, and give
each note its evidence: the probe that showed it, its date, its operation and its sample, a
recording under ``tests/fixtures/``, or its request where the probe kept no answer. A note
here is a ``###`` section, and its last paragraph, ``Probe:``, names them. ``CLAUDE.md`` and
``params.py`` keep the package's rules and point here.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "xippios" / "usda" / "esr"
UPSTREAM = ROOT / "docs" / "upstream"
OBSERVED = UPSTREAM / "OBSERVED.md"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
CITED = re.compile(r"`((?:tests|docs|src)/[^`\s]+\.[a-z]+)`")
REQUEST = re.compile(r"`GET (/api/esr/[^`\s]+)`")
OPERATION = re.compile(r"`(ESRData_\w+)`")
NOT_KEPT = "kept no answer"
PROBE = re.compile(r"\bprobed\b|\bnot kept\b")
"""How a text tells a probe: probed, or its answer not kept. A size that a task's docstring
gives agents, such as ``tasks.py``'s counts "as measured", tells no probe."""
REFERENCE = re.compile(r"^\[[^\]\n]+\]: \S+\n?", re.MULTILINE)
"""A link reference definition, which renders as nothing and is no note's paragraph."""


def text() -> str:
    return OBSERVED.read_text(encoding="utf-8")


def notes() -> dict[str, list[str]]:
    """Each note's heading and its paragraphs, each paragraph's lines joined by a space.

    A ``##`` heading groups notes and is none itself.
    """
    parts = re.split(r"^(##|###) (.+)$", REFERENCE.sub("", text()), flags=re.MULTILINE)
    return {
        heading: [" ".join(block.split()) for block in body.split("\n\n") if block.strip()]
        for level, heading, body in zip(parts[1::3], parts[2::3], parts[3::3], strict=True)
        if level == "###"
    }


def operations() -> dict[str, re.Pattern[str]]:
    """The snapshot's operations: each ``operationId`` and its path as a pattern."""
    document = json.loads((UPSTREAM / "openapi" / "portal-document.json").read_text("utf-8"))
    found: dict[str, re.Pattern[str]] = {}
    for path, methods in document["paths"].items():
        parts = ["[^/]+" if part.startswith("{") else re.escape(part) for part in path.split("/")]
        for operation in methods.values():
            found[operation["operationId"]] = re.compile("/".join(parts))
    return found


def test_fetched_md_lists_observed_md_in_a_row_of_its_own() -> None:
    fetched = (UPSTREAM / "FETCHED.md").read_text(encoding="utf-8")
    assert f"| OBSERVED.md | - | - | - | - | - | - | - | {HAND} |" in fetched.splitlines()
    assert "Nothing here was edited by hand but `OBSERVED.md`" in " ".join(fetched.split())


def test_every_note_ends_with_its_probe() -> None:
    """The date, an operation of the snapshot, and a recording or a request."""
    known = operations()
    found = notes()
    assert found
    for heading, paragraphs in found.items():
        probe = paragraphs[-1]
        assert probe.startswith("Probe: "), heading
        assert DATE.search(probe), heading
        named = OPERATION.findall(probe)
        assert named, heading
        assert set(named) <= set(known), heading
        assert CITED.search(probe) or REQUEST.search(probe), heading


def test_every_probe_a_note_names_has_its_own_date() -> None:
    """A recording's day, from its ``recorded_at``, is a date of its ``Probe:`` paragraph,
    and a request that kept no answer has a date in its own sentence."""
    for heading, paragraphs in notes().items():
        probe = paragraphs[-1]
        for path in CITED.findall(probe):
            if path.startswith("tests/fixtures/"):
                recorded = json.loads((ROOT / path).read_text("utf-8"))["recorded_at"]
                assert recorded[:10] in DATE.findall(probe), f"{heading}: {path}"
        for sentence in re.split(r"(?<=\.) (?=[A-Z])", probe):
            if REQUEST.search(sentence):
                assert DATE.search(sentence), f"{heading}: {sentence}"


def test_a_probe_that_kept_no_answer_names_its_request() -> None:
    """Where no recording holds the answer, the request stands in its place."""
    for heading, paragraphs in notes().items():
        if NOT_KEPT in paragraphs[-1]:
            assert REQUEST.search(paragraphs[-1]), heading


def test_every_request_is_one_of_the_snapshots_operations() -> None:
    paths = REQUEST.findall(text())
    assert paths
    patterns = operations().values()
    assert [path for path in paths if not any(p.fullmatch(path) for p in patterns)] == []


def test_every_file_the_notes_cite_exists() -> None:
    cited = CITED.findall(text())
    assert cited
    assert [path for path in cited if not (ROOT / path).is_file()] == []


def test_the_rules_point_to_the_notes() -> None:
    """``CLAUDE.md`` and ``params.py`` say what the package does with what ESR does."""
    for path in (ROOT / "CLAUDE.md", PACKAGE / "params.py"):
        rules = " ".join(path.read_text(encoding="utf-8").split())
        assert "docs/upstream/OBSERVED.md" in rules, path.name


def test_no_probe_stands_outside_the_notes() -> None:
    """The probes themselves, kept or not, stand in ``OBSERVED.md`` alone: neither
    ``CLAUDE.md`` nor any module of the package tells one."""
    found = [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for path in [ROOT / "CLAUDE.md", *sorted(PACKAGE.rglob("*.py"))]
        for match in PROBE.finditer(" ".join(path.read_text(encoding="utf-8").split()))
    ]
    assert found == []
