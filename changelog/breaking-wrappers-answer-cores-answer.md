- The endpoint wrappers under `api/` return core's `Answer`, the parsed answer as its
  `payload` beside the time it was retrieved as its `retrieved_at`, where they returned the
  parsed answer itself, so a caller of `api.get_commodities()` or another wrapper reads its
  `.payload`. That of `api.get_data_release_info()` is the `ReleaseList`.
  (https://github.com/xippios/sdk-core/issues/479)
