"""MCP server for USDA FAS Export Sales Reporting.

Every task in ``tasks.__all__`` is a read-only tool, but those ``tasks.BULK_TASKS``
names (``tool_functions``, sdk-core ADR-0040). No logic lives here (sdk-core ADR-0001). Entry point:
``xippios-usda-esr-mcp``.

The package contract (conventions §8; sdk-core ADR-0063, decisions 7 and 8): ``build()``
returns the tool set that core builds from ``tasks.py``, with what that module declares for
the server, ``server`` is built from it, and ``ENV_VARS`` beside ``SOURCE`` names the
variables the package reads. No line here is the source's: its server's text, caps and
options stand in ``tasks.py``.
"""

from xippios.core.mcp import ToolSet, build_server, main

from xippios.usda.esr import tasks
from xippios.usda.esr._client import ENV_VARS, SOURCE
from xippios.usda.esr._version import __version__

__all__ = ["ENV_VARS", "SOURCE", "build", "run", "server"]


def build() -> ToolSet:
    """The read-only tool set of ``tasks.py``: its tools, caps, text and option hooks."""
    return ToolSet.from_tasks(SOURCE, tasks, version=__version__)


server = build_server(build())


def run() -> None:
    """Run the server: stdio by default, ``--http`` for streamable HTTP, the source's options."""
    main(build)
