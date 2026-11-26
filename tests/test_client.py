"""The client's wiring and error mapping, and the shared package's api.data.gov gateway on it.

Recorded answers come from ``tests/fixtures`` (2026-10-25; the every-country form's 1900,
2026-10-28). Cases they do not cover say "NOT RECORDED", of three kinds conventions §10 name:
api.data.gov's documented 429 (``OVER_RATE_LIMIT``, in the shape sdk-usda-psd recorded on
2026-10-23, since recording it would spend the key's shared hourly quota); ESR's recorded empty
404 at its own URL with its content type changed; and a 400 in no shape upstream sends. The
gateway and its quota policy are the shared package's (``xippios.usda.fas``'s ``Gateway``,
sdk-core ADR-0032, sdk-core ADR-0037), whose tests hold its answers, the key's codes, the
policy's headers and window, a 429 classified on its own and core's retries of a 429; this
module checks that the package installs them, that the policy reads a 429
and the recorded quota headers through the package's client, and that ``classify`` keeps ESR's
own answers after the gateway's.
"""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import (
    Answer,
    AuthError,
    EnvVar,
    InvalidRequestError,
    MemoryCache,
    NotFoundError,
    RateLimitError,
)
from xippios.core.errors import request_description
from xippios.core.testing import CLOCK_SLACK, load_fixture, response_from_fixture
from xippios.usda.fas import Gateway, NoDataForYear

from xippios.usda.esr import api
from xippios.usda.esr._client import (
    API_KEY_ENV,
    BASE_URL,
    DATA_PATH,
    ENV_VARS,
    RATE_LIMIT,
    SOURCE,
    auth,
    classify,
    client,
    config,
    gateway,
)

FIXTURES = Path(__file__).parent / "fixtures"
COUNTRY = "get_country_data"
ALL = "get_all_countries_data"
EXPORTS = "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear"
SLACK = CLOCK_SLACK.total_seconds()
"""A wait read through the client counts from the snapshot to now, a moment later."""


def synthesised(
    status: int,
    body: object,
    headers: dict[str, str] | None = None,
    path: str = "/api/esr/commodities",
) -> httpx.Response:
    """NOT RECORDED as such: an answer in the shape api.data.gov documents and sends.
    It is composed from what the gateway documents (conventions §10, kind 2).
    """
    return httpx.Response(
        status,
        json=body,
        headers=headers or {},
        request=httpx.Request("GET", f"{BASE_URL}{path}"),
    )


OVER_RATE_LIMIT = {
    "error": {
        "code": "OVER_RATE_LIMIT",
        "message": "You have exceeded your rate limit. Try again later or contact us for "
        "assistance: https://api.fas.usda.gov:443",
    }
}
"""NOT RECORDED: api.data.gov's 429 body, in the shape sdk-usda-psd recorded on 2026-10-23
behind the same gateway (``OVER_RATE_LIMIT`` and a message ending in the gateway's URL;
conventions §10, kind 2)."""
QUOTA_SPENT = {"Retry-After": "3151", "x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
"""NOT RECORDED: the 429's headers as sdk-usda-psd recorded them: ``Retry-After`` and the
quota headers at zero (conventions §10, kind 2)."""


def test_the_client_is_wired_for_the_gateway() -> None:
    """One request per second, esr's classify, and the shared package's gateway installed: its
    key auth and its one quota policy per process for the shared key, whose headers and window
    the shared package's tests hold (sdk-core ADR-0032, sdk-core ADR-0037)."""
    assert (RATE_LIMIT.per_minute, RATE_LIMIT.capacity) == (60, 1)
    assert config.rate_limit is RATE_LIMIT
    assert config.classify is classify
    assert client.config is config
    assert config.base_url == BASE_URL == "https://api.fas.usda.gov"
    assert gateway.source == SOURCE == "usda-esr"
    assert gateway.data_path is DATA_PATH, "FAS's empty 404 is mapped there (sdk-core#106)"
    assert gateway.policy is Gateway.policy, "one policy per process for the shared key"
    assert config.observe == Gateway.policy.observe, "installed: every answer reaches it"
    assert config.before_request == Gateway.policy.before_request
    assert auth is gateway.auth
    assert (auth.location, auth.name) == ("header", "X-Api-Key")
    assert auth.env_var == API_KEY_ENV == "DATA_GOV_API_KEY"  # pragma: allowlist secret


def test_env_vars_name_the_one_key_the_package_reads() -> None:
    """``ENV_VARS`` tells a host what to set: the gateway's key, secret and required, and
    nothing else, since the package reads no other variable (conventions §7)."""
    assert (EnvVar(API_KEY_ENV, secret=True, required=True),) == ENV_VARS


def test_the_client_asks_for_json() -> None:
    """The snapshot's operations produce JSON and XML; httpx alone sends ``Accept: */*``."""
    assert config.headers == {"Accept": "application/json"}


@pytest.mark.anyio
async def test_the_key_goes_in_the_header_and_the_quota_headers_reach_the_policy(
    replay_fixture: Callable[[str, str], respx.Route], placeholder_api_key: str
) -> None:
    """Offline the key is core's placeholder; the recorded answer's quota headers, 1000 per
    hour and 987 left, are what the policy keeps."""
    route = replay_fixture(COUNTRY, "wheat_white_canada_2024")
    await api.get_country_data(104, 1220, 2024)
    assert [call.request.headers.get("X-Api-Key") for call in route.calls] == [placeholder_api_key]
    assert [call.request.headers.get("Accept") for call in route.calls] == ["application/json"]
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert (snapshot.limit, snapshot.remaining, snapshot.resumes_at) == (1000, 987, None)


def test_the_client_keeps_answers_in_cores_cache() -> None:
    """A read-only source of public data keeps upstream's answers in core's response cache,
    at core's default lifetime, every path for 300 s (conventions §6; sdk-core ADR-0061,
    decision 11)."""
    assert isinstance(config.cache, MemoryCache)
    assert dict(config.cache.lifetimes) == {"/": 300.0}


@pytest.mark.anyio
async def test_a_second_read_of_a_path_is_answered_from_the_cache(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """The release list, which the series and the exports read before their own request, is
    sent once: the second read is the cache's, with the time its entry was stored (sdk-core
    ADR-0037, decision 5)."""
    route = replay_fixture("get_data_release_info", "all")
    first = await api.get_data_release_info()
    second = await api.get_data_release_info()
    assert isinstance(first, Answer)
    assert route.call_count == 1
    assert second.retrieved_at == first.retrieved_at
    assert second.payload == first.payload


def test_the_data_path_covers_both_exports_forms_only() -> None:
    assert DATA_PATH.fullmatch(f"{EXPORTS}/2024")
    assert DATA_PATH.fullmatch("/api/esr/exports/commodityCode/1201/allCountries/marketYear/2024")
    assert not DATA_PATH.fullmatch("/api/esr/datareleasedates")
    assert not DATA_PATH.fullmatch("/api/esr/exports/commodityCode/104/marketYear/2024")


@pytest.mark.anyio
async def test_the_wrapper_raises_auth_error_on_the_recorded_invalid_key(
    replay_fixture: Callable[[str, str], respx.Route], placeholder_api_key: str
) -> None:
    route = replay_fixture("get_commodities", "invalid_key")
    with pytest.raises(AuthError, match="API_KEY_INVALID") as info:
        await api.get_commodities()
    assert placeholder_api_key not in str(info.value)
    assert route.call_count == 1, "a 403 is never retried"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("wrapper", "case", "path"),
    [
        (COUNTRY, "unknown_commodity", "/api/esr/exports/commodityCode/999/countryCode/1220"),
        (COUNTRY, "unknown_country", "/api/esr/exports/commodityCode/104/countryCode/9999"),
        (COUNTRY, "year_2099", EXPORTS),
        ("get_all_countries_data", "rye_2024", "/api/esr/exports/commodityCode/501"),
    ],
)
async def test_unknown_codes_future_years_and_no_exports_answer_an_empty_list(
    replay_fixture: Callable[[str, str], respx.Route], wrapper: str, case: str, path: str
) -> None:
    """Recorded: an unknown commodity (999) or country (9999), market year 2099 and rye
    for 2024 (valid codes, no exports) all answer HTTP 200 with ``[]``: no error."""
    route = replay_fixture(wrapper, case)
    response = response_from_fixture(load_fixture(FIXTURES / wrapper / f"{case}.json"))
    assert (response.status_code, response.json()) == (200, [])
    assert classify(response) is None
    assert response.request.url.path.startswith(path)
    assert (await client.get_answer(response.request.url.path)).payload == []
    assert route.call_count == 1


@pytest.mark.anyio
async def test_market_year_1900_answers_404_with_an_empty_body(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    response = response_from_fixture(load_fixture(FIXTURES / COUNTRY / "year_1900.json"))
    assert (response.status_code, response.content) == (404, b"")
    assert response.headers["content-type"].startswith("text/plain")
    error = classify(response)
    assert isinstance(error, NoDataForYear), "the shared package's, by data_path"
    assert isinstance(error, NotFoundError), "in the taxonomy, conventions §5"
    assert error.path == f"{EXPORTS}/1900"
    assert error.source == SOURCE
    assert f"no data for GET {EXPORTS}/1900 (HTTP 404 with an empty body)" in error.message
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear, match="empty body"):
        await api.get_country_data(104, 1220, 1900)
    assert route.call_count == 1, "a 404 is never retried"


@pytest.mark.anyio
async def test_market_year_1900_answers_alike_on_the_every_country_path(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Recorded 2026-10-28: ``allCountries`` answers 1900 as the one-country form does."""
    response = response_from_fixture(load_fixture(FIXTURES / ALL / "year_1900.json"))
    assert (response.status_code, response.content) == (404, b"")
    assert response.headers["content-type"].startswith("text/plain")
    error = classify(response)
    assert isinstance(error, NoDataForYear)
    assert error.path == "/api/esr/exports/commodityCode/104/allCountries/marketYear/1900"
    route = replay_fixture(ALL, "year_1900")
    with pytest.raises(NoDataForYear, match="empty body"):
        await api.get_all_countries_data(104, 1900)
    assert route.call_count == 1, "a 404 is never retried"


def test_the_content_type_is_compared_without_case() -> None:
    """NOT RECORDED as such: the recorded empty 404 with its content type upper-cased.
    Media types are case-insensitive (RFC 9110), so it is still ESR's empty year.
    A recorded answer with a header replaced (conventions §10, kind 4).
    """
    response = httpx.Response(
        404,
        headers=[("Content-Type", "TEXT/PLAIN; charset=utf-8")],
        content=b"",
        request=httpx.Request("GET", f"{BASE_URL}{EXPORTS}/1900"),
    )
    assert isinstance(classify(response), NoDataForYear)


def test_an_empty_404_is_no_data_for_year_only_on_an_exports_path_as_text() -> None:
    """NOT RECORDED as such: each recorded empty 404 of 1900 at its own URL, its ``text/plain``
    replaced (conventions §10, kind 4: a header replaced), is a plain ``NotFoundError``. Off an
    exports path nothing is served: no other operation was seen answering an empty 404 and
    the snapshot documents none, so that half rests on the gateway's ``data_path``, which
    matches the path of no other operation."""
    for wrapper in (COUNTRY, ALL):
        response = response_from_fixture(load_fixture(FIXTURES / wrapper / "year_1900.json"))
        response.headers["content-type"] = "application/json"
        error = classify(response)
        assert isinstance(error, NotFoundError)
        assert not isinstance(error, NoDataForYear), wrapper
    assert gateway.data_path is DATA_PATH
    for other in ("datareleasedates", "commodities", "countries", "regions", "unitsOfMeasure"):
        assert not DATA_PATH.fullmatch(f"/api/esr/{other}"), other


@pytest.mark.anyio
async def test_a_path_value_that_is_not_an_integer_is_an_invalid_request(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    """Recorded: ``commodityCode/abc`` answers HTTP 400 ``{"message": "The request is
    invalid."}``. The package never sends one (its parameters are ``int``); classify maps
    it all the same, and core does not retry it."""
    response = response_from_fixture(load_fixture(FIXTURES / COUNTRY / "not_an_integer.json"))
    assert response.status_code == 400
    assert response.json() == {"message": "The request is invalid."}
    error = classify(response)
    assert isinstance(error, InvalidRequestError)
    path = "/api/esr/exports/commodityCode/abc/countryCode/1220/marketYear/2024"
    assert request_description(response) == f"GET {path}"
    assert f"ESR refused GET {path} (HTTP 400: The request is invalid.)" in error.message
    assert "api.fas.usda.gov" not in error.message
    route = replay_fixture(COUNTRY, "not_an_integer")
    with pytest.raises(InvalidRequestError, match="The request is invalid"):
        await client.get_answer(path)
    assert route.call_count == 1


def test_each_error_classify_maps_names_the_request_by_cores_description() -> None:
    """ESR's own answers, after the gateway's, name the request as core's
    ``request_description`` gives it, its method and its path, never the host (conventions
    §5, sdk-core ADR-0030): the 400 recorded at its own path, and, since no empty 404 off an
    exports path or without ``text/plain`` was recorded, the recorded empty 404 of 1900 at its
    own URL, NOT RECORDED as such: its ``text/plain`` replaced (conventions §10, kind 4: a
    header replaced)."""
    empty = response_from_fixture(load_fixture(FIXTURES / COUNTRY / "year_1900.json"))
    empty.headers["content-type"] = "application/json"
    responses = [
        response_from_fixture(load_fixture(FIXTURES / COUNTRY / "not_an_integer.json")),
        empty,
    ]
    for response in responses:
        error = classify(response)
        assert isinstance(error, InvalidRequestError | NotFoundError)
        assert not isinstance(error, NoDataForYear)
        described = request_description(response)
        assert described.startswith("GET /api/esr/")
        assert f" {described} (HTTP {response.status_code}" in error.message, error.message
        assert "api.fas.usda.gov" not in error.message, "never the host"


def test_classify_itself_keeps_an_empty_404_a_plain_not_found_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each recorded empty 404 of 1900, unchanged at its own URL, with the gateway's mapping
    stubbed out: ``classify``'s own branch, which runs after the gateway's, keeps it a plain
    ``NotFoundError``. Only the gateway, given ``DATA_PATH``, says the year holds no data."""
    monkeypatch.setattr(gateway, "classify", lambda response: None)
    for wrapper in (COUNTRY, ALL):
        response = response_from_fixture(load_fixture(FIXTURES / wrapper / "year_1900.json"))
        error = classify(response)
        assert isinstance(error, NotFoundError)
        assert not isinstance(error, NoDataForYear), wrapper
        assert error.source == SOURCE


def test_a_400_without_esrs_message_falls_through_to_core() -> None:
    """NOT RECORDED: a 400 in another shape is core's ``UpstreamError``, not a guess.
    A body of no shape upstream sends (conventions §10, kind 5).
    """
    assert classify(synthesised(400, ["not", "an", "object"])) is None


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_the_policy_reads_a_429_through_core(respx_mock: respx.MockRouter) -> None:
    """NOT RECORDED: the 429 through the package's client. ``Gateway.policy``'s ``observe``
    marks the quota spent until its ``Retry-After``, ``classify`` raises after one request
    (3151 s is beyond ``backoff_max``) with the snapshot's wait from now, and the next
    request is refused before it is sent, in the gateway's name. Marked ``rate_limited``:
    the refusal is the policy's pause, which the plugin turns off.
    The 429 is composed from what the gateway documents (conventions §10, kind 2).
    """
    route = respx_mock.get(f"{BASE_URL}/api/esr/commodities").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=QUOTA_SPENT)
    )
    regions = respx_mock.get(f"{BASE_URL}/api/esr/regions")
    with pytest.raises(RateLimitError) as info:
        await api.get_commodities()
    assert info.value.retry_after is not None
    assert 3151 - SLACK <= info.value.retry_after <= 3151
    assert info.value.source == SOURCE
    assert route.call_count == 1, "not retried"
    assert "1000 requests per rolling hour per key" in info.value.message
    assert "0 of 1000 requests left" in info.value.message
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert (snapshot.limit, snapshot.remaining) == (1000, 0)
    assert snapshot.resumes_at == snapshot.observed_at + timedelta(seconds=3151)
    with pytest.raises(RateLimitError, match="nothing was sent") as refused:
        await api.get_regions()
    assert refused.value.source == "api.data.gov", "the gateway's quota, not esr's"
    assert refused.value.message.startswith("quota spent (")
    assert refused.value.retry_after is not None
    assert 3151 - SLACK <= refused.value.retry_after <= 3151
    assert regions.call_count == 0
