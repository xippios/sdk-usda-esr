"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

The script declares the snapshot, a ``Snapshot`` of ``xippios.core.refresh``, and runs it on
core's frame (conventions §3): the fetch through core's client, which the frame builds without
credentials and names after the package, the attribution check, ``FETCHED.md``, the write and
``--check`` are the frame's, the same in every source. The FAS Open Data Services portal
(https://apps.fas.usda.gov/opendatawebV2/) documents ESR, GATS and PSD alike, and what the three
FAS sources read of it is the kit of the shared package, ``xippios.usda.fas.portal``'s
``Portal``: the portal's pages, the cut of its two Swagger documents to one service's paths, the
backend document that the classic Swagger UI names, the comparison of the two, and the
paragraphs that say how. This script keeps what is ESR's own: the prefix ``/api/esr/``, the
program page, the two ESR query URLs, their notes and the paragraph on them. It writes:

- ``openapi/portal-document.json``: the ESR part of the portal's document;
- ``openapi/backend-docs-v1.json``: the ESR part of the API's own document;
- ``FETCHED.md``: written whole by the frame, one row per file and per page recorded without
  a file (the two shells and the ESR query URLs, which answer 404), and the program page the
  CDN refuses to headless clients under ``Not fetched``.

No key is needed or read. Run from the repository root::

    uv run python scripts/refresh_upstream.py            # fetch and write
    uv run python scripts/refresh_upstream.py --check    # fetch and compare, write nothing
"""

from xippios.core.refresh import Page, Row, Snapshot, run
from xippios.usda.fas.portal import Portal

PORTAL = Portal("/api/esr/")
"""The portal as ESR's snapshot reads it: its pages first, and its hooks."""

ESR_PROGRAM_URL = "https://www.fas.usda.gov/programs/export-sales-reporting-program"
"""The Export Sales Reporting program page, this package's ``Upstream`` URL."""
ESRQUERY_URLS = (
    "https://apps.fas.usda.gov/esrquery/",
    "https://apps.fas.usda.gov/esrquery/esrq.aspx",
)
"""The ESR query application's URLs; both answered 404 when this snapshot was set up."""
SET_UP_ON = "2026-10-25"
"""The day this package's snapshot was set up."""


def note(row: Row) -> str:
    """The row's note: what an ESR query URL answered, else the kit's or the page's own."""
    page, response = row.page, row.response
    if page.url in ESRQUERY_URLS:
        media = (response.content_type or "").split(";")[0].strip()
        body = f"a {media} body" if response.body else "an empty body"
        return (
            f"404 Not Found with {body}; when this snapshot was set up on {SET_UP_ON} this URL "
            "was expected to serve the ESR query application's client-rendered shell, and it "
            "does not"
        )
    return PORTAL.note(row)


OWN = (
    "Pages that answer 404 get no file, only a row with their HTTP status and the size and "
    f"sha256 of the body. The ESR query URLs {ESRQUERY_URLS[0]} and {ESRQUERY_URLS[1]} were "
    f"expected, when this snapshot was set up on {SET_UP_ON}, to serve the ESR query "
    "application's client-rendered shell; both answer 404, and their rows record what is "
    f"answered. The Export Sales Reporting program page, {ESR_PROGRAM_URL}, answers 403 Access "
    "Denied at the CDN edge to headless clients, a body that carries a per-request reference "
    "number."
)
"""ESR's own paragraph of "How this is captured", after the kit's four."""


SNAPSHOT = Snapshot(
    name="USDA FAS Export Sales Reporting",
    slug="usda-esr",
    pages=(
        *PORTAL.pages,
        Page(
            ESR_PROGRAM_URL,
            status=403,
            stable=False,
            names="Access Denied",
            note="the Export Sales Reporting program page; 403 Access Denied at the CDN edge",
        ),
        *(Page(url, status=404) for url in ESRQUERY_URLS),
    ),
    capture=f"{PORTAL.capture}\n\n{OWN}",
    reduce=PORTAL.reduce,
    linked=PORTAL.linked,
    note=note,
    sections=PORTAL.sections,
)
"""The snapshot: the portal's shell and its document, the classic Swagger UI and the backend
document it names, the program page the CDN refuses, and the two ESR query URLs. Neither
document states a copyright line, a licence or terms, so the attribution is empty, and the
frame stops a run on a page that comes to state one."""


if __name__ == "__main__":
    raise SystemExit(run(SNAPSHOT))
