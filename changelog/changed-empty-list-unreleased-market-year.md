- The docstrings of `get_exports`, `get_latest_week` and `get_top_destinations`, their MCP
  tools' descriptions, say that an empty list may be a market year ESR has not released
  yet as well as one without exports, since ESR answers both with an empty list and these
  tasks read no release list. `get_market_year` names a commodity's current market year.
  (https://github.com/xippios/sdk-usda-esr/issues/18)
