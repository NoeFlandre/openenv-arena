# SPDX-License-Identifier: Apache-2.0

"""
Family registry for Workbench Desk. Each module named here defines ``FAMILY``.
A module that does not exist yet is skipped.

Task ids are ``<family>-L<level>``, for example ``fin4-L2``.
"""

import importlib
import re

from ..spec import DeskFamily

FAMILY_MODULES = [
    # finance-economics
    "fin4",
    "fin5",
    "fin6",
    "fin7",
    "fin8",
    "fin9",
    "fin10",
    "fin11",
    "fin12",
    # natural-science
    "sci4",
    "sci5",
    "sci6",
    "sci7",
    "sci8",
    "sci9",
    "sci10",
    "sci11",
    # mathematics-or-formal-reasoning
    "math4",
    "math5",
    "math6",
    # media-content-production
    "med4",
    "med5",
    "med6",
    # office-white-collar
    "off4",
    "off5",
    # industrial-physical-systems
    "ind4",
    "ind5",
    # software-engineering
    "sw4",
    "sw5",
    # cybersecurity
    "sec4",
    "sec5",
]

DOMAIN_IDS = {
    "software-engineering",
    "industrial-physical-systems",
    "natural-science",
    "office-white-collar",
    "finance-economics",
    "mathematics-or-formal-reasoning",
    "cybersecurity",
    "media-content-production",
}

_TASK_RE = re.compile(r"^([a-z]{2,4}[0-9]{1,2})-L([1-3])$")


def parse_task_id(task_id: str) -> tuple[str, int]:
    """Split ``fin4-L2`` into ``("fin4", 2)``. Raises ValueError for anything else."""
    match = _TASK_RE.match(task_id or "")
    if not match:
        raise ValueError(f"unknown task_id: {task_id!r}")
    return match.group(1), int(match.group(2))


def load_families() -> dict[str, DeskFamily]:
    families: dict[str, DeskFamily] = {}
    for name in FAMILY_MODULES:
        try:
            module = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as exc:
            # A family still being written is skipped; test_desk checks that all exist.
            if exc.name == f"{__name__}.{name}":
                continue
            raise
        family = module.FAMILY
        if family.id != name:
            raise ValueError(f"module {name} defines family {family.id}")
        if family.domain not in DOMAIN_IDS:
            raise ValueError(f"family {name} has unknown domain {family.domain}")
        families[family.id] = family
    return families
