"""``README.md``'s scope against the snapshot in ``docs/upstream/openapi/``.

The README's ``## Scope`` says what of ESR the package wraps and what it leaves out, and
names, in a sentence on what a caller cannot set or make, each choice that the snapshot
documents and a caller of the package cannot make (conventions §2;
https://github.com/xippios/sdk-usda-esr/issues/62, part 8). The tests read the choices from
the portal's document, so a refresh that documents a new one fails here until a task takes it
or that sentence names it.
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


def readme() -> list[str]:
    return (ROOT / "README.md").read_text(encoding="utf-8").splitlines()


def cannot() -> list[str]:
    """The sentences of the README's ``## Scope`` that say what a caller cannot set or make."""
    lines = readme()
    start = lines.index("## Scope") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("## "))
    text = " ".join(" ".join(lines[start:end]).split())
    return [sentence for sentence in re.split(r"(?<=\.) ", text) if "cannot" in sentence]


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


def documented() -> list[str]:
    """Every parameter that an operation of the snapshot documents, by upstream's name."""
    return sorted(
        {
            parameter["name"]
            for operation in operations()
            for parameter in operation.get("parameters", [])
        }
    )


def unnamed(taken: set[str]) -> list[str]:
    """The documented parameters that no task takes in ``taken`` and no sentence of the
    README's ``## Scope`` on what a caller cannot set names."""
    not_taken = [name for name in documented() if snake(name) not in taken]
    named = " ".join(cannot())
    return [name for name in not_taken if f"`{name}`" not in named]


def test_every_documented_parameter_is_a_task_s_argument_or_named() -> None:
    """A parameter that the snapshot documents is an argument of a task, by its snake_case
    name, or the README names it by upstream's name as one a caller cannot set."""
    assert documented(), "the exports operations take path parameters"
    assert unnamed(arguments()) == []


def test_a_parameter_that_no_task_takes_is_held_to_the_readme_s_word() -> None:
    """Were ``country_code`` no argument of a task, ``countryCode`` would be a documented
    parameter that a caller cannot set, and the README, which names it among those the tasks
    take, would not say so: the check finds it."""
    assert unnamed(arguments() - {"country_code"}) == ["countryCode"]


def test_the_scope_stands_under_its_heading_after_the_introduction() -> None:
    """``## Scope`` is the README's first section, before ``## Install``: what the package
    wraps comes first in the family's order of a README (conventions §13), and the README's
    ``## Scope`` is where a documented parameter that a caller cannot set is named
    (conventions §2)."""
    headings = [line for line in readme() if line[:3] == "## "]
    assert headings[:2] == ["## Scope", "## Install"]


def test_every_documented_format_but_json_is_named() -> None:
    """Each format that an operation produces besides JSON, which the package reads, is one
    a caller cannot ask for, and the README's sentence on what a caller cannot make names it:
    ESR documents XML."""
    formats = {
        media.split("/")[1].upper()
        for operation in operations()
        for media in operation["produces"]
        if media not in JSON_TYPES
    }
    assert formats == {"XML"}
    named = " ".join(cannot())
    assert [name for name in sorted(formats) if name not in named] == []


def test_each_choice_a_caller_cannot_make_cites_its_public_issue() -> None:
    """A documented choice that a caller cannot make stands while the README's ``## Scope``
    names it with its public issue (conventions §2; sdk-core ADR-0060, decision 8), so each
    sentence of the scope on what a caller cannot set or make cites an issue of this
    repository: XML's is https://github.com/xippios/sdk-usda-esr/issues/82."""
    issue = re.compile(r"https://github\.com/xippios/sdk-usda-esr/issues/\d+")
    sentences = cannot()
    assert sentences, "the scope says what a caller cannot set or make"
    assert [sentence for sentence in sentences if not issue.search(sentence)] == []
