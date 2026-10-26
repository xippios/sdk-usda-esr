#!/usr/bin/env bash
# Sibling proof for ADR-0006: xippios-usda-esr, xippios-usda-psd and xippios-usda-nass
# install side by side in one clean environment as portions of the PEP 420 namespaces
# xippios and xippios.usda.
#
# Builds this package's wheel, installs it with xippios-usda-psd and xippios-usda-nass
# into a fresh virtual environment, imports all three, runs `uv pip check`, and fails if
# either namespace level gained an __init__.py in site-packages. A namespace proof, not a
# runtime one: xippios-usda-psd 0.1.0 imports on core 0.2.0, its runtime fix for core 0.2.0
# comes with psd 0.2.0. Needs the network, no key. Run from anywhere:
# scripts/check-siblings.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
unset VIRTUAL_ENV  # never install into whatever environment the shell has active

# xippios-usda-psd is on PyPI. xippios-usda-nass is not yet, so it is pinned to a commit on
# its main, 727c9eb, which a new head there cannot change (Johannes, 2026-10-25): switch it
# to "xippios-usda-nass" from PyPI in /release-prep once nass 0.1.0 is published.
# PSD_REQUIREMENT and NASS_REQUIREMENT override either.
psd="${PSD_REQUIREMENT:-xippios-usda-psd}"
nass="${NASS_REQUIREMENT:-xippios-usda-nass @ git+https://github.com/xippios/sdk-usda-nass@727c9eb}"

cd "$root"
uv build --wheel --out-dir "$work/dist"
uv venv --python "${PYTHON:-3.12}" "$work/venv"
python="$work/venv/bin/python"
uv pip install --python "$python" "$work"/dist/*.whl "$psd" "$nass"

"$python" - <<'PY'
import xippios.usda.esr
import xippios.usda.nass
import xippios.usda.psd
from xippios.usda.esr.params import PACKAGED_LISTS, packaged_values

assert all(packaged_values(name) is not None for name in PACKAGED_LISTS), "reference data"
print(
    "imported xippios.usda.esr", xippios.usda.esr.__version__,
    "xippios.usda.nass", xippios.usda.nass.__version__,
    "xippios.usda.psd", xippios.usda.psd.__version__,
)
PY
uv pip check --python "$python"

site="$("$python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
for level in xippios xippios/usda; do
  if [ -e "$site/$level/__init__.py" ]; then
    echo "error: $site/$level/__init__.py exists; $level must stay a namespace portion" >&2
    exit 1
  fi
done
echo "ok: no __init__.py at xippios/ or xippios/usda/ in $site"
