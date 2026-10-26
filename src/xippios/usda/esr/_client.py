"""The configured ``xippios.core`` client for USDA FAS Export Sales Reporting.

One ``AsyncClient`` for the whole package, shared by the tasks, the sync facades and the
MCP server, on api.data.gov's gateway at ``BASE_URL`` with the key in the ``X-Api-Key``
header and ``Accept: application/json``. It keeps a pace of its own, ``RATE_LIMIT``,
since the snapshot documents none; core's ``QuotaPolicy``, ``policy``, keeps
api.data.gov's hourly quota from every answer and never fires a request into a spent
one, waiting within ``RetryPolicy.backoff_max`` or refusing without sending (ADR-0010,
ADR-0015); and ``classify`` maps the gateway's ``API_KEY_*`` answers to ``AuthError``,
its 429 to ``RateLimitError``, its ``NOT_FOUND`` to ``NotFoundError``, ESR's empty 404 on
an exports path to ``errors.NoDataForYear`` and ESR's own 400 for a path value that is not
an integer to ``InvalidRequestError``.

The gateway pieces here (``HeaderKeyAuth("X-Api-Key", ...)``, the ``QuotaPolicy`` on
``x-ratelimit-*``, the ``API_KEY_*``, ``OVER_RATE_LIMIT`` and ``NOT_FOUND`` mappings
with host-free messages) are the third copy of sdk-usda-psd's adopted shape, accepted
until core 0.3.0 provides a shared api.data.gov gateway module (family review C14,
conventions §15 item 4), which these lines are the candidate for.
"""

import re

import httpx
from xippios.core import (
    AsyncClient,
    AuthError,
    ClientConfig,
    HeaderKeyAuth,
    InvalidRequestError,
    NotFoundError,
    QuotaPolicy,
    RateLimit,
    RateLimitError,
    XippiosError,
)
from xippios.core.errors import parse_retry_after

from xippios.usda.esr._version import __version__

SOURCE = "usda-esr"
BASE_URL = "https://api.fas.usda.gov"
"""The gateway's host root; every ESR path keeps its ``/api/esr/`` prefix, as the snapshot's
``paths`` name it (the portal document's ``host`` is ``api.fas.usda.gov``, no ``basePath``)."""
API_KEY_ENV = "DATA_GOV_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
# A self-imposed pace: upstream documents no limit (ADR-0010 decision 1).
RATE_LIMIT = RateLimit(per_minute=60, burst=1)
"""One request per second, no burst: a pace of our own, since the snapshot documents none.

At this pace the gateway's 1,000 requests per hour, shared with every other package using
the same key, last about 17 minutes; past that the quota policy takes over.
"""

DATA_PATH = re.compile(
    r"/api/esr/exports/commodityCode/[^/]+/(?:allCountries|countryCode/[^/]+)/marketYear/[^/]+"
)
"""The two exports forms: one destination country, and ``allCountries``, by market year."""

policy = QuotaPolicy(
    window=3600.0,
    source=SOURCE,
    limit_header="x-ratelimit-limit",
    remaining_header="x-ratelimit-remaining",
)
"""api.data.gov's quota for the key, kept by core from every answer from the wire.

``x-ratelimit-limit: 1000`` and ``x-ratelimit-remaining`` count requests per rolling hour
per key, not a pace: they are on every keyed ESR answer (the orchestrator's probes and the
recordings of 2026-10-25), and they are the quota api.data.gov documents
(https://api.data.gov/docs/developer-manual/), shared by every package and process using
the same ``DATA_GOV_API_KEY`` (ADR-0009). The gateway sends no reset header: a spent quota
comes back after a 429's ``Retry-After``, else after ``window``, one hour, from the
developer manual: "The block will automatically be lifted by waiting an hour".
``policy.snapshot()`` reads the quota as the last answer reported it.
"""

_URL = re.compile(r"https?://[^/\s]+")


def _gateway_error(response: httpx.Response) -> tuple[str | None, str]:
    """api.data.gov's ``{"error": {"code": ..., "message": ...}}``, or ``(None, "")``.

    The message comes back host-free (conventions §5): the gateway ends its messages with
    its URL (``"Get one at https://api.fas.usda.gov:443"``), written ``<host>`` here.
    """
    try:
        payload = response.json()
    except ValueError:
        return None, ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return None, ""
    message = error.get("message")
    return error["code"], _URL.sub("<host>", message) if isinstance(message, str) else ""


def _esr_message(response: httpx.Response) -> str | None:
    """ESR's own ``{"message": ...}`` body, host-free, or ``None`` when the body is another."""
    try:
        payload = response.json()
    except ValueError:
        return None
    message = payload.get("message") if isinstance(payload, dict) else None
    return _URL.sub("<host>", message) if isinstance(message, str) else None


def _over_rate_limit(response: httpx.Response) -> RateLimitError:
    """The gateway's 429, ``retry_after`` as long as the policy keeps the quota spent.

    Core's ``observe`` has read this answer before ``classify`` runs, so
    ``policy.snapshot()`` describes it; called on its own, without the client, there may be
    no snapshot, and the message says how long instead.
    """
    code, message = _gateway_error(response)
    upstream = ": ".join(part for part in (code, message) if part)
    named = parse_retry_after(response.headers.get("Retry-After"))
    wait = policy.window if named is None else min(named, policy.window)
    snapshot = policy.snapshot()
    allowance = (
        f"{snapshot.limit} requests per rolling hour per key"
        if snapshot is not None and snapshot.limit is not None
        else "an hourly quota per key"
    )
    state = (
        f"Quota: {snapshot.describe()}."
        if snapshot is not None
        else f"The quota is expected back in {wait:.0f} s."
    )
    bound = config.retry.backoff_max
    retried = (
        f" Nothing was retried: that is longer than a call waits ({bound:g} s)."
        if wait > bound
        else ""
    )
    return RateLimitError(
        f"api.data.gov rate limit reached for the key in {API_KEY_ENV} "
        f"(HTTP 429{' ' + upstream if upstream else ''}). The gateway allows {allowance}, "
        f"shared by every package using that key. {state}{retried}",
        retry_after=wait,
        source=SOURCE,
    )


def classify(response: httpx.Response) -> XippiosError | None:
    """The gateway's documented and ESR's recorded error shapes, mapped once (ADR-0008).

    - 401/403 with an api.data.gov ``error.code`` starting ``API_KEY_`` (developer manual:
      ``API_KEY_MISSING``, ``API_KEY_INVALID``, ``API_KEY_DISABLED``,
      ``API_KEY_UNAUTHORIZED``, ``API_KEY_UNVERIFIED``) is ``AuthError`` naming the code
      and the variable, never the key. Recorded: ``API_KEY_INVALID``
      (``ESRData_GetCommodities/invalid_key.json``).
    - 429 (``OVER_RATE_LIMIT``) is ``RateLimitError`` with ``retry_after`` from
      ``Retry-After``, else the policy's ``window`` (3600 s): as long as ``policy`` keeps
      the quota spent. Not recorded for ESR (spending the shared quota to record it was
      not worth it); the tests build it in the shape api.data.gov documents and
      sdk-usda-psd recorded on 2026-10-23. Core asks ``classify`` before it retries, so a
      wait beyond ``RetryPolicy.backoff_max`` is raised after one request, and the message
      describes ``policy.snapshot()``.
    - 404 with ``error.code`` ``NOT_FOUND`` is the gateway's: no such path. Not recorded;
      the tests build api.data.gov's documented body.
    - 404 with an empty ``text/plain`` body on an exports path (``DATA_PATH``) is ESR's own
      answer for a market year it holds no data for, recorded for 1900
      (``ESRData_GetCountryData/year_1900.json``). It is ``errors.NoDataForYear``, a
      ``NotFoundError``; an empty 404 anywhere else is a plain ``NotFoundError``.
    - 400 with ESR's ``{"message": "The request is invalid."}`` is ``InvalidRequestError``:
      a path value that is not an integer (``exports/commodityCode/abc/...``, recorded as
      ``ESRData_GetCountryData/not_an_integer.json``). The package never sends one, since
      its parameters are ``int``.

    An unknown commodity or country code answers HTTP 200 with ``[]``
    (``unknown_commodity``, ``unknown_country``), and so do a market year in the future
    (``year_2099``) and valid codes without exports (rye, market year 2024,
    ``ESRData_GetAllCountriesData/rye_2024.json``): empty means empty, not an error; the
    package refuses unknown codes and future years before the call (``params``).
    Everything else falls through to core's status mapping. Messages name the path, never
    the host.
    """
    status = response.status_code
    path = response.request.url.path
    if status in (401, 403):
        code, message = _gateway_error(response)
        if code is not None and code.startswith("API_KEY_"):
            return AuthError(
                f"api.data.gov refused the key in {API_KEY_ENV} (HTTP {status} {code}: "
                f"{message}). Check that the variable holds a valid, active api.data.gov key.",
                status=status,
                source=SOURCE,
            )
    if status == 429:
        return _over_rate_limit(response)
    if status == 404:
        code, message = _gateway_error(response)
        if code == "NOT_FOUND":
            return NotFoundError(
                f"api.data.gov has no route for {path} (HTTP 404 NOT_FOUND: {message})",
                source=SOURCE,
            )
        if not response.content.strip():
            content_type = response.headers.get("content-type", "").lower()
            if content_type.startswith("text/plain") and DATA_PATH.fullmatch(path):
                # errors imports SOURCE from this module, so it is imported here, not above
                from xippios.usda.esr.errors import NoDataForYear

                return NoDataForYear(path)
            return NotFoundError(
                f"ESR has no data for {path} (HTTP 404 with an empty body)", source=SOURCE
            )
    if status == 400:
        refusal = _esr_message(response)
        if refusal is not None:
            return InvalidRequestError(
                f"ESR refused {path} (HTTP 400: {refusal}). Every path value of an ESR "
                "export query is an integer: commodity code, country code and market year.",
                source=SOURCE,
            )
    return None


config = policy.install(
    ClientConfig(
        source=SOURCE,
        version=__version__,
        base_url=BASE_URL,
        rate_limit=RATE_LIMIT,
        headers={"Accept": "application/json"},
        classify=classify,
    )
)
# The key is read from the environment on the first request, never at import.
auth = HeaderKeyAuth("X-Api-Key", API_KEY_ENV, source=SOURCE)
client = AsyncClient(config, auth=auth)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "DATA_PATH",
    "RATE_LIMIT",
    "SOURCE",
    "auth",
    "classify",
    "client",
    "config",
    "policy",
]
