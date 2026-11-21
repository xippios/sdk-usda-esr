- The `NotFoundError` and the `InvalidRequestError` that the client maps from ESR's own
  answers name the request by its method and its path, as xippios-core's
  `request_description` gives it, where they named the path alone. An empty 404 other
  than an exports path's empty market year reads
  `ESR has no data for GET <path> (HTTP 404 with an empty body)`, where it read
  `ESR has no data for <path> (HTTP 404 with an empty body)`, and the 400 for a path value
  that is not an integer starts `ESR refused GET <path> (HTTP 400: <message>)`, where it
  started `ESR refused <path> (HTTP 400: <message>)`. Neither error's class, source or any
  other attribute changes. (https://github.com/xippios/sdk-usda-esr/issues/49)
