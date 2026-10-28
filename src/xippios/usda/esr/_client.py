"""The configured ``xippios.core`` client for USDA FAS Export Sales Reporting.

One ``AsyncClient`` for the whole package, shared by the tasks, the sync facades and the
MCP server, on api.data.gov's gateway at ``BASE_URL`` with ``Accept: application/json``.
It keeps a pace of its own, ``RATE_LIMIT``, since the snapshot documents none. The gateway
is core's, ``xippios.core.data_gov``'s ``Gateway`` (ADR-0009; family review C14):
``gateway.auth`` sends the key from ``DATA_GOV_API_KEY`` in the ``X-Api-Key`` header;
``Gateway.policy``, the one ``QuotaPolicy`` per process for that key, keeps api.data.gov's
hourly quota from every answer and never fires a request into a spent one, waiting within
the policy's ``pause_cap`` or refusing without sending, a refusal that speaks for
``api.data.gov`` (ADR-0010, ADR-0015); and ``gateway.classify`` maps the gateway's
``API_KEY_*`` answers to ``AuthError``, its 429 to ``RateLimitError`` (its ``Retry-After``
read by the gateway) and its ``NOT_FOUND`` to ``NotFoundError``. ``classify`` asks the
gateway first and then maps ESR's own answers: its empty 404 on an exports path to
``errors.NoDataForYear`` and its 400 for a path value that is not an integer to
``InvalidRequestError``.
"""

import re

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    InvalidRequestError,
    NotFoundError,
    RateLimit,
    XippiosError,
)
from xippios.core.data_gov import API_KEY_ENV, Gateway

from xippios.usda.esr._version import __version__

SOURCE = "usda-esr"
BASE_URL = "https://api.fas.usda.gov"
"""The gateway's host root; every ESR path keeps its ``/api/esr/`` prefix, as the snapshot's
``paths`` name it (the portal document's ``host`` is ``api.fas.usda.gov``, no ``basePath``)."""
# A self-imposed pace: upstream documents no per-second or per-minute limit (ADR-0010 decision 1).
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
# process that every source behind the gateway shares (ADR-0009).
gateway = Gateway(SOURCE)

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
    """The gateway's documented and ESR's recorded error shapes, mapped once (ADR-0008).

    The gateway's answers come first, mapped by ``gateway.classify``: its ``API_KEY_*``
    refusals (recorded: ``API_KEY_INVALID``, ``get_commodities/invalid_key.json``),
    its 429 and its ``NOT_FOUND`` 404 (neither recorded for ESR; the tests build them in
    the shapes api.data.gov documents and sdk-usda-psd recorded). ESR's own follow:

    - 404 with an empty ``text/plain`` body on an exports path (``DATA_PATH``) is ESR's own
      answer for a market year it holds no data for, recorded for 1900
      (``get_country_data/year_1900.json``). It is ``errors.NoDataForYear``, a
      ``NotFoundError``; an empty 404 anywhere else is a plain ``NotFoundError``.
    - 400 with ESR's ``{"message": "The request is invalid."}`` is ``InvalidRequestError``:
      a path value that is not an integer (``exports/commodityCode/abc/...``, recorded as
      ``get_country_data/not_an_integer.json``). The package never sends one, since
      its parameters are ``int``.

    An unknown commodity or country code answers HTTP 200 with ``[]``
    (``unknown_commodity``, ``unknown_country``), and so do a market year in the future
    (``year_2099``) and valid codes without exports (rye, market year 2024,
    ``get_all_countries_data/rye_2024.json``): empty means empty, not an error; the
    package refuses unknown codes and future years before the call (``params``).
    Everything else falls through to core's status mapping. Messages name the path, never
    the host.
    """
    error = gateway.classify(response)
    if error is not None:
        return error
    status = response.status_code
    path = response.request.url.path
    if status == 404 and not response.content.strip():
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


config = gateway.install(
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
auth = gateway.auth
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
    "gateway",
]
