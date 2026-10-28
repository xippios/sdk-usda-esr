"""The client's wiring and error mapping, and core's api.data.gov gateway wired to it.

Recorded answers come from ``tests/fixtures`` (2026-10-25). Cases the recordings do not
cover are built in api.data.gov's documented shapes and say "NOT RECORDED": the
gateway's 429 (``OVER_RATE_LIMIT``; spending the key's hourly quota, shared with
sdk-usda-psd and sdk-usda-gats, to record it was not worth it; its shape is the one
api.data.gov documents and sdk-usda-psd recorded on 2026-10-23), the gateway's
``NOT_FOUND`` 404 and the other ``API_KEY_*`` codes. The gateway and its quota policy are
core's (``xippios.core.data_gov.Gateway``, ADR-0009, ADR-0015) and are tested there; this
module checks that the package installs them, that the policy reads a 429 and the recorded
quota headers through the package's client, that ``classify`` keeps ESR's own answers
after the gateway's, and that it shapes core's retries of a 429.
"""

import dataclasses
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import (
    AsyncClient,
    AuthError,
    InvalidRequestError,
    NotFoundError,
    RateLimitError,
    RetryPolicy,
)
from xippios.core.data_gov import Gateway
from xippios.core.testing import CLOCK_SLACK, load_fixture, response_from_fixture

from xippios.usda.esr import api
from xippios.usda.esr._client import (
    API_KEY_ENV,
    BASE_URL,
    DATA_PATH,
    RATE_LIMIT,
    SOURCE,
    auth,
    classify,
    client,
    config,
    gateway,
)
from xippios.usda.esr.errors import NoDataForYear

FIXTURES = Path(__file__).parent / "fixtures"
COUNTRY = "get_country_data"
EXPORTS = "/api/esr/exports/commodityCode/104/countryCode/1220/marketYear"
SLACK = CLOCK_SLACK.total_seconds()
"""A wait read through the client counts from the snapshot to now, a moment later."""


def synthesised(
    status: int,
    body: object,
    headers: dict[str, str] | None = None,
    path: str = "/api/esr/commodities",
) -> httpx.Response:
    """NOT RECORDED as such: an answer in the shape api.data.gov documents and sends."""
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
behind the same gateway (``OVER_RATE_LIMIT`` and a message ending in the gateway's URL)."""
QUOTA_SPENT = {"Retry-After": "3151", "x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
"""NOT RECORDED: the 429's headers as sdk-usda-psd recorded them: ``Retry-After`` and the
quota headers at zero."""
GATEWAY_NOT_FOUND = {
    "error": {
        "code": "NOT_FOUND",
        "message": "The requested URL was not found on this server.",
    }
}
"""NOT RECORDED: api.data.gov's documented ``NOT_FOUND`` body."""


def test_the_client_is_wired_for_the_gateway() -> None:
    """One request per second, esr's classify, and core's gateway: its key auth and its
    one quota policy per process on api.data.gov's ``x-ratelimit-*`` headers, which count
    the rolling hour, not a pace; one hour is the fallback wait (ADR-0009, ADR-0015)."""
    assert (RATE_LIMIT.per_minute, RATE_LIMIT.capacity) == (60, 1)
    assert config.rate_limit is RATE_LIMIT
    assert config.classify is classify
    assert client.config is config
    assert config.base_url == BASE_URL == "https://api.fas.usda.gov"
    assert gateway.source == SOURCE == "usda-esr"
    assert gateway.policy is Gateway.policy, "one policy per process for the shared key"
    assert config.observe == Gateway.policy.observe, "installed: every answer reaches it"
    assert config.before_request == Gateway.policy.before_request
    assert (Gateway.policy.limit_header, Gateway.policy.remaining_header) == (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
    )
    assert (Gateway.policy.window, Gateway.policy.source) == (3600.0, "api.data.gov")
    assert auth is gateway.auth
    assert auth.header == "X-Api-Key"
    assert auth.env_var == API_KEY_ENV == "DATA_GOV_API_KEY"  # pragma: allowlist secret


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


def test_the_data_path_covers_both_exports_forms_only() -> None:
    assert DATA_PATH.fullmatch(f"{EXPORTS}/2024")
    assert DATA_PATH.fullmatch("/api/esr/exports/commodityCode/1201/allCountries/marketYear/2024")
    assert not DATA_PATH.fullmatch("/api/esr/datareleasedates")
    assert not DATA_PATH.fullmatch("/api/esr/exports/commodityCode/104/marketYear/2024")


def test_invalid_key_is_an_auth_error_naming_the_code_and_the_variable() -> None:
    """The gateway's text, from ``gateway.classify``: the code, the variable, never the key."""
    response = response_from_fixture(
        load_fixture(FIXTURES / "get_commodities" / "invalid_key.json")
    )
    assert response.status_code == 403
    assert "x-ratelimit-remaining" not in response.headers, "no quota headers for a bad key"
    error = classify(response)
    assert isinstance(error, AuthError)
    assert error.status == 403
    assert error.message.startswith(
        f"api.data.gov refused the key in {API_KEY_ENV} (HTTP 403 API_KEY_INVALID: "
    )
    assert "An invalid api_key was supplied. Get one at <host>" in error.message
    assert "api.fas.usda.gov" not in error.message, "host-free (conventions §5)"
    assert error.source == SOURCE


@pytest.mark.parametrize(
    "code",
    ["API_KEY_MISSING", "API_KEY_DISABLED", "API_KEY_UNAUTHORIZED", "API_KEY_UNVERIFIED"],
)
def test_every_documented_key_code_is_an_auth_error(code: str) -> None:
    """NOT RECORDED: the other documented codes, in the recorded body's shape."""
    error = classify(synthesised(403, {"error": {"code": code, "message": "documented"}}))
    assert isinstance(error, AuthError)
    assert code in error.message


def test_a_403_without_a_gateway_code_falls_through_to_core() -> None:
    assert classify(synthesised(403, {"Message": "Access denied"})) is None


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
    assert await client.get_json(response.request.url.path) == []
    assert route.call_count == 1


@pytest.mark.anyio
async def test_market_year_1900_answers_404_with_an_empty_body(
    replay_fixture: Callable[[str, str], respx.Route],
) -> None:
    response = response_from_fixture(load_fixture(FIXTURES / COUNTRY / "year_1900.json"))
    assert (response.status_code, response.content) == (404, b"")
    assert response.headers["content-type"].startswith("text/plain")
    error = classify(response)
    assert isinstance(error, NoDataForYear)
    assert isinstance(error, NotFoundError), "in the taxonomy, conventions §5"
    assert error.path == f"{EXPORTS}/1900"
    assert f"no data for {EXPORTS}/1900 (HTTP 404 with an empty body)" in error.message
    route = replay_fixture(COUNTRY, "year_1900")
    with pytest.raises(NoDataForYear, match="empty body"):
        await api.get_country_data(104, 1220, 1900)
    assert route.call_count == 1, "a 404 is never retried"


def test_the_content_type_is_compared_without_case() -> None:
    """NOT RECORDED as such: the recorded empty 404 with its content type upper-cased.
    Media types are case-insensitive (RFC 9110), so it is still ESR's empty year."""
    response = httpx.Response(
        404,
        headers=[("Content-Type", "TEXT/PLAIN; charset=utf-8")],
        content=b"",
        request=httpx.Request("GET", f"{BASE_URL}{EXPORTS}/1900"),
    )
    assert isinstance(classify(response), NoDataForYear)


def test_an_empty_404_is_no_data_for_year_only_on_an_exports_path_as_text() -> None:
    """NOT RECORDED: the recorded empty 404 moved off an exports path, or without its
    ``text/plain``. Neither is ESR's answer for an empty year: both stay a plain
    ``NotFoundError``."""
    fixture = load_fixture(FIXTURES / COUNTRY / "year_1900.json")
    for url, headers in [
        (f"{BASE_URL}/api/esr/datareleasedates", fixture.response.headers),
        (fixture.request.url, [("content-type", "application/json")]),
    ]:
        response = httpx.Response(
            404, headers=headers, content=b"", request=httpx.Request("GET", url)
        )
        error = classify(response)
        assert isinstance(error, NotFoundError)
        assert not isinstance(error, NoDataForYear), url


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
    assert f"ESR refused {path} (HTTP 400: The request is invalid.)" in error.message
    assert "api.fas.usda.gov" not in error.message
    route = replay_fixture(COUNTRY, "not_an_integer")
    with pytest.raises(InvalidRequestError, match="The request is invalid"):
        await client.get_json(path)
    assert route.call_count == 1


def test_a_400_without_esrs_message_falls_through_to_core() -> None:
    """NOT RECORDED: a 400 in another shape is core's ``UpstreamError``, not a guess."""
    assert classify(synthesised(400, ["not", "an", "object"])) is None


def test_the_gateway_not_found_is_a_not_found_error() -> None:
    """NOT RECORDED: api.data.gov's documented NOT_FOUND body, on an exports path too."""
    for path in ("/api/esr/commodities", f"{EXPORTS}/2024"):
        error = classify(synthesised(404, GATEWAY_NOT_FOUND, path=path))
        assert isinstance(error, NotFoundError)
        assert not isinstance(error, NoDataForYear), "a wrong request, not an empty year"
        assert f"api.data.gov has no route for {path}" in error.message


def test_other_statuses_fall_through_to_core() -> None:
    assert classify(synthesised(500, {"Message": "An error has occurred."})) is None
    for path in [
        FIXTURES / "get_commodities" / "all.json",
        FIXTURES / COUNTRY / "wheat_white_canada_2024.json",
    ]:
        assert classify(response_from_fixture(load_fixture(path))) is None, path.name


def test_a_429_is_a_rate_limit_error_with_its_retry_after() -> None:
    """NOT RECORDED: api.data.gov's 429 with ``Retry-After`` and the quota at zero.
    ``classify`` called on its own gives the exact wait: no client has observed it."""
    error = classify(synthesised(429, OVER_RATE_LIMIT, QUOTA_SPENT))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 3151.0
    assert "OVER_RATE_LIMIT: You have exceeded your rate limit" in error.message
    assert "api.fas.usda.gov" not in error.message, "host-free (conventions §5)"
    assert "expected back in 3151 s" in error.message, "no snapshot without the client"
    assert "retry after" not in error.message, "core's adapters append the retry hint"
    assert API_KEY_ENV in error.message
    assert error.source == SOURCE


def test_a_429_without_retry_after_falls_back_to_the_quota_window() -> None:
    """NOT RECORDED: the 429 body without Retry-After or quota headers."""
    error = classify(synthesised(429, OVER_RATE_LIMIT))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == Gateway.policy.window == 3600.0
    assert "an hourly quota per key" in error.message, "no limit known, none invented"
    assert "expected back in 3600 s" in error.message


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_the_policy_reads_a_429_through_core(respx_mock: respx.MockRouter) -> None:
    """NOT RECORDED: the 429 through the package's client. ``Gateway.policy``'s ``observe``
    marks the quota spent until its ``Retry-After``, ``classify`` raises after one request
    (3151 s is beyond ``backoff_max``) with the snapshot's wait from now, and the next
    request is refused before it is sent, in the gateway's name. Marked ``rate_limited``:
    the refusal is the policy's pause, which the plugin turns off."""
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
    assert refused.value.message.startswith(f"api.data.gov quota of the key in {API_KEY_ENV} spent")
    assert refused.value.retry_after is not None
    assert 3151 - SLACK <= refused.value.retry_after <= 3151
    assert regions.call_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("retry_after", "shaped", "attempts"),
    [("3151", True, 1), (None, True, 1), (None, False, 4)],
    ids=["with_retry_after", "without_retry_after", "control_without_classify"],
)
async def test_core_retries_a_429_only_within_its_backoff(
    respx_mock: respx.MockRouter, retry_after: str | None, shaped: bool, attempts: int
) -> None:
    """NOT RECORDED: the 429 above. esr's ``classify`` shapes core's retries (ADR-0015): its
    ``RateLimitError`` carries the wait, ``Retry-After`` or else the one-hour window, beyond
    ``backoff_max`` (30 s), so a 429 is sent once, with or without the header. The control
    drops ``classify``: core then retries the 429 without ``Retry-After`` on its status
    alone, three more times at its short backoff, so this test fails if ``classify`` stops
    shaping the retries."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    headers = dict(QUOTA_SPENT)
    if retry_after is None:
        del headers["Retry-After"]
    route = respx_mock.get(f"{BASE_URL}/api/esr/commodities").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=headers)
    )
    quick = dataclasses.replace(config, rate_limit=None)
    if not shaped:
        quick = dataclasses.replace(quick, classify=None)
    with pytest.raises(RateLimitError) as info:
        await AsyncClient(quick, sleep=fake_sleep).get_json("/api/esr/commodities")
    assert route.call_count == attempts
    assert len(sleeps) == attempts - 1
    assert all(seconds <= RetryPolicy().backoff_max for seconds in sleeps)
    if shaped:
        # read through the client: the snapshot's wait from now, a moment under the header's
        assert info.value.retry_after is not None
        expected = float(retry_after or 3600)
        assert expected - SLACK <= info.value.retry_after <= expected
    else:
        assert info.value.retry_after is None, "core's own mapping: no Retry-After, no wait"
