# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for USDA FAS Export Sales Reporting, empty task layer, MCP server and FastAPI router
  wired to it, test harness, CI, the nightly live tests and publishing.
- Upstream documentation snapshot of 2026-10-25 in `docs/upstream/`: the ESR part (seven
  `/api/esr/` operations) of the FAS Open Data Services portal's Swagger 2.0 document and
  of the API's own Swashbuckle document, with `FETCHED.md`; written by
  `scripts/refresh_upstream.py` (standard library only, no key), which also records the
  portal and Swagger UI shells, the ESR program page (403 to headless clients) and the
  ESR query URLs (404) without files.
