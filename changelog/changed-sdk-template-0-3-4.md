- Adopts sdk-template v0.3.4, from v0.3.1, with conventions 1.27 and no new core minor: the
  floor stays `xippios-core~=0.3.0`. The README lists the package's documents under
  `## Documents`, and `CLAUDE.md` holds the rules that `.claude/family.md` carried, which
  leaves with `/adopt-release`, citing sdk-core's decision records as `sdk-core ADR-NNNN`.
  Changelog entries are fragments under `changelog/`, the package's own decisions go into
  `docs/adr/` with the index that `scripts/adr_index.py` writes, and a pull request runs the
  organization's checks from `organization.yml`, where `gates.yml` was.
  (https://github.com/xippios/sdk-template/releases/tag/v0.3.4,
  https://github.com/xippios/sdk-usda-esr/issues/15)
