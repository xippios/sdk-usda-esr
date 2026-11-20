"""``scripts/refresh_reference.py`` offline: its run, the requests it counts, ``--only``.

A run sends each request once and counts it, reads the quota left from the answers,
fetches every list before it writes one, and with ``--only`` fetches the lists it names
alone (sdk-template 0.4.0's note on the script). These tests replay the recorded answers
of the four list operations, write under ``tmp_path`` alone and replace the render, so
nothing in the package moves; the last one renders ``enums.py`` in memory.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx
from xippios.core import PackagedList, UpstreamError
from xippios.core.testing import load_fixture

from xippios.usda.esr._client import BASE_URL, client

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_reference.py"
PACKAGE_DIR = ROOT / "src" / "xippios" / "usda" / "esr"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
FIXTURES = Path(__file__).parent / "fixtures"
WRAPPERS = {
    "unitsOfMeasure": "get_units_of_measure",
    "commodities": "get_commodities",
    "countries": "get_countries",
    "regions": "get_regions",
}
"""Each packaged list's wrapper, the fixture directory of its recorded answer, in the order
a run fetches them: the id list, then the tables."""


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def recorded(name: str) -> list[dict[str, object]]:
    body: list[dict[str, object]] = json.loads(
        load_fixture(FIXTURES / WRAPPERS[name] / "all.json").response.body
    )
    return body


def files(reference: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(reference.iterdir())}


@pytest.fixture
def renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The packaged files copied under ``tmp_path``, the script pointed at them, and its
    render replaced by a record of the directory it would read: a test reads what a run
    writes, and nothing in the package moves."""
    reference = tmp_path / "reference"
    shutil.copytree(REFERENCE, reference)
    monkeypatch.setattr(script, "REFERENCE", reference)
    rendered: list[Path] = []
    monkeypatch.setattr(script, "render", lambda: rendered.append(script.REFERENCE))
    return rendered


def test_a_run_sends_each_list_once_then_writes_them(
    renders: list[Path],
    replay_fixture: Callable[[str, str], respx.Route],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Four requests, one per list, each answered as recorded; the count and the quota
    left that the last answer reported are printed after the fetches, then each file is
    written with upstream's records and ``enums.py`` rendered once."""
    routes = {name: replay_fixture(wrapper, "all") for name, wrapper in WRAPPERS.items()}
    script.refresh()
    assert {name: route.call_count for name, route in routes.items()} == dict.fromkeys(WRAPPERS, 1)
    (reference,) = renders
    for name in WRAPPERS:
        path = reference / f"{name}.json"
        packaged = PackagedList.model_validate_json(path.read_text(encoding="utf-8"))
        assert packaged.records == recorded(name), name
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "requests sent: 4; quota left: 990 (x-ratelimit-remaining)"
    assert lines[1:] == [
        "unitsOfMeasure.json: 5 records from ESRData_GetUnitsOfMeasure",
        "commodities.json: 44 records from ESRData_GetCommodities",
        "countries.json: 211 records from ESRData_GetCountries",
        "regions.json: 12 records from ESRData_GetRegions",
    ]


def test_a_failed_fetch_is_sent_once_and_writes_nothing(
    renders: list[Path],
    replay_fixture: Callable[[str, str], respx.Route],
    respx_mock: respx.MockRouter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NOT RECORDED: a bare 503 for the last list, a body of no shape upstream was seen to
    send, to show that the run leaves it to core (conventions §10). The client's retry
    policy would send it four times; the run sends it once, prints the count of a failed
    run too, writes no file and renders nothing, and the client's configuration is the
    package's again afterwards."""
    for name in ("unitsOfMeasure", "commodities", "countries"):
        replay_fixture(WRAPPERS[name], "all")
    failing = respx_mock.get(f"{BASE_URL}/api/esr/regions").mock(return_value=httpx.Response(503))
    configured = client.config
    assert configured.retry.max_attempts > 1
    before = files(script.REFERENCE)
    with pytest.raises(UpstreamError):
        script.refresh()
    assert failing.call_count == 1
    assert client.config is configured
    assert files(script.REFERENCE) == before
    assert renders == []
    assert capsys.readouterr().out == (
        "requests sent: 4; quota left: 991 (x-ratelimit-remaining)\n"
    )


def test_only_fetches_the_named_lists_and_keeps_every_other_file(
    renders: list[Path],
    replay_fixture: Callable[[str, str], respx.Route],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--only regions`` sends one request, writes ``regions.json`` and renders
    ``enums.py`` from every file; the other files keep their bytes."""
    before = files(script.REFERENCE)
    route = replay_fixture("get_regions", "all")
    script.main(["--only", "regions"])
    assert route.call_count == 1
    after = files(script.REFERENCE)
    assert {name for name in after if after[name] != before[name]} == {"regions.json"}
    assert renders == [script.REFERENCE]
    assert capsys.readouterr().out.splitlines()[0] == (
        "requests sent: 1; quota left: 990 (x-ratelimit-remaining)"
    )


def test_only_refuses_a_list_it_does_not_package_before_any_request(
    renders: list[Path], respx_mock: respx.MockRouter
) -> None:
    with pytest.raises(SystemExit, match=r"^--only: no list units, exports in unitsOfMeasure, "):
        script.refresh(["units", "regions", "exports"])
    assert not respx_mock.calls
    assert renders == []


def test_only_refuses_to_keep_a_list_that_is_not_packaged_before_any_request(
    renders: list[Path], respx_mock: respx.MockRouter
) -> None:
    """``--only`` keeps every other list's file, so each must be packaged already: with
    ``countries.json`` absent, ``--only regions`` stops before its keyed request."""
    (script.REFERENCE / "countries.json").unlink()
    before = files(script.REFERENCE)
    with pytest.raises(SystemExit, match=r"^countries is not packaged yet: run without --only$"):
        script.refresh(["regions"])
    assert not respx_mock.calls
    assert files(script.REFERENCE) == before
    assert renders == []


def test_only_and_render_only_exclude_each_other() -> None:
    with pytest.raises(SystemExit) as info:
        script.main(["--render-only", "--only", "regions"])
    assert info.value.code == 2


def test_render_writes_enums_py_as_committed() -> None:
    """``--render-only``'s text, formatted as the script formats it, is ``enums.py`` byte
    for byte: core's default class name for the id field ``unitId`` is ``UnitId``, the name
    the script's own line gave it (https://github.com/xippios/sdk-core/issues/95). The text
    goes through ruff on stdin with the repository's configuration; nothing is written."""
    text = script.module()
    for command in (["format"], ["check", "--fix", "--quiet", "--exit-zero"]):
        text = subprocess.run(
            [sys.executable, "-m", "ruff", *command, "--stdin-filename", str(ENUMS), "-"],
            input=text,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        ).stdout
    assert text == ENUMS.read_text(encoding="utf-8")
