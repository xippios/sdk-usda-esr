#!/usr/bin/env bash
# Sibling proof for sdk-core ADR-0006: this package's wheel installs beside its siblings,
# the packages under the same provider namespace (xippios.usda.nass beside
# xippios.usda.psd), as portions of the PEP 420 namespaces between xippios and the package.
#
# sdk-template renders this file, and .github/workflows/siblings.yml that runs it, where
# the import path nests or the source declares a source package it depends on; copier
# update keeps both as the template's. The siblings are the repositories of the xippios
# organisation named sdk-<provider>-* whose distribution, xippios-<provider>-*, is on
# PyPI; uv installs the newest release of each that shares one xippios-core minor with
# this wheel. A sibling every release of which sits on another core minor is left out with
# a warning, never a failure, and so is a sibling that pins this package's previous minor,
# since it takes this minor in its own adoption; every other conflict fails. The script
# builds the wheel, installs it with the siblings into a fresh virtual environment, fails if
# a namespace level is a regular package (an __init__.py at xippios/ or
# xippios/<provider>/), imports every package under the provider namespace, checks that
# every tracked file of the package ships in the wheel and runs `uv pip check`. It calls
# nothing upstream. Needs the network, no key. Run from anywhere:
# .github/scripts/check-siblings.sh
#
# The source packages this one depends on (sdk-core ADR-0021), as pyproject.toml declares
# them (xippios-<slug>~=X.Y.0), install with the wheel from PyPI at their bound and import
# beside it, each namespace level above them a portion too. A declared dependency is never
# left out as a sibling on another core minor is: a conflict, another xippios-core minor
# included, fails the check, since both share one core minor. A flat source that declares
# one has no siblings to find, and the check proves the dependencies alone.
#
#   XIPPIOS_SIBLINGS  one requirement per line, replacing the discovered siblings: a
#                     sibling not on PyPI yet, from its checkout beside this repository or
#                     from git; set and empty, the wheel is installed alone
#   GITHUB_TOKEN      where set, authenticates the listing of the organisation's
#                     repositories (siblings.yml passes the job's read-only token); the
#                     listing alone sees it
#   PYTHON            the environment's Python version, 3.12 unless set
set -euo pipefail

# The token reaches the listing below and nothing else: uv build and the installs run the
# packages' code and never see it (conventions §13).
token="${GITHUB_TOKEN:-}"
unset GITHUB_TOKEN

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
unset VIRTUAL_ENV  # never install into whatever environment the shell has active
cd "$root"

# The distribution and the import path as copier recorded them (sdk-core ADR-0006).
answer() { sed -n "s/^$1: //p" .copier-answers.yml; }
slug="$(answer source_slug)"
import_path="$(answer import_path)"
if [ -z "$slug" ] || [ -z "$import_path" ]; then
  echo "error: .copier-answers.yml names no source_slug or import_path" >&2
  exit 1
fi
distribution="xippios-$slug"
package="xippios.$import_path"
provider="${import_path%%.*}"
# Repositories are named by slug, so an underscore of the import path is a hyphen there:
# world_bank.wdi lives in sdk-world-bank-wdi.
prefix="sdk-${provider//_/-}-"

uv venv --quiet --python "${PYTHON:-3.12}" "$work/venv"
python="$work/venv/bin/python"

# The source packages this one depends on, by distribution name: every xippios-* but core
# in [project] dependencies (sdk-core ADR-0021). The wheel requires them at their bound.
declared=()
names="$("$python" - <<'PY'
import re
import tomllib

with open("pyproject.toml", "rb") as file:
    requirements = tomllib.load(file).get("project", {}).get("dependencies", [])
for requirement in requirements:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    name = re.sub(r"[-_.]+", "-", match[1]).lower() if match else ""
    if name.startswith("xippios-") and name != "xippios-core":
        print(name)
PY
)"
while IFS= read -r line; do
  if [ -n "$line" ]; then
    declared+=("$line")
  fi
done <<< "$names"
if [ "${#declared[@]}" != 0 ]; then
  echo "declared dependencies, from pyproject.toml, installed with the wheel at their bound:"
  printf '  %s\n' "${declared[@]}"
fi

if [ -n "${XIPPIOS_SIBLINGS+set}" ]; then
  siblings="$XIPPIOS_SIBLINGS"
  echo "siblings from XIPPIOS_SIBLINGS"
elif [[ "$import_path" != *.* ]]; then
  siblings=""
  echo "no siblings: the import path is flat"
else
  siblings="$(GITHUB_TOKEN="$token" "$python" - "$prefix" "$distribution" <<'PY'
"""Print the siblings on PyPI: xippios-<provider>-* for each sdk-<provider>-* of xippios."""
import json
import os
import sys
import urllib.error
import urllib.request

prefix, own = sys.argv[1:]
agent = {"User-Agent": "xippios check-siblings (+https://github.com/xippios)"}
headers = {**agent, "Accept": "application/vnd.github+json"}
if os.environ.get("GITHUB_TOKEN"):
    headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
repositories: list[str] = []
page = 1
while True:
    url = f"https://api.github.com/orgs/xippios/repos?type=public&per_page=100&page={page}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as got:
        listed = json.load(got)
    repositories += [repo["name"] for repo in listed if not repo["archived"]]
    if len(listed) < 100:
        break
    page += 1
for name in sorted(repositories):
    distribution = "xippios-" + name.removeprefix("sdk-")
    if not name.startswith(prefix) or distribution == own:
        continue
    simple = urllib.request.Request(f"https://pypi.org/simple/{distribution}/", headers=agent)
    try:
        urllib.request.urlopen(simple, timeout=30).close()
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        print(f"{distribution}: not on PyPI yet, left out", file=sys.stderr)
        continue
    print(distribution)
PY
)"
  echo "siblings on PyPI, from the repositories ${prefix}* of xippios"
fi
requirements=()
while IFS= read -r line; do
  if [ -n "$line" ] && [[ " ${declared[*]} " == *" $line "* ]]; then
    echo "  $line: a declared dependency, installed with the wheel"
  elif [ -n "$line" ]; then
    requirements+=("$line")
    echo "  $line"
  fi
done <<< "$siblings"
if [ "${#requirements[@]}" = 0 ] && [ "${#declared[@]}" = 0 ]; then
  echo "  none: the wheel is installed alone"
elif [ "${#requirements[@]}" = 0 ]; then
  echo "  none beside the declared dependencies"
fi

# A development pin of core (conventions §12): while pyproject.toml takes xippios-core from
# git, the wheel needs core from that pin too, which its bound alone would not fetch.
core="$("$python" - <<'PY'
import tomllib

with open("pyproject.toml", "rb") as file:
    pin = tomllib.load(file).get("tool", {}).get("uv", {}).get("sources", {}).get("xippios-core")
if isinstance(pin, dict) and "git" in pin:
    ref = next((pin[key] for key in ("rev", "tag", "branch") if key in pin), None)
    print(f"xippios-core @ git+{pin['git']}" + (f"@{ref}" if ref else ""))
PY
)"
if [ -n "$core" ]; then
  echo "xippios-core from the git pin in pyproject.toml: $core"
fi

uv build --quiet --wheel --out-dir "$work/dist"
wheel=("$work"/dist/*.whl)
# The wheel installs first, with the source packages it depends on at their bound: a
# conflict there fails the check, a declared dependency on another core minor included.
if ! uv pip install --quiet --python "$python" "${wheel[@]}" ${core:+"$core"}; then
  echo "error: the wheel does not install${declared[*]:+ with its declared dependencies}" >&2
  exit 1
fi
own_core="$("$python" -c 'from importlib.metadata import version; print(version("xippios-core"))')"
own="$("$python" -c 'import sys, importlib.metadata as m; print(m.version(sys.argv[1]))' \
  "$distribution")"

minor() { local rest="${1#*.}"; echo "${1%%.*}.${rest%%.*}"; }
# The minor below a version's own, 0.1 for 0.2.3; none for a major's first minor.
previous_minor() {
  local rest="${1#*.}"
  local number="${rest%%.*}"
  if [ "$number" -gt 0 ]; then
    echo "${1%%.*}.$((number - 1))"
  fi
}
# The release of a distribution that the requirements given resolve to, on their own; fails
# when they do not resolve. A resolved version, read from uv's pinned output, never its errors.
resolved() {
  local name="$1" pinned
  shift
  pinned="$(printf '%s\n' "$@" | uv pip compile --quiet --no-header --no-annotate \
    --python "$python" - 2> /dev/null)" || return 1
  sed -n "s/^$name==//p" <<< "$pinned"
}

# A sibling every release of which sits on another xippios-core minor cannot install beside
# this wheel until one of the two adopts the other's minor (conventions §15): it is left out
# with a warning, so the proof stays with the siblings on this wheel's minor. It is told by
# resolved versions: on its own the sibling resolves to a core of another minor, and held to
# this wheel's minor it resolves to none.
# A sibling that depends on this package and pins its previous minor takes this minor in its
# own adoption, which follows this package's release (conventions §12): it is left out with
# a warning that names the pin, so the release of a new minor stays green. It is told by
# resolved versions too: on its own the sibling resolves to a release of this package's
# previous minor, and with its requirement on this package overridden by the wheel it
# installs, so the pin is its one conflict. Any other conflict fails the check.
printf '%s @ file://%s\n' "$distribution" "${wheel[0]}" > "$work/override.txt"
kept=()
for requirement in "${requirements[@]}"; do
  if trial="$(uv pip install --dry-run --python "$python" "${wheel[@]}" "$requirement" \
    ${core:+"$core"} 2>&1)"; then
    kept+=("$requirement")
    continue
  fi
  pinned="$(resolved "$distribution" "$requirement" || true)"
  alone="$(resolved xippios-core "$requirement" || true)"
  if [ -n "$pinned" ] && [ "$(minor "$pinned")" = "$(previous_minor "$own")" ] \
    && uv pip install --quiet --dry-run --python "$python" "${wheel[@]}" "$requirement" \
      ${core:+"$core"} --override "$work/override.txt" > /dev/null 2>&1; then
    echo "::warning::${requirement}: pins ${distribution} $(minor "$pinned").*, this wheel" \
      "${own}; left out until it adopts $(minor "$own") in its own package"
  elif [ -n "$alone" ] && [ "$(minor "$alone")" != "$(minor "$own_core")" ] \
    && ! resolved xippios-core "$requirement" "xippios-core==$(minor "$own_core").*" \
      > /dev/null; then
    echo "::warning::${requirement}: every release needs xippios-core $(minor "$alone").*, this" \
      "wheel $(minor "$own_core").*; left out until both share a minor"
  else
    echo "$trial" >&2
    echo "error: ${requirement} does not install beside this wheel" >&2
    exit 1
  fi
done
if [ "${#kept[@]}" != 0 ]; then
  uv pip install --python "$python" "${wheel[@]}" "${kept[@]}" ${core:+"$core"}
fi

"$python" - "$package" "${declared[@]}" <<'PY'
"""Every level above the package stays a namespace portion; every package under it imports,
and so does every source package it depends on, beside it (sdk-core ADR-0021)."""
import importlib
import pkgutil
import sys
from importlib.metadata import distribution, version

package, *declared = sys.argv[1:]


def portions(name: str) -> list[str]:
    """The namespace levels above a package, each required to be a portion."""
    levels = name.split(".")
    namespaces = [".".join(levels[:depth]) for depth in range(1, len(levels))]
    for level in namespaces:
        module = importlib.import_module(level)
        if getattr(module, "__file__", None) is not None:
            sys.exit(f"error: {level} is a regular package ({module.__file__}), not a portion")
    return namespaces


namespaces = portions(package)
names = [package]
if len(namespaces) > 1:
    provider = sys.modules[namespaces[-1]]
    found = pkgutil.iter_modules(provider.__path__, f"{provider.__name__}.")
    names = sorted(info.name for info in found if info.ispkg)
    if package not in names:
        sys.exit(f"error: {package} is not installed under {provider.__name__}")
for name in names:
    module = importlib.import_module(name)
    print(f"imported {name} {getattr(module, '__version__', '')}")
for dependency in declared:
    # Its package is the shallowest directory below xippios/ the distribution installs an
    # __init__.py in: xippios/usda/esmis/__init__.py for xippios-usda-esmis.
    inits = [
        file.parts[:-1]
        for file in distribution(dependency).files or []
        if file.parts[0] == "xippios" and file.name == "__init__.py" and len(file.parts) > 2
    ]
    if not inits:
        sys.exit(f"error: {dependency} installs no package under xippios")
    name = ".".join(min(inits, key=len))
    namespaces += [level for level in portions(name) if level not in namespaces]
    module = importlib.import_module(name)
    print(f"imported {name} {version(dependency)}, a declared dependency ({dependency})")
core = version("xippios-core")
print(f"ok: {' and '.join(namespaces)} stay namespace portions, on xippios-core {core}")
PY

site="$("$python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
missing=0
while IFS= read -r -d '' file; do
  if [ ! -e "$site/${file#src/}" ]; then
    echo "error: ${file#src/} is not in the wheel" >&2
    missing=1
  fi
done < <(git ls-files -z -- "src/${package//.//}")
if [ "$missing" != 0 ]; then
  exit 1
fi
echo "ok: every tracked file of src/${package//.//} ships in the wheel"
uv pip check --python "$python"
