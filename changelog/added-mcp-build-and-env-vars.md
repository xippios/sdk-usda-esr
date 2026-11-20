- `xippios.usda.esr.mcp.build()` returns the read-only tool set that `xippios-usda-esr-mcp`
  serves, xippios-core's `ToolSet` with the caps of `tasks.MCP_CAPS`, so a host serves the
  same tools beside other sources' in one server. `ENV_VARS`, beside `SOURCE` in
  `xippios.usda.esr.mcp`, names the one variable the package reads, `DATA_GOV_API_KEY`,
  secret and required. (https://github.com/xippios/sdk-core/issues/245,
  https://github.com/xippios/sdk-template/issues/81)
