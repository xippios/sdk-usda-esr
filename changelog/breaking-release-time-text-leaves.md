- `DataReleaseInfo.release_time_stamp_text` leaves: `release_time_stamp` is the one reading of
  `releaseTimeStamp`, a naive `datetime` that keeps upstream's fraction of a second, and a
  record equals one built from its values. `meta.vintage` of `get_release_dates` still holds
  the newest release as upstream prints it, `"2026-10-22T08:30:42.67"`.
  (https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-usda-esr/issues/69)
