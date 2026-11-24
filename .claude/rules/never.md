# Never

What no change of `xippios-usda-esr` does, whoever makes it. The template writes this
file again at every update, so a rule of the package's own goes into `CLAUDE.md`.

- Never hand-write a fixture, and never commit one without grepping it for key patterns
  (conventions §10).
- Never read or print `.envrc`, `.env`, the credential variable of this package,
  `DATA_GOV_API_KEY`, or any variable ending in `_API_KEY`, `_TOKEN` or
  `_SECRET`.
- Never write a key, a token or another credential into a file or a commit.
- Never put logic in `mcp.py` or `http.py`, and never add a route or a tool by hand: the
  adapters register `tasks.__all__` (sdk-core ADR-0001).
- Never rename or re-map an upstream concept to another source's (sdk-core ADR-0028).
- Never return a documented personal identifier in a task's projection, echo one in
  `meta.request`, or commit one in a fixture (sdk-core ADR-0017).
- Never edit `docs/upstream/` by hand but `docs/upstream/OBSERVED.md`, the notes on what
  upstream does but never documents: `/refresh-upstream` fetches the rest, and the pull
  request shows its diff (conventions §3).
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and the
  package (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone (conventions §12).
