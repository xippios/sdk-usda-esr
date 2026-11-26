- `get_weekly_series` names its market years in `meta.notes`, each answered one with its count
  of rows in the order of the rows and each passed over for having no data in ESR: `Market
  years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows.` The counts tell
  apart the two rows of a week that straddles two market years, since a record states none.
  (https://github.com/xippios/sdk-core/issues/478, https://github.com/xippios/sdk-usda-esr/issues/23)
