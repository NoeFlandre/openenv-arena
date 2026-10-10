# SPDX-License-Identifier: Apache-2.0

"""
Answer grading. Pure functions, no I/O, never runs agent code.

An answer is a JSON object with one key per field. A field is exact unless its
kind allows a tolerance. Reward:

- 0.0 when the answer is not a non-empty object, is over MAX_ANSWER_CHARS, or
  has no correct field.
- 1.0 when every field is correct (the solved state).
- Otherwise 0.05 + 0.45 * (correct fields / fields), rounded to 3 places. It is
  always below 0.5, so partial credit never ranks above a solve.
"""

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

MAX_ANSWER_CHARS = 300
KINDS = frozenset({"int", "number", "text", "set", "fraction", "object"})
# Plain p/q or integer text only. Fraction() on an exponent such as 1e20 hangs the server.
_FRACTION_RE = re.compile(r"^-?[0-9]{1,15}(/[0-9]{1,15})?$")


@dataclass(frozen=True)
class Field:
    """One answer field. ``kind`` picks the comparison; tolerances apply to ``number``."""

    kind: str
    abs_tol: float = 0.0
    rel_tol: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown field kind: {self.kind}")


def canon(value: Any) -> Any:
    """Canonical form for ``object`` fields. Dict keys sort. Scalar lists are unordered.

    Integral floats become ints, so 1.0 equals 1.
    """
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        items = [canon(v) for v in value]
        if all(not isinstance(i, (dict, list)) for i in items):
            return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
        return items
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _is_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _set_key(items: Any) -> frozenset[str]:
    return frozenset(json.dumps(canon(i), sort_keys=True) for i in items)


def field_ok(spec: Field, got: Any, want: Any) -> bool:
    """True when ``got`` answers the field exactly, within the field's tolerance."""
    if got is None:
        return False
    if spec.kind == "int":
        return _is_int(got) and int(got) == int(want)
    if spec.kind == "number":
        if not _is_num(got):
            return False
        tol = max(spec.abs_tol, spec.rel_tol * abs(float(want)))
        return abs(float(got) - float(want)) <= tol + 1e-12
    if spec.kind == "text":
        return isinstance(got, str) and got.strip() == str(want).strip()
    if spec.kind == "set":
        return isinstance(got, list) and _set_key(got) == _set_key(want)
    if spec.kind == "fraction":
        if not isinstance(got, str) or not _FRACTION_RE.match(got.strip()):
            return False
        try:
            return Fraction(got.strip()) == Fraction(str(want))
        except (ValueError, ZeroDivisionError):
            return False
    if spec.kind == "object":
        return isinstance(got, dict) and canon(got) == canon(want)
    raise ValueError(spec.kind)


def answer_size(answer: Any) -> int:
    return len(json.dumps(answer, separators=(",", ":"), ensure_ascii=False))


def score_answer(answer: Any, fields: dict[str, Field], want: dict[str, Any]) -> float:
    """Reward for a submitted answer. See the module docstring for the rule."""
    if not isinstance(answer, dict) or not answer:
        return 0.0
    if answer_size(answer) > MAX_ANSWER_CHARS:
        return 0.0
    correct = sum(
        1 for name, spec in fields.items() if field_ok(spec, answer.get(name), want[name])
    )
    if correct == 0:
        return 0.0
    if correct == len(fields):
        return 1.0
    return round(0.05 + 0.45 * correct / len(fields), 3)
