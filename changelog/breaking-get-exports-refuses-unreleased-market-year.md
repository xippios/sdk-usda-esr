- `get_exports` raises `NotFoundError` for a market year that ESR has not released, naming the
  commodity's current market year, where it answered the empty list that ESR gives a year
  without exports, so the empty list now means no exports alone. For a market year from the
  current calendar year on it reads the release list first, one request more, which core's
  response cache answers within its lifetime. Its refusal, as `get_weekly_series`' of a range
  past that year and either task's of a commodity that the release list lacks, says that the
  release list was read and no exports were requested.
  (sdk-core ADR-0054, https://github.com/xippios/sdk-usda-esr/issues/21,
  https://github.com/xippios/sdk-usda-esr/issues/84)
