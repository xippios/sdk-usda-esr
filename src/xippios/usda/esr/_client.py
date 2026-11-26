"""The configured ``xippios.core`` client for USDA FAS Export Sales Reporting.

One ``AsyncClient`` for the whole package, shared by the tasks, the sync facades and the
MCP server, on api.data.gov's gateway at ``BASE_URL`` with ``Accept: application/json``.
It keeps a pace of its own, ``RATE_LIMIT``, since the snapshot documents none, and keeps
upstream's answers in core's response cache, ``MemoryCache`` at core's default lifetime of
300 s for every path, since the package only reads public data (conventions §6; sdk-core
ADR-0061, decision 11): the release list that ``get_exports`` and ``get_weekly_series`` read
for a market year from the current calendar year on is one request per lifetime, and a
continuation of a cut ``get_exports`` answer is the cache's. The gateway is the shared
package's, ``xippios.usda.fas``'s ``Gateway``
(sdk-core ADR-0032, decision 5; sdk-core ADR-0065, decision 1): ``gateway.auth`` sends the key
from ``DATA_GOV_API_KEY`` in the ``X-Api-Key`` header; ``Gateway.policy``, the one
``QuotaPolicy`` per process for that key, keeps api.data.gov's hourly quota from every answer
from the wire and never fires a request into a spent one, refusing it without sending, a
refusal that speaks for ``api.data.gov`` (sdk-core ADR-0033, sdk-core ADR-0037); and
``gateway.classify`` maps the gateway's ``API_KEY_*`` answers to ``AuthError``, its 429 to
``RateLimitError`` (its ``Retry-After`` read by the gateway), its ``NOT_FOUND`` to
``NotFoundError`` and, since ``Gateway(SOURCE, data_path=DATA_PATH)`` names the exports
paths, FAS's empty 404 there to the shared package's ``NoDataForYear``
(https://github.com/xippios/sdk-core/issues/106). ``classify`` asks the gateway first and
then maps ESR's own answers: an empty 404 anywhere else to a plain ``NotFoundError`` and its
400 for a path value that is not an integer to ``InvalidRequestError``.
"""

import re

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    EnvVar,
    InvalidRequestError,
    MemoryCache,
    NotFoundError,
    RateLimit,
    XippiosError,
)
from xippios.core.errors import request_description
from xippios.usda.fas import API_KEY_ENV, Gateway

from xippios.usda.esr._version import __version__

SOURCE = "usda-esr"
BASE_URL = "https://api.fas.usda.gov"
"""The gateway's host root; every ESR path keeps its ``/api/esr/`` prefix, as the snapshot's
``paths`` name it (the portal document's ``host`` is ``api.fas.usda.gov``, no ``basePath``)."""
ENV_VARS: tuple[EnvVar, ...] = (EnvVar(API_KEY_ENV, secret=True, required=True),)
"""The variables the package reads, for a host (conventions §7; sdk-core ADR-0026, amendment
2026-11-18, point c): the gateway's key alone. An ``EnvVar`` names a variable and reads none;
a variable the source reads beside these joins the list."""
# A self-imposed pace: upstream documents no per-second or per-minute limit (sdk-core ADR-0033
# decision 1).
RATE_LIMIT = RateLimit(per_minute=60, burst=1)
"""One request per second, no burst: a pace of our own, since the snapshot documents none.

At this pace the gateway's 1,000 requests per hour, shared with every other package using
the same key, last about 17 minutes; past that the quota policy takes over.
"""

DATA_PATH = re.compile(
    r"/api/esr/exports/commodityCode/[^/]+/(?:allCountries|countryCode/[^/]+)/marketYear/[^/]+"
)
"""The two exports forms: one destination country, and ``allCountries``, by market year."""

# api.data.gov's key, its documented answers and its hourly quota, kept by one policy per
# process that every source behind the gateway shares (sdk-core ADR-0032).
gateway = Gateway(SOURCE, data_path=DATA_PATH)
"""api.data.gov for this package: ``auth``, ``classify`` and ``install``.

``classify`` maps FAS's empty ``text/plain`` 404 on ``DATA_PATH`` to the shared package's
``NoDataForYear``, in this package's name."""

_URL = re.compile(r"https?://[^/\s]+")


def _esr_message(response: httpx.Response) -> str | None:
    """ESR's own ``{"message": ...}`` body, host-free, or ``None`` when the body is another."""
    try:
        payload = response.json()
    except ValueError:
        return None
    message = payload.get("message") if isinstance(payload, dict) else None
    return _URL.sub("<host>", message) if isinstance(message, str) else None


def classify(response: httpx.Response) -> XippiosError | None:
    """The gateway's and ESR's error shapes as taxonomy errors (sdk-core ADR-0031, decision 2).

    The gateway's answers come first, mapped by ``gateway.classify``: its ``API_KEY_*``
    refusals (recorded: ``API_KEY_INVALID``, ``get_commodities/invalid_key.json``),
    its 429 and its ``NOT_FOUND`` 404 (neither recorded for ESR; the tests build them in
    the shapes api.data.gov documents and sdk-usda-psd recorded), and, given ``DATA_PATH``,
    ESR's own answer for a market year it holds no data for, a 404 with an empty
    ``text/plain`` body on an exports path, recorded for 1900 on both forms
    (``get_country_data/year_1900.json``, ``get_all_countries_data/year_1900.json``), as
    the shared package's ``NoDataForYear``, a ``NotFoundError``. ESR's own follow:

    - An empty 404 anywhere else, off an exports path or not ``text/plain``, is a plain
      ``NotFoundError``: it says the request is wrong, not that the year is empty.
    - 400 with ESR's ``{"message": "The request is invalid."}`` is ``InvalidRequestError``:
      a path value that is not an integer (``exports/commodityCode/abc/...``, recorded as
      ``get_country_data/not_an_integer.json``). The package never sends one, since
      its parameters are ``int``.

    An unknown commodity or country code answers HTTP 200 with ``[]``
    (``unknown_commodity``, ``unknown_country``), and so do a market year in the future
    (``year_2099``) and valid codes without exports (rye, market year 2024,
    ``get_all_countries_data/rye_2024.json``): empty means empty, not an error; the
    package refuses unknown codes and future years before the call (``params``).
    Everything else falls through to core's status mapping. ESR's own two errors name the
    request as ``request_description`` gives it, method and path; the gateway's keep core's text.
    """
    error = gateway.classify(response)
    if error is not None:
        return error
    status = response.status_code
    request = request_description(response)
    if status == 404 and not response.content.strip():
        return NotFoundError(
            f"ESR has no data for {request} (HTTP 404 with an empty body)", source=SOURCE
        )
    if status == 400:
        refusal = _esr_message(response)
        if refusal is not None:
            return InvalidRequestError(
                f"ESR refused {request} (HTTP 400: {refusal}). Every path value of an ESR "
                "export query is an integer: commodity code, country code and market year.",
                source=SOURCE,
            )
    return None


config = gateway.install(
    ClientConfig(
        source=SOURCE,
        version=__version__,
        base_url=BASE_URL,
        rate_limit=RATE_LIMIT,
        cache=MemoryCache(),
        headers={"Accept": "application/json"},
        classify=classify,
    )
)
# The key is read from the environment on the first request, never at import.
auth = gateway.auth
client = AsyncClient(config, auth=auth)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "DATA_PATH",
    "ENV_VARS",
    "RATE_LIMIT",
    "SOURCE",
    "auth",
    "classify",
    "client",
    "config",
    "gateway",
]
