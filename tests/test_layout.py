"""The namespace levels stay empty and the package ships its typing marker (ADR-0006)."""

from pathlib import Path

import xippios.usda.esr as package

PACKAGE_DIR = Path(package.__file__ or "").parent


def test_namespace_levels_have_no_init() -> None:
    levels = list(PACKAGE_DIR.parents)
    names = [level.name for level in levels]
    assert "xippios" in names, f"no xippios directory above {PACKAGE_DIR}; is it under src/?"
    for level in levels[: names.index("xippios") + 1]:
        assert not (level / "__init__.py").exists(), f"{level} must stay a namespace portion"


def test_py_typed_marker_ships() -> None:
    assert (PACKAGE_DIR / "py.typed").is_file()
