# Reference data for USDA FAS Export Sales Reporting

Code lists and calendars the upstream publishes (commodities, countries, report
schedules) ship here as CSV or JSON, versioned with the package, and load through
`xippios.core.reference`:

```python
from xippios.core import load_table

rows = load_table("xippios.usda.esr", "commodities.csv", Commodity)
```

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py` with `xippios.core.reference`: one `StrEnum` per value list
  (`render_str_enums`), or one `IntEnum` per list of integer ids (`render_int_enums`).
- Files keep upstream's names: a table its column names, a list of integer ids its
  records under upstream's field names.
- Every file has a row below naming the endpoint or URL it came from and the date.
- Agents get a lookup task for every packaged list so they can form valid calls: one
  lookup task per list, `list_<thing>`, served as the MCP tool
  `usda_esr_list_<thing>`, or the upstream's own lookup operation when it serves
  every list through one; `/refresh-reference-data` adds the task where it is missing.
- A multi-tenant source packages no tenant data (ADR-0014), only lists that are the same
  for every tenant, if any.

| File | Origin | Fetched |
| --- | --- | --- |
| (none yet) | | |
