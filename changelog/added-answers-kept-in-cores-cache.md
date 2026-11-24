- The answers are kept in core's response cache for 300 s, every path alike, so a second
  read of the release list, of an exports answer or of a market year of the series within
  that time sends no request, and `meta.retrieved_at` is the client's time of the answer, the
  time its entry was stored for a cached one and the oldest where `get_weekly_series`
  assembles several. (https://github.com/xippios/sdk-core/issues/479,
  https://github.com/xippios/sdk-usda-esr/issues/65)
