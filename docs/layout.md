# Layout

The files that every source of the family holds are laid out once, in the tree of
sdk-template's README,
[What gets generated](https://github.com/xippios/sdk-template/blob/main/README.md#what-gets-generated).
This file holds what `xippios-usda-esr` adds to that tree, a module, a task file, a
script or a test of its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.usda.esr` (sdk-core ADR-0006); `src/xippios/` is a
namespace package, and so is `src/xippios/usda/`, the provider level.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this file says so (conventions §2).

```
src/xippios/usda/esr/
  _client.py       also DATA_PATH, the two exports paths, and the gateway of
                   xippios.usda.fas, whose policy keeps the key's quota
  api/             one module per upstream operation, named after it in snake case without
                   the ESRData_ prefix: get_commodities, get_countries, get_regions,
                   get_units_of_measure, get_data_release_info, get_country_data and
                   get_all_countries_data; each returns core's Answer
  params.py        also COMMODITIES, COUNTRIES, REGIONS and UNITS, the packaged lists that a
                   check or a name reads, and the market year's checks
  enums.py         IntEnum UnitId from the packaged unitsOfMeasure; never edited by hand
  reference/       commodities, countries, regions and unitsOfMeasure as packaged
tests/
  test_lists.py    the list tasks answer the recorded lists from the package, without a call
  test_series.py   the weekly series replays the recorded exports answers: order only
  test_api.py      replay tests for the endpoint wrappers
  test_client.py   wiring, classify on recorded error bodies, the gateway's quota policy on
                   a 429, core's response cache
  test_params.py   packaged lists, the enum, the code and year checks, the reference script
  test_refresh_upstream.py  the snapshot script's own pages, notes and paragraph on the
                   kit of the FAS portal, offline
  test_observed.py docs/upstream/OBSERVED.md as committed: each note's probe, its files
  test_readme.py   README.md's scope against the snapshot: each documented parameter a
                   task takes or the README names, and each format besides JSON named
docs/
  upstream/        also OBSERVED.md, the notes by hand on what ESR does but never documents,
                   and openapi/, the ESR parts of the portal's and the backend's documents
```
