# Reference data for USDA FAS Export Sales Reporting

The four code lists ESR publishes ship here as JSON, versioned with the package, and
load through `xippios.usda.esr.params` (built on `xippios.core.reference`):

```python
from xippios.usda.esr.params import packaged_values

packaged_values("commodities").records  # [{"commodityCode": 101, ...}, ...], no network call
```

Each file holds upstream's records verbatim, under upstream's field names and in
upstream order, padding included (`countryName` and `countryDescription` are padded with
spaces upstream), plus the list name (`param`, as the upstream path names it), the
operation it came from (`endpoint`) and the UTC fetch date (`fetched`). Codes and ids are
integers, as upstream sends them.

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py` with `xippios.core.reference`: one `StrEnum` per value list
  (`render_str_enums`), or one `IntEnum` per list of integer ids (`render_int_enums`).
  ESR's one id list is `unitsOfMeasure`, which makes `UnitId`; commodity, country and
  region codes stay tables, not enums.
- Files keep upstream's names: a file is named as the upstream path names its list, and
  a table and a list of integer ids alike hold their records under upstream's field
  names (`unitNames` is plural upstream and stays so).
- Every file has a row below naming the endpoint it came from, the date and the count.
- A multi-tenant source packages no tenant data (ADR-0014); ESR is single-tenant, every
  list is the same for every caller of the api.data.gov key.
- Agents get a lookup task for every packaged list so they can form valid calls: one
  lookup task per list, `list_<thing>`, served as the MCP tool `usda_esr_list_<thing>`,
  or the upstream's own lookup operation when it serves every list through one. ESR
  serves each list through an operation of its own, so each gets its task; they come in
  the next PR (`list_commodities`, `list_countries`, `list_regions`,
  `list_units_of_measure`) and answer from these files without an upstream call. Until
  then `get_exports` checks its codes against these files and names the closest ones.
- Refresh policy: `/refresh-reference-data` inside `/release-prep`, and whenever a
  validation failure names a code the package lacks.

| File | Origin | Fetched (UTC) | Records |
| --- | --- | --- | --- |
| `commodities.json` | `GET https://api.fas.usda.gov/api/esr/commodities` (`ESRData_GetCommodities`) | 2026-10-25 | 44 |
| `countries.json` | `GET https://api.fas.usda.gov/api/esr/countries` (`ESRData_GetCountries`) | 2026-10-25 | 211 |
| `regions.json` | `GET https://api.fas.usda.gov/api/esr/regions` (`ESRData_GetRegions`) | 2026-10-25 | 12 |
| `unitsOfMeasure.json` | `GET https://api.fas.usda.gov/api/esr/unitsOfMeasure` (`ESRData_GetUnitsOfMeasure`) | 2026-10-25 | 5 |

The 2026-10-25 files were written by `scripts/refresh_reference.py` against the live API
at about 20:39 UTC, ten minutes after the same four lists were recorded under
`tests/fixtures/<operation>/all.json`; the records are equal to the recorded ones, which
`tests/test_params.py` checks.
