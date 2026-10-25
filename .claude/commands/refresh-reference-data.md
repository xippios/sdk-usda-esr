Refresh the packaged reference data for USDA FAS Export Sales Reporting: $ARGUMENTS

Reference data the upstream publishes for every caller alike (code lists, attribute
lists, report calendars) may ship inside the package under
`src/xippios/usda/esr/reference/` and is loaded with `xippios.core.reference`. It
comes from the upstream, never from memory. Not every source packages lists: one that
changes often stays a lookup task that calls upstream. A multi-tenant source (ADR-0014)
packages no tenant data, only reference lists that are the same for every tenant, if any.

1. Work on a branch `chore/reference-<thing>`.
2. Identify the upstream list endpoint for each list named in the arguments, using
   `docs/upstream/`; a wrapper for it belongs in `api/` (`/add-endpoint`).
3. Add the list to `scripts/refresh_reference.py`, by its shape, then run the script from
   the repository root with whatever the list endpoints need in the environment (a key
   only where they take one). It writes `reference/<name>.json` with the fetch date and
   regenerates `enums.py`, ASCII-only and ruff-clean as core renders it, committed as
   rendered with no formatting step after it (ADR-0008):
   - a list of strings goes into `LISTS` (name as upstream calls it, fetcher through
     `api/`) and `PACKAGED_LISTS` in `params.py`; `render_str_enums` makes one `StrEnum`
     of it. A value with no identifier to derive (a non-Latin label, a name too long for
     a line) is named once through `member_names=` in the script's `render_str_enums`
     call;
   - a list of integer ids and names goes into `ID_LISTS` (id field and name field as
     upstream names them, fetcher of the records through `api/`); the records are
     packaged under upstream's field names, `id_name_pairs` builds their `(id, name)`
     pairs and `render_int_enums` one `IntEnum`, so a member equals the id in upstream's
     data (conventions §3). `member_names=` takes ids there.

   Each renderer writes a whole module, so `enums.py` holds one kind and the script
   refuses to run with both mappings filled; a source with lists of both kinds keeps the
   second kind in a module of its own and says so in the PR. Tables that are not plain
   value lists go under `reference/` as CSV with upstream column names, written by the
   same script. `uv run python scripts/refresh_reference.py --render-only` regenerates
   `enums.py` from the packaged files alone, without a request or a key, as an adoption
   does after a core release changes the renderers (`/adopt-release`).
4. Update the provenance table in `reference/README.md`: file, origin (endpoint or
   URL), fetch date.
5. If agents have no lookup task for this list yet, add one with `/add-endpoint` so they
   can look the codes up: one lookup task per list (`list_<thing>`), or the upstream's
   own lookup operation when it serves every list through one. A lookup over a packaged
   list returns the packaged data, it does not call upstream. A list an agent needs whole
   that is longer than the default result cap (200 rows or 64 KB) gets a cap of its own,
   `MCP_CAPS` in `tasks.py`, keyed by the task's name (ADR-0016).
6. Run the checks and open the PR with the diff summarised: how many rows changed, any
   codes that disappeared (those may break existing fixtures or callers). Do not merge.
