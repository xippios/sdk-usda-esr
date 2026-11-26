- `get_weekly_series` refuses a range over its ceiling of 10 market years in xippios-core's
  wording, which names the range and the ceiling and says that nothing was sent, followed by
  the range to ask for as before, its class `InvalidRequestError` kept. A request after the
  first market year that fails raises its error, its class kept, naming the market years
  answered before it and that the series returns nothing. (sdk-core ADR-0054,
  https://github.com/xippios/sdk-usda-esr/issues/29)
