- `get_market_year` leaves, with its MCP tool and its route, and `get_release_dates` takes
  `commodity_code`, which keeps that commodity's record, its current market year, after the
  one request: `get_release_dates(commodity_code=104).data` in place of
  `get_market_year(104).data`, a list of one record, empty where the release list lacks the
  commodity, where `get_market_year` raised `NotFoundError`.
  (https://github.com/xippios/sdk-core/issues/474, https://github.com/xippios/sdk-usda-esr/issues/64)
