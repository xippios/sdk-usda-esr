# Core's plugin keeps the default run offline and free of real keys (sdk-core ADR-0035),
# runs anyio tests on asyncio and serves the family check in tests/test_family.py; it reads a
# key's variable from ENV_VARS in _client.py and sets it to its placeholder, not here.
pytest_plugins = ["xippios.core.testing.plugin"]
