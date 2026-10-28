# Core's plugin keeps the default run offline and free of real keys (ADR-0013), runs anyio
# tests on asyncio and serves the family check in tests/test_family.py; a key's variable is
# named under xippios_placeholder_key_envs in pyproject.toml, not here.
pytest_plugins = ["xippios.core.testing.plugin"]
