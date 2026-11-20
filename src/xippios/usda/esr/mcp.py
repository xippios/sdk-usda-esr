"""MCP server for USDA FAS Export Sales Reporting.

Every task in ``tasks.__all__`` is a read-only tool, but those ``tasks.BULK_TASKS``
names (``tool_functions``, sdk-core ADR-0040). No logic lives here (sdk-core ADR-0001). Entry point:
``xippios-usda-esr-mcp``.

The package contract (conventions §8; sdk-core ADR-0026, amendment 2026-11-18, points c and d):
``build()`` returns the tool set a host serves as this entry point does, with the caps
and the option hooks ``tasks.py`` defines, ``MCP_CAPS``, ``mcp_add_options`` and
``mcp_apply_options``; ``server`` is built from it, and ``ENV_VARS`` beside ``SOURCE``
names the variables the package reads.
"""

from xippios.core.mcp import ToolSet, build_server, main, tool_functions

from xippios.usda.esr import tasks
from xippios.usda.esr._client import ENV_VARS, SOURCE
from xippios.usda.esr._version import __version__

__all__ = ["ENV_VARS", "SOURCE", "build", "run", "server"]

INSTRUCTIONS = (
    "USDA FAS Export Sales Reporting via xippios. "
    "Tools are read-only. "
    "Where list tools (usda_esr_list_*) exist, call them first to find valid values, "
    "then query."
)


def build() -> ToolSet:
    """The read-only tool set: the tasks with their caps, text, version and option hooks."""
    return ToolSet(
        SOURCE,
        tool_functions(tasks),
        caps=getattr(tasks, "MCP_CAPS", None),
        instructions=INSTRUCTIONS,
        version=__version__,
        add_options=getattr(tasks, "mcp_add_options", None),
        apply_options=getattr(tasks, "mcp_apply_options", None),
    )


server = build_server(build())


def run() -> None:
    """Run the server: stdio by default, ``--http`` for streamable HTTP, the source's options."""
    tools = build()
    main(server, add_options=tools.add_options, apply_options=tools.apply_options)
