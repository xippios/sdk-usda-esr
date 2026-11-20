"""``scripts/refresh_upstream.py``'s ``FETCHED.md`` and its writing, offline.

Nothing here sends a request: ``render_fetched`` and ``write_snapshot`` take what a capture
run fetched, here one row and two ESR parts made up for the test alone, written under
``tmp_path``, never to ``docs/upstream/``. ``OBSERVED.md`` is the one file under
``docs/upstream/`` written by hand (conventions §3, sdk-core ADR-0028).
"""

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
FETCHED = "2026-11-20T09:00:00Z"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def a_row() -> object:
    """A row of a document kept as a file, as a capture run makes one."""
    response = script.Response(
        url="https://apps.fas.usda.gov/opendatawebV2/assets/swagger/swagger.json",
        status=200,
        body=b'{"swagger": "2.0"}',
        content_type="application/json",
        etag=None,
        last_modified=None,
        redirects=(),
    )
    return script.Row(response, "a note", script.PORTAL_FILE, b'{"swagger": "2.0"}\n')


def render(*, observed: bool) -> str:
    part = script.EsrPart(
        part={"swagger": "2.0", "info": {"title": "ESR"}},
        kept=1,
        dropped={},
        definitions_kept=0,
        definitions_total=0,
    )
    text: str = script.render_fetched(
        [a_row()],
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
    script.write_snapshot(tmp_path, [a_row()], render(observed=True))
    assert notes.read_text(encoding="utf-8") == "# What ESR does but never documents\n"
    assert (tmp_path / script.PORTAL_FILE).read_bytes() == b'{"swagger": "2.0"}\n'


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
