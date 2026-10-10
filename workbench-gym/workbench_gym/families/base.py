# SPDX-License-Identifier: Apache-2.0

"""
Family contract. A family is one task type with three difficulty levels.

``build(level, rng)`` makes a fresh instance: the files the agent may read, the
question, the answer fields, the correct answer, and at least three plausible
wrong answers (decoys). The correct answer comes from how the instance was
built. ``solve(files, question)`` is an independent reference solver that reads
only the text. The gates check that the two agree on every seed.
"""

import random
import re
from dataclasses import dataclass, field
from typing import Any

from ..core.grading import Field


@dataclass
class Built:
    question: str
    files: dict[str, str]
    fields: dict[str, Field]
    answer: dict[str, Any]
    decoys: list[dict[str, Any]] = field(default_factory=list)


class Family:
    id: str = ""
    domain: str = ""
    title: str = ""
    levels: tuple[int, ...] = (1, 2, 3)

    def build(self, level: int, rng: random.Random) -> Built:
        raise NotImplementedError

    def solve(self, files: dict[str, str], question: str) -> dict[str, Any]:
        raise NotImplementedError


def must_match(pattern: str, text: str, flags: int = 0) -> re.Match[str]:
    """Search ``text`` for ``pattern``. A missing match is a bug in the family, so raise."""
    match = re.search(pattern, text, flags)
    if match is None:
        raise ValueError(f"no match for {pattern!r}")
    return match
