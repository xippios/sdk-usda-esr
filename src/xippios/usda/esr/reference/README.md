# Reference data for USDA FAS Export Sales Reporting

Lists and tables the upstream publishes for every caller alike, shipped with the package
(conventions §3): each `reference/<name>.json` holds `{"param", "endpoint", "fetched",
"records"}` and an optional `"note"`, upstream's records under upstream's field names,
written by `/refresh-reference-data`'s script with `PackagedList.write`, never by hand,
and read with `PackagedList.load`. One row per file: Origin is the endpoint or URL it was
fetched from, or the `docs/upstream/` file it was rebuilt from; Fetched is the UTC time
of that fetch, or the snapshot's `Fetched` time for a rebuilt file.

ESR's four code lists are records, kept in upstream order with upstream's padding
(`countryName` and `countryDescription` are padded with spaces upstream), codes and ids
integers as upstream sends them. `unitsOfMeasure`, a list of integer ids, makes
`enums.UnitId`; the commodity, country and region codes stay tables. The `list_*` tasks
answer from these files without an upstream call, and `get_exports` checks its codes
against them. The nightly live tests compare each packaged list with the live one
(`test_packaged_list_equals_the_live_list` in `tests/test_live.py`, one keyed call per
list) and name the records that are gone and those that are new: the signal to run
`/refresh-reference-data`.

| File | Origin | Fetched (UTC) | Records |
| --- | --- | --- | --- |
| `commodities.json` | `GET https://api.fas.usda.gov/api/esr/commodities` (`ESRData_GetCommodities`) | 2026-10-25 | 44 |
| `countries.json` | `GET https://api.fas.usda.gov/api/esr/countries` (`ESRData_GetCountries`) | 2026-10-25 | 211 |
| `regions.json` | `GET https://api.fas.usda.gov/api/esr/regions` (`ESRData_GetRegions`) | 2026-10-25 | 12 |
| `unitsOfMeasure.json` | `GET https://api.fas.usda.gov/api/esr/unitsOfMeasure` (`ESRData_GetUnitsOfMeasure`) | 2026-10-25 | 5 |

The 2026-10-25 files were written by `scripts/refresh_reference.py` against the live API
at about 20:39 UTC, ten minutes after the same four lists were recorded under
`tests/fixtures/<operation>/all.json`; the records are equal to the recorded ones, which
`tests/test_params.py` checks. Their `fetched` is the bare date the script then wrote,
which `PackagedList.load` reads as 00:00 UTC of that day (so the list tasks'
`meta.retrieved_at`) until the next refresh writes the full time.
