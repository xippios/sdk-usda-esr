- `xippios-usda-esr-mcp` names itself in its usage line and its errors, an unknown option
  ending `xippios-usda-esr-mcp: error: unrecognized arguments: --<option>`, where they
  named the server, `xippios-usda-esr`. Its help says that `--allow-remote` changes
  nothing, since this read server is not held to loopback, where it spoke of a write
  server. (https://github.com/xippios/sdk-core/issues/167)
