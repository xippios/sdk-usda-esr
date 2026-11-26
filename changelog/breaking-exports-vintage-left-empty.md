- `get_exports` and `get_weekly_series` leave `meta.vintage` empty, where it held the newest
  `week_ending_date` of the rows, since an exports answer states no release of its own. The
  newest week is the last row's `week_ending_date`, and `get_release_dates` gives the
  commodity's last release. (https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-usda-esr/issues/67)
