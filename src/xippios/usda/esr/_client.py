"""The configured ``xippios.core`` client for USDA FAS Export Sales Reporting.

One ``AsyncClient`` for the whole package: task functions share its rate limiter and
cache, and the same instance serves the sync facades and the MCP server.
"""

from xippios.core import AsyncClient, ClientConfig, HeaderKeyAuth, RateLimit

from xippios.usda.esr._version import __version__

SOURCE = "usda-esr"
BASE_URL = "https://api.fas.usda.gov"
API_KEY_ENV = "DATA_GOV_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
# A self-imposed pace: upstream documents no limit (ADR-0010 decision 1).
RATE_LIMIT = RateLimit(per_minute=60, burst=1)

config = ClientConfig(
    source=SOURCE,
    version=__version__,
    base_url=BASE_URL,
    rate_limit=RATE_LIMIT,
)

# An upstream that reports an hourly or daily quota installs one QuotaPolicy, from
# xippios.core, on config: it reads the quota headers of every answer and never sends
# into a spent quota, waiting within the retry backoff or raising RateLimitError
# (ADR-0015; ADR-0010 decisions 3 and 4). Name only headers that count that quota, never
# a pace (None turns one off); window is the fallback wait, 86400.0 for a daily quota.
# classify, the ClientConfig hook, maps upstream's answer to a spent quota to
# RateLimitError with retry_after. A source without a quota adds nothing.
#
# policy = QuotaPolicy(
#     window=3600.0,
#     limit_header="x-ratelimit-limit",
#     remaining_header="x-ratelimit-remaining",
#     source=SOURCE,
# )
# config = policy.install(config)

# The key is read from the environment on the first request, never at import.
auth = HeaderKeyAuth("X-Api-Key", API_KEY_ENV, source=SOURCE)
client = AsyncClient(config, auth=auth)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "RATE_LIMIT",
    "SOURCE",
    "auth",
    "client",
    "config",
]
