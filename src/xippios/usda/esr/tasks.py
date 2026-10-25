"""Task-shaped functions for USDA FAS Export Sales Reporting.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.
"""

__all__: list[str] = []

# MCP_CAPS, only where a tool needs a result cap of its own: a list an agent needs whole
# (conventions §8, ADR-0016), keyed by task function name; mcp.py reads it with getattr,
# so a source without one adds nothing. ResultCap needs the mcp extra, which a base
# install lacks, so its import is guarded and a base install, which serves no tool, gets
# an empty mapping (the annotation quoted, Mapping from collections.abc):
#
# try:
#     from xippios.core.mcp import ResultCap
# except ImportError:  # pragma: no cover - a base install has no MCP server
#     MCP_CAPS: "Mapping[str, ResultCap]" = {}
# else:
#     MCP_CAPS = {"list_<thing>": ResultCap(max_rows=400)}
