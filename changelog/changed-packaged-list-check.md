- A code that is not an integer is refused in xippios-core's wording, `'104' is not an
  integer code: commodity_code takes the integer codes of the packaged commodities list
  (fetched 2026-10-28), such as 101 (Wheat - HRW). Nothing was sent. Pass it as the integer
  104.`, followed by the reason ESR's codes are checked, where it read `commodity_code must
  be an integer code such as 104 (Wheat - White), got '104'.`, its class
  `InvalidRequestError` kept. `list_countries(region_id=...)` refuses a region the packaged
  regions list lacks with `UnknownCode`, naming the closest ids, where it answered an empty
  list. (sdk-core ADR-0045, https://github.com/xippios/sdk-usda-esr/issues/27)
