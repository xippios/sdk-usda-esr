"""``README.md``'s scope against the snapshot in ``docs/upstream/openapi/``.

The README says in one paragraph what of ESR the package wraps and what it leaves out, and
names each choice that the snapshot documents and a caller of the package cannot make
(https://github.com/xippios/sdk-usda-esr/issues/62, part 8). The tests read the choices from
the portal's document, so a refresh that documents a new one fails here until a task takes it
or the README names it.
"""

import inspect
import json
import re
from pathlib import Path
from typing import Any

from xippios.usda.esr import tasks

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "upstream" / "openapi" / "portal-document.json"
JSON_TYPES = frozenset({"application/json", "text/json"})
"""The media types the package reads, the client's ``Accept: application/json`` among them."""


def operations() -> list[dict[str, Any]]:
    """The snapshot's operations, each as the portal's document states it."""
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    return [operation for methods in document["paths"].values() for operation in methods.values()]


def readme() -> str:
    return " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())


def arguments() -> set[str]:
    """Every argument of a task the package exports."""
    return {
        name
        for task in tasks.__all__
        for name in inspect.signature(getattr(tasks, task)).parameters
    }


def snake(name: str) -> str:
    """Upstream's camelCase name as the package spells it: ``commodityCode``, ``commodity_code``."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def test_every_documented_parameter_is_a_task_s_argument_or_named() -> None:
    """A parameter that the snapshot documents is an argument of a task, by its snake_case
    name, or the README names it by upstream's name as one a caller cannot set."""
    taken = arguments()
    documented = {
        parameter["name"]
        for operation in operations()
        for parameter in operation.get("parameters", [])
    }
    assert documented, "the exports operations take path parameters"
    not_taken = [name for name in sorted(documented) if snake(name) not in taken]
    text = readme()
    assert [name for name in not_taken if f"`{name}`" not in text] == []


def test_every_documented_format_but_json_is_named() -> None:
    """Each format that an operation produces besides JSON, which the package reads, is one
    a caller cannot ask for, and the README names it: ESR documents XML."""
    formats = {
        media.split("/")[1].upper()
        for operation in operations()
        for media in operation["produces"]
        if media not in JSON_TYPES
    }
    assert formats == {"XML"}
    text = readme()
    assert [name for name in sorted(formats) if name not in text] == []
