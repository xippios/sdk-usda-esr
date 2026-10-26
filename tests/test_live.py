"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task function gets one live smoke test here, next to the reachability check.
"""

import httpx
import pytest

from xippios.usda.esr._client import BASE_URL, config

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_upstream_answers() -> None:
    """The base URL answers without a server error.

    A plain request, not the package's client, so no key goes out and no call counts
    against the key's quota; a keyed gateway's answer to it (a 403 or a 404, say) still
    shows the host is up.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
    assert response.status_code < 500
