"""``scripts/refresh_upstream.py``'s ``FETCHED.md`` and its writing, offline.

Nothing here sends a request: ``render_fetched`` and ``write_snapshot`` take what a capture
run fetched, here one row of the portal's document whose body the snapshot gives, and its
ESR part as ``document_row`` cuts it, written under ``tmp_path``, never to
``docs/upstream/``. ``OBSERVED.md`` is the one file under ``docs/upstream/`` written by hand
(conventions §3, sdk-core ADR-0028).
"""

import importlib.util
import itertools
import json
import re
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
UPSTREAM = ROOT / "docs" / "upstream"
FETCHED = "2026-11-20T09:00:00Z"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"
TABLE = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


PORTAL = UPSTREAM / script.PORTAL_FILE


def a_row() -> tuple[object, object]:
    """A row of the portal's document kept as a file, and its ESR part, as a run makes them.

    NOT RECORDED as served: the body is composed from what the snapshot documents, the ESR
    part of the portal's document that the capture of 2026-11-20 kept in ``PORTAL``, read at
    test time without its final newline, in the shape upstream answered the whole document,
    the text ``json.dumps(indent=2, ensure_ascii=False)`` reproduces (conventions §10). The
    tests assert what the script makes of it, never that upstream sends it.
    """
    response = script.Response(
        url=script.PORTAL_SWAGGER_URL,
        status=200,
        body=PORTAL.read_bytes().removesuffix(b"\n"),
        content_type="application/json",
        etag=None,
        last_modified=None,
        redirects=(),
    )
    row, part = script.document_row(script.PORTAL_FILE, response)
    return row, part


def render(*, observed: bool) -> str:
    row, part = a_row()
    text: str = script.render_fetched(
        [row],
        part,
        part,
        "main.0123abcd.js",
        "https://apps.fas.usda.gov/opendata/swagger/docs/v1",
        FETCHED,
        observed,
    )
    return text


def test_fetched_md_lists_observed_md_in_a_row_of_its_own() -> None:
    """Once ``OBSERVED.md`` exists, the table lists it as written by hand."""
    text = render(observed=True)
    row = f"| {script.OBSERVED} | - | - | - | - | - | - | - | {HAND} |"
    assert row in text.splitlines()
    assert f"edited by hand but `{script.OBSERVED}`" in " ".join(text.split())


def test_fetched_md_names_no_observed_md_while_there_is_none() -> None:
    text = render(observed=False)
    assert script.OBSERVED not in text
    assert "Nothing here was edited by hand." in " ".join(text.split())


def test_fetched_md_cites_core_s_standing_record() -> None:
    """The two sentences that cite the record of upstream fidelity cite it as it stands at
    sdk-core 0.4.0, sdk-core ADR-0028, which superseded sdk-core ADR-0003; ``FETCHED.md``
    takes them at the next capture (conventions §15)."""
    text = " ".join(render(observed=False).split())
    assert text.count("(sdk-core ADR-0028)") == 2
    assert "ADR-0003" not in text


def test_a_snapshot_leaves_observed_md_as_written(tmp_path: Path) -> None:
    """The run writes its files and ``FETCHED.md`` and never touches the notes."""
    notes = tmp_path / script.OBSERVED
    notes.write_text("# What ESR does but never documents\n", encoding="utf-8")
    (tmp_path / "FETCHED.md").write_text("old\n", encoding="utf-8")
    row, _ = a_row()
    script.write_snapshot(tmp_path, [row], render(observed=True))
    assert notes.read_text(encoding="utf-8") == "# What ESR does but never documents\n"
    assert (tmp_path / script.PORTAL_FILE).read_bytes() == PORTAL.read_bytes()


def test_the_committed_fetched_md_is_the_scripts_text() -> None:
    """Beside the rows of what the capture fetched, ``FETCHED.md`` is ``render_fetched``'s
    text for the committed snapshot, the row of ``OBSERVED.md`` where the file exists, as a
    run's ``main`` renders it. The prose quotes the two ESR parts under ``openapi/``, the
    backend document's URL and the bundle's name, which the fetched rows hold."""
    committed = (UPSTREAM / "FETCHED.md").read_text(encoding="utf-8").splitlines()
    head = committed.index(TABLE) + 1
    table = itertools.takewhile(lambda line: line.startswith("| "), committed[head:])
    rows = [line for line in table if not line.startswith(f"| {script.OBSERVED} |")]
    by_file = {line.split(" | ")[0].removeprefix("| "): line.split(" | ") for line in rows}
    bundle = re.search(r"loads the bundle `(main\.[0-9a-f]+\.js)`", "\n".join(rows))
    assert bundle is not None
    parts = [
        script.EsrPart(
            part=json.loads((UPSTREAM / path).read_text(encoding="utf-8")),
            kept=0,
            dropped={},
            definitions_kept=0,
            definitions_total=0,
        )
        for path in (script.PORTAL_FILE, script.BACKEND_FILE)
    ]
    rendered = script.render_fetched(
        [],
        *parts,
        bundle.group(1),
        by_file[script.BACKEND_FILE][1],
        FETCHED,
        (UPSTREAM / script.OBSERVED).is_file(),
    ).splitlines()
    assert len(rows) == 7
    assert committed[:head] + committed[head + len(rows) :] == rendered


def test_fetched_md_says_when_and_where_the_portal_document_was_found() -> None:
    """How this is captured dates the find of the portal's Swagger document.

    It states what was fetched, when and where the URL stood, which a reader of the snapshot
    can check against the portal, and names nobody who fetched it or where they kept the copies;
    nor does the script's own text (https://github.com/xippios/sdk-usda-esr/issues/17).
    """
    text = " ".join(render(observed=False).split())
    found = (
        f"On {script.PORTAL_SWAGGER_FOUND_ON}, when sdk-usda-psd's snapshot was set up, the"
        " portal page and its JavaScript bundle were fetched into a temporary directory and"
        " that URL was found in the bundle's Swagger UI configuration; those copies have"
        " since been deleted, and this script reuses the URL."
    )
    assert found in text
    assert "scratch" not in text
    assert "scratch" not in SCRIPT.read_text(encoding="utf-8")
