# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-10-25T00:00:00Z"
# ///
"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

The FAS Open Data Services portal (https://apps.fas.usda.gov/opendatawebV2/) is an
Angular app whose page holds no documentation text; its Swagger window loads the
Swagger 2.0 document ``assets/swagger/swagger.json``. On 2026-10-23 the session that set
up sdk-usda-psd's snapshot fetched the portal page and its bundle ``main.<hash>.js`` into
a session-local scratch directory and found that URL in the bundle's Swagger UI
configuration; those copies have since been deleted, and this script reuses the URL.
It never downloads the bundle, because the bundle embeds the portal's own api.data.gov
signup-widget key; FETCHED.md records only the bundle's file name. The API also serves
its own Swashbuckle document, whose URL the script reads from the classic Swagger UI
page. Both documents describe ESR, GATS and PSD; this package wraps ESR only. It writes:

- ``openapi/portal-document.json``: the ESR part of the portal's document;
- ``openapi/backend-docs-v1.json``: the ESR part of the API's own document;
- ``FETCHED.md``: regenerated entirely, one row per file and per page recorded without
  a file (client-rendered shells, a page the CDN refuses to headless clients, and the
  ESR query URLs, which answer 404).

The ESR part of a document is every top-level field verbatim and in upstream order, with
``paths`` reduced to the keys starting with ``/api/esr/`` and ``definitions`` reduced to
those the kept paths reference, written with ``json.dumps(indent=2, ensure_ascii=False)``.

Everything is fetched before anything is written, one request at a time, each URL retried
at most once. Files under ``openapi/`` that the run does not produce are removed;
``FETCHED.md`` is rewritten; nothing else under ``docs/upstream/`` is touched.
``Fetched`` is the UTC time of the run in ISO 8601 with an explicit ``Z``, taken once at
the start and the same in every row (conventions §3). The same upstream gives the same
files under ``openapi/``, and ``FETCHED.md`` differs between runs only in ``Fetched``:
the refused page's body carries a per-request reference, so its row records neither size
nor sha256. No key is needed or read. Run from the repository root::

    uv run scripts/refresh_upstream.py
"""

import argparse
import hashlib
import http.client
import json
import re
import textwrap
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import IO, Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs/upstream"
COMMAND = "uv run scripts/refresh_upstream.py"

PORTAL_URL = "https://apps.fas.usda.gov/opendatawebV2/"
PORTAL_SWAGGER_URL = "https://apps.fas.usda.gov/opendatawebV2/assets/swagger/swagger.json"
"""Named by the Swagger UI configuration in the portal's ``main.<hash>.js`` bundle."""
PORTAL_SWAGGER_FOUND_ON = "2026-10-23"
"""The day sdk-usda-psd's session found ``PORTAL_SWAGGER_URL`` in a scratch copy of the bundle."""
CLASSIC_UI_URL = "https://apps.fas.usda.gov/opendata/swagger/ui/index"
ESR_PROGRAM_URL = "https://www.fas.usda.gov/programs/export-sales-reporting-program"
"""The Export Sales Reporting program page, this package's ``Upstream`` URL."""
ESRQUERY_URLS = (
    "https://apps.fas.usda.gov/esrquery/",
    "https://apps.fas.usda.gov/esrquery/esrq.aspx",
)
"""The ESR query application's URLs; both answered 404 when this snapshot was set up."""
SET_UP_ON = "2026-10-25"
"""The day this package's snapshot was set up."""
API_HOST = "apps.fas.usda.gov"
"""The host the backend document URL read from the classic UI page must have."""

PORTAL_FILE = "openapi/portal-document.json"
BACKEND_FILE = "openapi/backend-docs-v1.json"
"""No ``swagger`` in snapshot paths: detect-secrets' ``is_swagger_file`` would skip them."""
SUBDIRS = ("openapi",)
KEEP_PREFIX = "/api/esr/"
SHELL_NOTE = "client-rendered shell, no documentation text"
REFUSED_NOTE = "403 Access Denied at the CDN edge"
MAX_SHELL_BYTES = 16_384
"""A page recorded as a shell must stay this small; a larger one needs a look by hand."""
ATTRIBUTION_KEYS = ("license", "termsOfService", "contact")
"""Swagger 2.0 ``info`` fields that would state terms or an owner."""

USER_AGENT = "xippios-usda-esr refresh_upstream (+https://github.com/xippios)"
TIMEOUT = 60.0
PAUSE = 2.0
"""Seconds before every request; requests never run in parallel."""
RETRY_PAUSE = 10.0
"""Seconds before the one retry after a network error or a 5xx."""

_BUNDLE = re.compile(r"""<script\s+src=["'](main\.[0-9a-f]+\.js)["']""")
_ROOT_URL = re.compile(r"rootUrl:\s*'([^']+)'")
_DISCOVERY = re.compile(r"discoveryPaths:\s*arrayFrom\('([^']*)'\)")
_PREFIX = re.compile(r"/api/[^/]+/")
_COPYRIGHT = re.compile(rb"\xc2\xa9|\\u00a9|&copy;|&#169;|copyright", re.IGNORECASE)
"""A copyright sign as UTF-8, as a JSON or HTML escape, or the word, in a document's text."""


@dataclass(frozen=True)
class Response:
    """One GET as served: status, body and validators, and any redirects on the way."""

    url: str
    status: int
    body: bytes
    content_type: str | None
    etag: str | None
    last_modified: str | None
    redirects: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class Row:
    """One row of the ``FETCHED.md`` table, with the snapshot file it produced, if any."""

    response: Response
    note: str
    path: str | None = None
    content: bytes | None = None
    stable: bool = True
    """False for a body that differs on every request: no size or sha256 is recorded."""


@dataclass(frozen=True)
class EsrPart:
    """The ESR part of one Swagger document and what was left out of it."""

    part: dict[str, Any]
    kept: int
    dropped: dict[str, int]
    definitions_kept: int
    definitions_total: int


class _RetryableError(Exception):
    """A network error or a 5xx: worth one more attempt."""


class _RecordRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects as urllib does, remembering each status and target."""

    def __init__(self) -> None:
        super().__init__()
        self.hops: list[tuple[int, str]] = []

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Record the hop, then let urllib build the follow-up request."""
        self.hops.append((code, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


def _unexpected(url: str, expect: int, status: int, reason: str) -> SystemExit:
    return SystemExit(
        f"GET {url}: expected HTTP {expect}, got {status} {reason}.\nLook at the URL by hand "
        "and update scripts/refresh_upstream.py. Nothing was written."
    )


def _get(url: str, expect: int) -> Response:
    redirects = _RecordRedirects()
    opener = urllib.request.build_opener(redirects)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            body: bytes = response.read()
            status: int = response.status
            reason: str = response.reason
            headers = response.headers
    except urllib.error.HTTPError as error:
        if error.code >= 500:
            raise _RetryableError(f"HTTP {error.code} {error.reason}") from None
        if error.code != expect:
            raise _unexpected(url, expect, error.code, str(error.reason)) from None
        body, status, headers = error.read(), error.code, error.headers
        reason = str(error.reason)
    except (http.client.HTTPException, OSError) as error:  # URLError is an OSError
        raise _RetryableError(str(error)) from None
    if status != expect:
        raise _unexpected(url, expect, status, reason)
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding != "identity":
        raise SystemExit(f"GET {url}: unexpected Content-Encoding {encoding!r}")
    return Response(
        url,
        status,
        body,
        headers.get_content_type() if headers.get("Content-Type") else None,
        headers.get("ETag"),
        headers.get("Last-Modified"),
        tuple(redirects.hops),
    )


def fetch(url: str, expect: int = 200) -> Response:
    """GET ``url`` after a polite pause; retry once on a network error or a 5xx."""
    time.sleep(PAUSE)
    try:
        response = _get(url, expect)
    except _RetryableError as error:
        _log(f"  {url}: {error}; retrying once in {RETRY_PAUSE:.0f} s")
        time.sleep(RETRY_PAUSE)
        try:
            response = _get(url, expect)
        except _RetryableError as error:
            raise SystemExit(f"GET {url}: {error} (after one retry)") from None
    digest = hashlib.sha256(response.body).hexdigest()
    hops = "".join(f", {code} to {target}" for code, target in response.redirects)
    _log(
        f"  {url}: HTTP {response.status}{hops}, {len(response.body)} bytes "
        f"({response.content_type or 'no Content-Type'}), sha256 {digest}, "
        f"Last-Modified {response.last_modified or '-'}, ETag {response.etag or '-'}"
    )
    return response


def _page_changed(url: str, what: str) -> SystemExit:
    return SystemExit(
        f"{url} changed: {what}.\nLook at the page by hand and update "
        "scripts/refresh_upstream.py; it may now need a file of its own. Nothing was written."
    )


def _text(response: Response) -> str:
    try:
        return response.body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _page_changed(response.url, f"body is not UTF-8 ({error})") from None


def _redirect_note(response: Response) -> str:
    return "".join(f"redirected ({code}) to {target}; " for code, target in response.redirects)


def shell(url: str, marker: str) -> tuple[Response, str]:
    """Fetch a page that must still be a small client-rendered shell carrying ``marker``."""
    response = fetch(url)
    text = _text(response)
    if marker not in text:
        raise _page_changed(url, f"the client-rendering mount point {marker!r} is gone")
    if len(response.body) > MAX_SHELL_BYTES:
        raise _page_changed(url, f"{len(response.body)} bytes, more than a shell's")
    return response, text


def portal_shell() -> tuple[Row, str]:
    """Record the portal page and read the name of the bundle it loads."""
    response, text = shell(PORTAL_URL, "<app-root>")
    bundles = sorted(set(_BUNDLE.findall(text)))
    if len(bundles) != 1:
        raise _page_changed(PORTAL_URL, f"expected one main.<hash>.js, found {bundles}")
    note = f"{_redirect_note(response)}{SHELL_NOTE}; loads the bundle `{bundles[0]}`"
    return Row(response, note), bundles[0]


def classic_ui() -> tuple[Row, str]:
    """Record the classic Swagger UI page and read the backend document's URL from it."""
    response, text = shell(CLASSIC_UI_URL, 'id="swagger-ui-container"')
    roots, discovery = _ROOT_URL.findall(text), _DISCOVERY.findall(text)
    if len(roots) != 1 or len(discovery) != 1:
        raise _page_changed(CLASSIC_UI_URL, f"rootUrl {roots}, discoveryPaths {discovery}")
    paths = [path for path in discovery[0].split("|") if path]
    if len(paths) != 1:
        raise _page_changed(CLASSIC_UI_URL, f"expected one discovery path, found {paths}")
    url = f"{roots[0].rstrip('/')}/{paths[0].lstrip('/')}"
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != API_HOST:
        raise _page_changed(CLASSIC_UI_URL, f"the document URL {url!r} left https://{API_HOST}")
    note = f"{_redirect_note(response)}{SHELL_NOTE}; Swagger UI that loads `{url}`"
    return Row(response, note), url


def esr_program() -> Row:
    """Record the ESR program page, which the CDN refuses to headless clients."""
    response = fetch(ESR_PROGRAM_URL, expect=403)
    if b"Access Denied" not in response.body:
        raise _page_changed(ESR_PROGRAM_URL, "HTTP 403 without 'Access Denied' in the body")
    note = (
        f"{_redirect_note(response)}the Export Sales Reporting program page; {REFUSED_NOTE}; "
        "the body is not stable (it carries a per-request reference), so neither its size "
        "nor its sha256 is recorded"
    )
    return Row(response, note, stable=False)


def esrquery(url: str) -> Row:
    """Record an ESR query URL, which answers 404 where a client-rendered shell was expected."""
    response = fetch(url, expect=404)
    body = f"a {response.content_type} body" if response.body else "an empty body"
    note = (
        f"{_redirect_note(response)}404 Not Found with {body}; when this snapshot was set "
        f"up on {SET_UP_ON} this URL was expected to serve the ESR query application's "
        "client-rendered shell, and it does not"
    )
    return Row(response, note)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate keys {duplicates}")
    return dict(pairs)


def _document(response: Response) -> dict[str, Any]:
    try:
        document = json.loads(response.body, object_pairs_hook=_no_duplicates)
    except ValueError as error:
        raise SystemExit(f"GET {response.url}: not usable JSON ({error})") from None
    if not isinstance(document, dict) or document.get("swagger") != "2.0":
        raise SystemExit(f"GET {response.url}: expected a Swagger 2.0 document")
    if not isinstance(document.get("paths"), dict):
        raise SystemExit(f"GET {response.url}: no paths object")
    if not isinstance(document.get("definitions", {}), dict):
        raise SystemExit(f"GET {response.url}: definitions is not an object")
    if not isinstance(document.get("info"), dict):
        raise SystemExit(f"GET {response.url}: no info object")
    stated = [f"info.{key}" for key in ATTRIBUTION_KEYS if key in document["info"]]
    stated += [repr(match.decode()) for match in _COPYRIGHT.findall(response.body)]
    if stated:
        raise SystemExit(
            f"GET {response.url}: the document now states {', '.join(stated)}. FETCHED.md "
            "says that neither document states a copyright line; look at the document by "
            "hand and update the attribution in scripts/refresh_upstream.py. Nothing was "
            "written."
        )
    return document


def _refs(value: Any) -> set[str]:
    """Every definition name a ``#/definitions/...`` reference in ``value`` points at."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith("#/definitions/"):
                name = unquote(item.removeprefix("#/definitions/"))
                found.add(name.replace("~1", "/").replace("~0", "~"))
            else:
                found |= _refs(item)
    elif isinstance(value, list):
        for item in value:
            found |= _refs(item)
    return found


def esr_part(response: Response) -> EsrPart:
    """The ESR part of a Swagger document: kept paths and the definitions they reference."""
    document = _document(response)
    paths: dict[str, Any] = document["paths"]
    definitions: dict[str, Any] = document.get("definitions", {})
    kept = {key: value for key, value in paths.items() if key.startswith(KEEP_PREFIX)}
    if not kept:
        raise SystemExit(f"GET {response.url}: no path starts with {KEEP_PREFIX}")
    dropped: Counter[str] = Counter()
    for key in paths:
        if not key.startswith(KEEP_PREFIX):
            match = _PREFIX.match(key)
            dropped[match.group(0) if match else key] += 1

    wanted: set[str] = set()
    pending = _refs(kept)
    while pending:
        name = pending.pop()
        if name in wanted:
            continue
        if name not in definitions:
            raise SystemExit(f"GET {response.url}: #/definitions/{name} is referenced, absent")
        wanted.add(name)
        pending |= _refs(definitions[name])

    part: dict[str, Any] = {}
    for key, value in document.items():
        if key == "paths":
            part[key] = kept
        elif key == "definitions":
            part[key] = {name: item for name, item in value.items() if name in wanted}
        else:
            part[key] = value
    full = json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")
    if full != response.body.replace(b"\r\n", b"\n"):
        raise SystemExit(
            f"GET {response.url}: re-serialised with json.dumps(indent=2, ensure_ascii=False), "
            "the document no longer reproduces the fetched text up to line endings, so its "
            "ESR part would not be an excerpt of the upstream text.\nLook at the document by "
            "hand and update scripts/refresh_upstream.py. Nothing was written."
        )
    return EsrPart(
        part=part,
        kept=len(kept),
        dropped=dict(dropped),
        definitions_kept=len(wanted),
        definitions_total=len(definitions),
    )


def document_row(path: str, response: Response) -> tuple[Row, EsrPart]:
    """Fetch-side work for one document: its ESR part, the file content and the row."""
    esr = esr_part(response)
    content = (json.dumps(esr.part, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    dropped = ", ".join(f"{count} `{prefix}`" for prefix, count in esr.dropped.items())
    note = (
        f"{_redirect_note(response)}ESR part; Bytes and sha256 are the full document's. "
        f"Kept {esr.kept} `{KEEP_PREFIX}` paths; dropped {dropped or 'none'} (out of scope "
        f"here, own packages); kept {esr.definitions_kept} of {esr.definitions_total} "
        "definitions"
    )
    _log(f"  {path}: {len(content)} bytes written from {len(response.body)} fetched")
    return Row(response, note, path, content), esr


def _iso_http_date(value: str | None) -> str:
    if value is None:
        return "-"
    return parsedate_to_datetime(value).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cell(value: str) -> str:
    return value.replace("|", r"\|")


def _fields(names: list[str], conjunction: str = "and") -> str:
    quoted = [f"`{name}`" for name in names]
    if len(quoted) < 2:
        return "".join(quoted) or "nothing"
    return f"{', '.join(quoted[:-1])} {conjunction} {quoted[-1]}"


def _paragraph(*sentences: str) -> list[str]:
    text = " ".join(sentences)
    wrapped = textwrap.fill(text, width=88, break_long_words=False, break_on_hyphens=False)
    return [*wrapped.splitlines(), ""]


def _comparison(portal: EsrPart, backend: EsrPart) -> str:
    """How the two ESR parts compare, top-level field by top-level field."""
    keys = list(dict.fromkeys([*portal.part, *backend.part]))
    both = [key for key in keys if key in portal.part and key in backend.part]
    differ = [key for key in both if portal.part[key] != backend.part[key]]
    agree = [key for key in both if key not in differ]
    clauses = [f"differ in {_fields(differ)}"] if differ else []
    for name, mine, other in (("portal", portal, backend), ("backend", backend, portal)):
        only = [key for key in keys if key in mine.part and key not in other.part]
        if only:
            clauses.append(f"only the {name} document has {_fields(only)}")
    clauses.append(f"they agree in {_fields(agree)}")
    return "; ".join(clauses)


def _info_fields(portal: EsrPart, backend: EsrPart) -> str:
    """Which fields the two documents' ``info`` objects carry."""
    mine, other = list(portal.part["info"]), list(backend.part["info"])
    if mine == other:
        return f"the `info` object of each carries only {_fields(mine)}"
    return (
        f"the portal document's `info` object carries only {_fields(mine)}, the backend "
        f"document's only {_fields(other)}"
    )


def render_fetched(
    rows: list[Row],
    portal: EsrPart,
    backend: EsrPart,
    bundle: str,
    backend_url: str,
    fetched: str,
) -> str:
    """The whole of ``FETCHED.md``."""
    lines = [
        "# Upstream documentation snapshot \N{EM DASH} USDA FAS Export Sales Reporting",
        "",
        *_paragraph(
            "Source of truth for every endpoint wrapper (ADR-0003). The files in this",
            "directory are written by `scripts/refresh_upstream.py` (`/refresh-upstream`)",
            "from the documents in the table below and refreshed deliberately by PR, so that",
            "changes show up as diffs. This file is generated by the same script. Nothing",
            "here was edited by hand.",
        ),
        "## Attribution",
        "",
        *_paragraph(
            f"Neither document states a copyright line: {_info_fields(portal, backend)},",
            f"with no {_fields(list(ATTRIBUTION_KEYS), 'or')}, and neither document's text",
            "contains a copyright sign or the word copyright. The script stops if either",
            "comes to state one. The documents' text is reproduced here as this package's",
            "reference (ADR-0003); a vendor's objection is met by replacing it with a",
            "summary that keeps the names and semantics the wrappers rely on.",
        ),
        "## How this is captured",
        "",
        *_paragraph(
            f"The FAS Open Data Services portal, {PORTAL_URL}, documents three APIs of",
            "USDA's Foreign Agricultural Service: ESR, GATS and PSD. It is an Angular app",
            "whose page is a shell without documentation text. Its Swagger window loads the",
            f"Swagger 2.0 document {PORTAL_SWAGGER_URL}. On {PORTAL_SWAGGER_FOUND_ON} the",
            "session that set up sdk-usda-psd's snapshot fetched the portal page and its",
            "JavaScript bundle into a session-local scratch directory and found that URL in",
            "the bundle's Swagger UI configuration; those copies have since been deleted,",
            "and this script reuses the URL. The script never downloads the bundle, since",
            "it embeds the portal's own api.data.gov signup-widget key, and this file",
            f"records only its file name: as of this run the portal page loads `{bundle}`.",
        ),
        *_paragraph(
            f"The API also serves its own Swashbuckle document, {backend_url}, which the",
            f"classic Swagger UI at {CLASSIC_UI_URL} loads; the script reads that URL from",
            "the UI page's `rootUrl` and `discoveryPaths`. Both documents are kept because",
            "they are two upstream statements of the same API that need not agree on how it",
            f"is reached. As fetched, their ESR parts {_comparison(portal, backend)}.",
        ),
        *_paragraph(
            "Both documents cover ESR, GATS and PSD, and GATS and PSD get their own packages",
            "in this family, so each file here holds the ESR part only: every top-level field",
            "verbatim and in upstream order, `paths` reduced to the keys starting with",
            f"`{KEEP_PREFIX}` and `definitions` reduced to those the kept paths reference,",
            "directly or through other definitions; each document's row counts the paths",
            "kept and dropped, per prefix. The script writes the part with",
            "`json.dumps(indent=2, ensure_ascii=False)` in upstream key order, with LF line",
            "endings and a final newline, and stops unless the full document re-serialised",
            "the same way reproduces the fetched text up to line endings, so each file is the",
            "upstream text with the other APIs cut out. Bytes and sha256 in a document's row",
            "are those of the full document as fetched, so a change anywhere in it shows",
            "here.",
        ),
        *_paragraph(
            "Pages that are client-rendered shells, that refuse headless clients or that",
            "answer 404 get no file, only a row with their HTTP status and the size and",
            f"sha256 of the body. The ESR query URLs {ESRQUERY_URLS[0]} and",
            f"{ESRQUERY_URLS[1]} were expected, when this snapshot was set up on {SET_UP_ON},",
            "to serve the ESR query application's client-rendered shell; both answer 404,",
            "and their rows record what is answered. The program page's 403 body carries a",
            "per-request reference number and so is not stable; its row records neither",
            "size nor sha256. The same upstream thus gives the same files under `openapi/`,",
            "and this file differs between runs only in `Fetched`.",
        ),
        *_paragraph(
            "`Fetched` is the UTC time of the run in ISO 8601 with an explicit `Z`, taken",
            "once at its start and the same in every row (conventions §3); Last-Modified is",
            "the HTTP header in UTC, ETag as sent. Requests go one at a time, identified as",
            f"`{USER_AGENT}`; no API key is sent or read.",
        ),
        "## Files and pages",
        "",
        "| File | URL | Fetched | HTTP | Bytes | sha256 | ETag | Last-Modified | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        response = row.response
        cells = [
            row.path or "(no file)",
            response.url,
            fetched,
            str(response.status),
            str(len(response.body)) if row.stable else "-",
            hashlib.sha256(response.body).hexdigest() if row.stable else "-",
            response.etag or "-",
            _iso_http_date(response.last_modified),
            row.note,
        ]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    lines += ["", f"Regenerate: `{COMMAND}`"]
    return "\n".join(lines) + "\n"


def write_snapshot(out: Path, rows: list[Row], fetched_md: str) -> None:
    """Write the files and ``FETCHED.md`` with LF line endings; prune stale ``openapi/`` files.

    Only files under ``openapi/`` that this run does not produce are removed.
    """
    if out.exists() and any(out.iterdir()) and not (out / "FETCHED.md").is_file():
        raise SystemExit(f"{out} is neither empty nor a snapshot (no FETCHED.md); not writing")
    files = {row.path: row.content for row in rows if row.path and row.content is not None}
    for subdir in SUBDIRS:
        directory = out / subdir
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(directory.iterdir()):
            if path.is_file() and f"{subdir}/{path.name}" not in files:
                path.unlink()
                _log(f"  removed {subdir}/{path.name}: no longer produced")
    for name, content in files.items():
        (out / name).write_bytes(content)
    (out / "FETCHED.md").write_bytes(fetched_md.encode("utf-8"))


def main() -> None:
    """Fetch every document and page, then write the snapshot."""
    parser = argparse.ArgumentParser(description="Refresh docs/upstream/ from USDA FAS.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot directory")
    out: Path = parser.parse_args().out
    fetched = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    _log(f"Run {fetched}. Portal: {PORTAL_URL}")
    portal_page, bundle = portal_shell()
    portal_row, portal = document_row(PORTAL_FILE, fetch(PORTAL_SWAGGER_URL))
    _log(f"Classic Swagger UI: {CLASSIC_UI_URL}")
    ui_page, backend_url = classic_ui()
    backend_row, backend = document_row(BACKEND_FILE, fetch(backend_url))
    _log("Pages recorded without a file")
    pages = [esr_program(), *(esrquery(url) for url in ESRQUERY_URLS)]

    rows = [portal_row, backend_row, portal_page, ui_page, *pages]
    fetched_md = render_fetched(rows, portal, backend, bundle, backend_url, fetched)
    write_snapshot(out, rows, fetched_md)
    written = sum(1 for row in rows if row.path)
    _log(f"Wrote {written} files and FETCHED.md under {out}")


if __name__ == "__main__":
    main()
