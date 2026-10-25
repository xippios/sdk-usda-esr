import pytest

# Core's plugin keeps the default run offline and free of real keys (ADR-0013); a key's
# variable is named under xippios_placeholder_key_envs in pyproject.toml, not here.
pytest_plugins = ["xippios.core.testing.plugin"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
