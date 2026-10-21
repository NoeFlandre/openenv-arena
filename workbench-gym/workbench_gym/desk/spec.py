# SPDX-License-Identifier: Apache-2.0

"""
Task contract and output grading for Workbench Desk.

A family builds a ``DeskTask``: input files, an instruction that names every
input and output path, and the outputs the grader checks. Outputs are files the
agent writes into its workspace: a JSON object, a CSV table or one plain value.

Grading reads each output file (a regular file of at most MAX_OUTPUT_BYTES, no
symlinks) and compares it with the expected content:

- 1.0 when every output is right.
- FORMAT_CREDIT when every output exists and has the asked shape (JSON keys and
  value types, CSV header and row count, a parseable value) but a value is wrong.
- 0.0 otherwise.
"""

import csv
import io
import json
import math
import os
import random
import re
import stat
from dataclasses import dataclass, field
from typing import Any

FORMAT_CREDIT = 0.1
MAX_OUTPUT_BYTES = 256 * 1024
CHECK_KINDS = frozenset({"int", "num", "text", "set", "list", "map", "bool"})


@dataclass(frozen=True)
class Check:
    """How one value is compared. ``tol`` and ``rel`` apply to numbers, in lists and maps too."""

    kind: str
    tol: float = 0.0
    rel: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in CHECK_KINDS:
            raise ValueError(f"unknown check kind: {self.kind}")


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _num_ok(check: Check, got: Any, want: Any) -> bool:
    if not _is_num(got):
        return False
    limit = max(check.tol, check.rel * abs(float(want)))
    return abs(float(got) - float(want)) <= limit + 1e-9


def _scalar_ok(check: Check, got: Any, want: Any) -> bool:
    if isinstance(want, bool):
        return got is want
    if _is_num(want):
        return _num_ok(check, got, want)
    return isinstance(got, str) and got.strip() == str(want).strip()


def _scalar_key(value: Any) -> str:
    if _is_num(value) and float(value).is_integer():
        return json.dumps(int(value))
    if isinstance(value, str):
        return json.dumps(value.strip())
    return json.dumps(value)


def value_ok(check: Check, got: Any, want: Any) -> bool:
    """True when ``got`` equals ``want`` under ``check``."""
    kind = check.kind
    if kind == "int":
        return _is_num(got) and float(got).is_integer() and int(got) == int(want)
    if kind == "num":
        return _num_ok(check, got, want)
    if kind == "text":
        return isinstance(got, str) and got.strip() == str(want).strip()
    if kind == "bool":
        return isinstance(got, bool) and got is bool(want)
    if kind == "set":
        if not isinstance(got, list) or len(got) != len(want):
            return False
        return sorted(map(_scalar_key, got)) == sorted(map(_scalar_key, want))
    if kind == "list":
        if not isinstance(got, list) or len(got) != len(want):
            return False
        return all(_scalar_ok(check, g, w) for g, w in zip(got, want, strict=True))
    if kind == "map":
        if not isinstance(got, dict):
            return False
        got_norm = {str(k).strip(): v for k, v in got.items()}
        if set(got_norm) != {str(k) for k in want}:
            return False
        return all(_scalar_ok(check, got_norm[str(k)], w) for k, w in want.items())
    raise ValueError(kind)


def shape_ok(check: Check, got: Any) -> bool:
    """True when ``got`` has the type ``check`` asks for, whatever its value."""
    kind = check.kind
    if kind in ("int", "num"):
        return _is_num(got)
    if kind == "text":
        return isinstance(got, str)
    if kind == "bool":
        return isinstance(got, bool)
    if kind in ("set", "list"):
        return isinstance(got, list)
    return isinstance(got, dict)


def _parse_cell(check: Check, cell: str) -> Any:
    """A CSV cell as the type the column asks for, or None when it does not parse."""
    text = cell.strip()
    if check.kind in ("int", "num"):
        try:
            value = float(text)
        except ValueError:
            return None
        return value if math.isfinite(value) else None
    return text


@dataclass(frozen=True)
class JsonOut:
    """A JSON object file. Extra keys are allowed; every key in ``checks`` must be right."""

    path: str
    checks: dict[str, Check]
    want: dict[str, Any]

    def grade(self, text: str) -> tuple[bool, bool]:
        try:
            got = json.loads(text)
        except ValueError:
            return False, False
        if not isinstance(got, dict):
            return False, False
        shape = all(name in got and shape_ok(c, got[name]) for name, c in self.checks.items())
        right = shape and all(
            value_ok(c, got[name], self.want[name]) for name, c in self.checks.items()
        )
        return shape, right


@dataclass(frozen=True)
class CsvOut:
    """A CSV file with an exact header. Rows match in order, or by ``key`` column when set."""

    path: str
    header: tuple[str, ...]
    columns: tuple[Check, ...]
    rows: tuple[tuple[Any, ...], ...]
    key: int | None = None

    def grade(self, text: str) -> tuple[bool, bool]:
        lines = [row for row in csv.reader(io.StringIO(text.lstrip("﻿"))) if row]
        if not lines or tuple(c.strip() for c in lines[0]) != self.header:
            return False, False
        body = lines[1:]
        if len(body) != len(self.rows) or any(len(r) != len(self.header) for r in body):
            return False, False
        parsed = [
            tuple(_parse_cell(c, x) for c, x in zip(self.columns, r, strict=True)) for r in body
        ]
        if any(v is None for r in parsed for v in r):
            return False, False
        if self.key is None:
            pairs = list(zip(parsed, self.rows, strict=True))
        else:
            k = self.key
            by_key = {str(r[k]).strip(): r for r in parsed}
            if len(by_key) != len(parsed):
                return True, False
            pairs = []
            for want in self.rows:
                got = by_key.get(str(want[k]).strip())
                if got is None:
                    return True, False
                pairs.append((got, want))
        right = all(
            all(_scalar_ok(c, g, w) for c, g, w in zip(self.columns, got, want, strict=True))
            for got, want in pairs
        )
        return True, right


@dataclass(frozen=True)
class TextOut:
    """A file holding one value: a number, an integer or a line of text."""

    path: str
    check: Check
    want: Any

    def grade(self, text: str) -> tuple[bool, bool]:
        value = _parse_cell(self.check, text)
        if value is None or (self.check.kind == "text" and not value):
            return False, False
        return True, value_ok(self.check, value, self.want)


Output = JsonOut | CsvOut | TextOut


@dataclass
class DeskTask:
    """One task instance. ``instruction`` writes the workspace directory as ``{root}``."""

    instruction: str
    files: dict[str, str | bytes]
    outputs: list[Output]
    oracle: dict[str, str]
    decoys: list[dict[str, str]] = field(default_factory=list)

    def text(self, root: str) -> str:
        return self.instruction.replace("{root}", root)


class DeskFamily:
    """One task type. ``build`` makes an instance; ``solve`` re-derives its outputs from files."""

    id: str = ""
    domain: str = ""
    title: str = ""
    levels: tuple[int, ...] = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        raise NotImplementedError

    def solve(self, files: dict[str, str | bytes], instruction: str) -> dict[str, str]:
        raise NotImplementedError


def read_output(workdir: str, relpath: str) -> str | None:
    """The text of an output file, or None when it is missing, too big or not a regular file."""
    path = os.path.join(workdir, relpath)
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OUTPUT_BYTES:
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(MAX_OUTPUT_BYTES)
    except OSError:
        return None


def grade_texts(outputs: list[Output], texts: dict[str, str | None]) -> tuple[float, str]:
    """Reward for output texts keyed by path, with a short note for the agent."""
    shapes, rights = [], []
    for out in outputs:
        text = texts.get(out.path)
        if text is None:
            return 0.0, f"{out.path} is missing"
        shape, right = out.grade(text)
        shapes.append(shape)
        rights.append(right)
    if all(rights):
        return 1.0, "all outputs are correct"
    if all(shapes):
        return FORMAT_CREDIT, "the outputs have the right shape but some values are wrong"
    return 0.0, "an output does not have the asked format"


def grade_workdir(outputs: list[Output], workdir: str) -> tuple[float, str]:
    return grade_texts(outputs, {o.path: read_output(workdir, o.path) for o in outputs})


def must_match(pattern: str, text: str, flags: int = 0) -> re.Match[str]:
    """Search ``text`` for ``pattern``. A missing match is a bug in the family, so raise."""
    match = re.search(pattern, text, flags)
    if match is None:
        raise ValueError(f"no match for {pattern!r}")
    return match


def money(value: float) -> float:
    """Round half up to the cent, as accountants do (0.005 -> 0.01)."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(repr(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
