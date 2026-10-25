"""The adapters expose exactly the tasks, in the shapes the conventions prescribe.

Per-task end-to-end calls belong next to the task's replay test, with
``xippios.core.testing.mcp_call`` and FastAPI's ``TestClient``.
"""

import inspect
import typing
from collections.abc import Callable

import pytest
from fastapi.routing import APIRoute
from xippios.core.http import is_scalar
from xippios.core.mcp import tool_name

from xippios.usda.esr import tasks
from xippios.usda.esr._client import SOURCE
from xippios.usda.esr.http import router
from xippios.usda.esr.mcp import server

pytestmark = pytest.mark.anyio

TASKS: dict[str, Callable[..., object]] = {name: getattr(tasks, name) for name in tasks.__all__}


def _parameters(fn: Callable[..., object]) -> dict[str, object]:
    hints = typing.get_type_hints(fn)
    parameters = inspect.signature(fn).parameters.values()
    return {p.name: hints.get(p.name, p.annotation) for p in parameters}


async def test_mcp_tools_are_the_tasks_with_their_parameters() -> None:
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert set(tools) == {tool_name(SOURCE, fn) for fn in TASKS.values()}
    for name, fn in TASKS.items():
        tool = tools[tool_name(SOURCE, fn)]
        assert set(tool.input_schema.get("properties", {})) == set(_parameters(fn)), name
        assert tool.description, f"{name} has no docstring; agents read it"


async def test_http_routes_are_the_tasks_with_the_right_methods() -> None:
    routes = {route.path: route for route in router.routes if isinstance(route, APIRoute)}
    assert set(routes) == {f"/{SOURCE}/{name}" for name in TASKS}
    for name, fn in TASKS.items():
        scalar_only = all(is_scalar(annotation) for annotation in _parameters(fn).values())
        assert routes[f"/{SOURCE}/{name}"].methods == ({"GET"} if scalar_only else {"POST"}), name
