- `get_top_destinations` and `get_latest_week` leave, with their MCP tools, their routes and
  `models.ExportField`, by the boundary of a source package: a task that ranks or picks the
  newest week for the caller is not the package's. A caller reads the same records from
  `get_exports` and ranks or picks them itself. (https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-usda-esr/issues/63)
