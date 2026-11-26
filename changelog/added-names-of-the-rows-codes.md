- The answers of `get_exports` and `get_weekly_series` name the country asked for and the
  countries and the units of their rows in `meta.names`, `{"country_code": {"1220": "CANADA"}, "unit_id": {"1": "Metric
  Tons"}}`, by the packaged lists, and `list_commodities` names its units alike. A row's code
  that the packaged list lacks is left out of the names and said in `meta.notes`, so no
  answer is withheld for it.
  (https://github.com/xippios/sdk-core/issues/478, https://github.com/xippios/sdk-usda-esr/issues/30)
