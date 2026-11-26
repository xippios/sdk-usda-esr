- The arguments that identify a record stay positional in the order of upstream's path, and
  every filter and every argument of the package's own is keyword-only:
  `get_exports(104, 2024, country_code=1220)`, `get_weekly_series(104, 1220, start_year=2023,
  end_year=2024)`, `get_release_dates(since=...)`, `list_countries(region_id=11)` and
  `list_commodities(search="wheat")`, where 0.3.0 took the same values by position. Over MCP
  and HTTP nothing changes, since a tool and a route take their arguments by name.
  (https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-usda-esr/issues/68)
