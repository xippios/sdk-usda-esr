- `NoDataForYear`, raised for a market year ESR holds no data for, such as 1900, is
  xippios-core's `xippios.core.data_gov.NoDataForYear`, and `xippios.usda.esr.errors` is
  gone. The class is still a `NotFoundError` with `path`, the tasks' messages still name
  commodity, country and market year, and an `except NotFoundError` catches it as before.
  An endpoint wrapper of `api/` raises it with core's text, `no data for <path> (HTTP 404
  with an empty body): the year it names holds no data upstream`, where it read
  `ESR has no data for <path> (HTTP 404 with an empty body)`.
  (https://github.com/xippios/sdk-core/issues/106)
