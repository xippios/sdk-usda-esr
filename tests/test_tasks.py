"""Structural checks every task must satisfy. Per-task tests with recorded fixtures go below.

A replay test that checks what was sent compares ``xippios.core.testing.sent_urls(route)``,
the URLs the route received with credentials redacted, rather than keep a request from
``route.calls`` in its frame, where a failure or ``pytest -l`` would print it.
"""

import inspect

import pytest

from xippios.usda.esr import __version__, tasks

TASKS = [getattr(tasks, name) for name in tasks.__all__]


def test_package_has_a_version() -> None:
    assert __version__


@pytest.mark.parametrize("task", TASKS, ids=tasks.__all__)
def test_task_is_a_sync_facade_with_an_agent_docstring(task: object) -> None:
    assert callable(task)
    assert hasattr(task, "async_fn"), "write the async function and derive the sync one with sync()"
    doc = inspect.getdoc(task) or ""
    assert doc, "task functions need a docstring: agents read it"
    assert doc.splitlines()[0].endswith("."), "the first line is one sentence"
    if inspect.signature(task).parameters:
        assert "Args:" in doc, "explain every parameter under Args: with valid-value examples"
