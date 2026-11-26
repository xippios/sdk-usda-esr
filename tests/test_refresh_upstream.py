"""``scripts/refresh_upstream.py``'s own code, offline: its ``Snapshot`` and its own hooks.

The script declares a ``Snapshot`` that sdk-core's frame runs, ``xippios.core.refresh``
(conventions §3): the fetch through core's client, ``FETCHED.md``, the write and ``--check``
are the frame's, and core's tests hold them. The portal's pages, the hooks that read them and
the paragraphs that say how are the kit of the FAS portal in ``xippios.usda.fas``, whose tests
hold its units (https://github.com/xippios/sdk-usda-esr/issues/33). The tests here hold what
the script declares on the kit, its own pages, its own paragraph and its own notes, and that
the kit's cut reproduces the committed ESR part. Nothing here sends a request or writes under
``docs/upstream/``. ``OBSERVED.md`` is the one file under ``docs/upstream/`` written by hand
(conventions §3, sdk-core ADR-0028).
"""

import importlib.util
from pathlib import Path
from types import ModuleType

from xippios.core.refresh import Page, Response, Row
from xippios.usda.fas.portal import Portal

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
UPSTREAM = ROOT / "docs" / "upstream"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


PORTAL_FILE = "openapi/portal-document.json"
"""The committed ESR part of the portal's document, the file of the kit's second page."""
PORTAL = UPSTREAM / PORTAL_FILE


def portal_page() -> Page:
    pages: tuple[Page, ...] = script.SNAPSHOT.pages
    (page,) = [page for page in pages if page.file == PORTAL_FILE]
    return page


def answer(url: str, status: int, body: bytes, content_type: str) -> Response:
    """An answer as a run reads it, composed by the test.

    It is an input of the test, not an answer from USDA FAS.
    """
    return Response(
        url=url,
        status=status,
        body=body,
        content_type=content_type,
        etag=None,
        last_modified=None,
        redirects=(),
    )


def portal_answer() -> Response:
    """The portal's document as a run reads it, here composed from the snapshot.

    NOT RECORDED as served: the body is composed from what the snapshot documents, the ESR
    part of the portal's document that the capture of 2026-11-20 kept in ``PORTAL``, read at
    test time without its final newline, in the shape upstream answered the whole document,
    the text ``json.dumps(indent=2, ensure_ascii=False)`` reproduces. The tests assert what
    the script makes of it, never that upstream sends it. The answer is an input of the test,
    not an answer from USDA FAS. (conventions §10; sdk-core ADR-0049, decision 10)
    """
    return answer(
        portal_page().url, 200, PORTAL.read_bytes().removesuffix(b"\n"), "application/json"
    )


def test_the_script_builds_on_the_kit_of_the_portal_for_esr() -> None:
    """One ``Portal`` for ESR's prefix, whose hooks the snapshot takes, but ``note``, which
    names the script's own pages first."""
    assert isinstance(script.PORTAL, Portal)
    assert (script.PORTAL.prefix, script.PORTAL.service) == ("/api/esr/", "ESR")
    snapshot = script.SNAPSHOT
    assert (snapshot.name, snapshot.slug) == ("USDA FAS Export Sales Reporting", "usda-esr")
    assert snapshot.reduce == script.PORTAL.reduce
    assert snapshot.linked == script.PORTAL.linked
    assert snapshot.sections == script.PORTAL.sections
    assert snapshot.note is script.note


def test_reduce_cuts_a_document_to_its_esr_part_as_committed() -> None:
    """The kit's cut, applied to the ESR part itself, gives back the committed part byte for
    byte: its paths, the definitions they reference, in upstream order,
    ``json.dumps(indent=2, ensure_ascii=False)`` and a final newline."""
    assert script.SNAPSHOT.reduce(portal_page(), portal_answer()) == PORTAL.read_bytes()


def test_a_document_row_counts_the_paths_kept_and_dropped() -> None:
    """The script's ``note`` leaves a document's row to the kit, which names what the cut
    kept; the frame adds that the row's Bytes and sha256 are the whole document's
    (``excerpt``)."""
    page, response = portal_page(), portal_answer()
    assert page.excerpt
    content = script.SNAPSHOT.reduce(page, response)
    note = script.SNAPSHOT.note(Row(page, response, content, page.note))
    assert note == (
        "ESR part: kept 7 `/api/esr/` paths; dropped none (out of scope here, own packages); "
        "kept 0 of 0 definitions"
    )


def test_the_snapshot_declares_its_pages_in_order() -> None:
    """The kit's pages first, the portal's three, whose own tests hold them; then ESR's own:
    the program page the CDN refuses, which goes to ``Not fetched``, and the two ESR query
    URLs, recorded by their 404."""
    pages = script.SNAPSHOT.pages
    assert pages[:3] == script.PORTAL.pages
    assert [(page.url, page.file, page.status) for page in pages[3:]] == [
        (script.ESR_PROGRAM_URL, None, 403),
        *((url, None, 404) for url in script.ESRQUERY_URLS),
    ]
    assert portal_page() in pages[:3], "the kit's document page writes the committed part"
    refused = pages[3]
    assert (refused.stable, refused.names) == (False, "Access Denied")
    assert script.SNAPSHOT.attribution == (), "neither document states a copyright line"


def test_an_esr_query_url_s_row_says_what_it_answered() -> None:
    """The script's own note for the two ESR query URLs, from the answer: its status was
    expected to be a shell when the snapshot was set up, and the body it answers now."""
    for url in script.ESRQUERY_URLS:
        page = next(page for page in script.SNAPSHOT.pages if page.url == url)
        empty = answer(url, 404, b"", "text/html; charset=utf-8")
        assert script.note(Row(page, empty, None, page.note)) == (
            "404 Not Found with an empty body; when this snapshot was set up on 2026-10-25 "
            "this URL was expected to serve the ESR query application's client-rendered "
            "shell, and it does not"
        )
        html = answer(url, 404, b"<html></html>", "text/html; charset=utf-8")
        assert script.note(Row(page, html, None, page.note)).startswith(
            "404 Not Found with a text/html body; "
        )


def test_the_capture_is_the_kit_s_then_esr_s_own_paragraph() -> None:
    """How this is captured: the kit's four paragraphs, then ESR's own on the pages that
    answer 404 and the program page, which leaves the shells' bound to the kit's."""
    capture = script.SNAPSHOT.capture
    assert capture.startswith(f"{script.PORTAL.capture}\n\n")
    own = capture.removeprefix(f"{script.PORTAL.capture}\n\n")
    assert own.startswith("Pages that answer 404 get no file")
    assert "\n\n" not in own, "one paragraph of the script's own"
    assert "bytes" not in own, "the shells' bound is the kit's to state"


def test_fetched_md_says_when_and_where_the_portal_document_was_found() -> None:
    """How this is captured dates the find of the portal's Swagger document.

    It states what was fetched, when and where the URL stood, which a reader of the snapshot
    can check against the portal, and names nobody who fetched it or where they kept the copies;
    nor does the script's own text (https://github.com/xippios/sdk-usda-esr/issues/17).
    """
    text = " ".join(script.SNAPSHOT.capture.split())
    found = (
        "On 2026-10-23, when sdk-usda-psd's snapshot was set up, the portal page and its"
        " JavaScript bundle were fetched into a temporary directory and that URL was found in"
        " the bundle's Swagger UI configuration; those copies have since been deleted, and this"
        " script reuses the URL."
    )
    assert found in text
    assert "scratch" not in text
    assert "scratch" not in SCRIPT.read_text(encoding="utf-8")
