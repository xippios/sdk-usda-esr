- The answers of `get_exports` and `get_weekly_series` name the commodity and the country asked
  for and the commodities, countries and units of their rows in `meta.names`,
  `{"commodity_code": {"104": "Wheat - White"}, "country_code": {"1220": "CANADA"}, "unit_id":
  {"1": "Metric Tons"}}`, by the packaged lists, `get_release_dates` names its commodities and
  the one asked for, `list_commodities` its units and `list_countries` its regions and the one
  asked for. A row's code that the packaged list lacks is left out of the names and said in
  `meta.notes`, so no answer is withheld for it.
  (sdk-core ADR-0067, https://github.com/xippios/sdk-usda-esr/issues/30,
  https://github.com/xippios/sdk-usda-esr/issues/85)
