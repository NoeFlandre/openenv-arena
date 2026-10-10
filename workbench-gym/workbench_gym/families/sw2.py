# SPDX-License-Identifier: Apache-2.0

"""
sw2: snippet output (software engineering).

``snippet.py`` is a short script from a bug report. Two traps decide its
output. A mutable default argument is one list shared by every call that
leaves the argument out. A module-level name shadows a builtin: ``max`` is an
int there, so ``max(vals)`` raises TypeError and the except branch runs. The
answer is the single line the script prints. The reference solver runs the
file, so the answer is what Python prints, not what a reader expects.
"""

import contextlib
import io
import random

from ..core.grading import Field
from .base import Built, Family

LINES = {1: 10, 2: 25, 3: 40}
QUESTION = (
    "snippet.py is a short script from bug report 4812. What single line does it print "
    "when run with python3? Give that exact line as output."
)
HELPERS = [
    "normalize",
    "to_cents",
    "label_row",
    "split_sku",
    "clamp_qty",
    "tidy_name",
    "rows_by_day",
    "fmt_total",
    "parse_id",
    "dedupe",
    "pick_rate",
    "round_pair",
]
NOTES = [
    "# keep in sync with the billing export",
    "# old layout, not used since the March cut",
    "# TODO: move to the shared helpers module",
    "# see ticket 4790 before touching this",
]


def _filler(count: int, rng: random.Random) -> list[str]:
    lines: list[str] = []
    names = rng.sample(HELPERS, len(HELPERS))
    k = 0
    while len(lines) < count:
        left = count - len(lines)
        if left >= 2 and rng.random() < 0.6:
            k += 1
            name = names[k % len(names)]
            lines.append(f"def {name}_{k}(x):")
            lines.append("    return str(x).strip()")
        else:
            lines.append(rng.choice(NOTES))
    return lines


def _core(vals: list[int], limit: int) -> list[str]:
    return [
        "def push(item, bucket=[]):",
        "    bucket.append(item)",
        "    return len(bucket)",
        "mine = []",
        f"vals = [{', '.join(str(v) for v in vals)}]",
        "out = [push(v, mine) if v % 2 == 0 else push(v) for v in vals]",
        f"max = {limit}",
        "try: out.append(max(vals))",
        "except TypeError: out.append(-1)",
        'print(",".join(map(str, out)))',
    ]


def _push_result(bucket: list[int], item: int, count_before: bool) -> int:
    before = len(bucket)
    bucket.append(item)
    return before if count_before else len(bucket)


def _output(
    vals: list[int], fresh_default=False, fresh_explicit=False, count_before=False, real_max=False
) -> str:
    default: list[int] = []
    mine: list[int] = []
    out: list[int] = []
    for v in vals:
        if v % 2 == 0:
            bucket = [] if fresh_explicit else mine
        else:
            bucket = [] if fresh_default else default
        out.append(_push_result(bucket, v, count_before))
    out.append(max(vals) if real_max else -1)
    return ",".join(str(x) for x in out)


class SnippetOutput(Family):
    id = "sw2"
    domain = "software-engineering"
    title = "Snippet output"

    def build(self, level: int, rng: random.Random) -> Built:
        while True:
            vals = [rng.randint(1, 99) for _ in range(rng.randint(4, 8))]
            odd = sum(v % 2 for v in vals)
            if 2 <= odd <= len(vals) - 2:
                break
        limit = rng.randint(2, 9)
        lines = _filler(LINES[level] - 10, rng) + _core(vals, limit)
        answer = _output(vals)
        decoys = [
            {"output": _output(vals, fresh_default=True)},
            {"output": _output(vals, fresh_explicit=True)},
            {"output": _output(vals, count_before=True)},
            {"output": _output(vals, real_max=True)},
        ]
        return Built(
            question=QUESTION,
            files={"snippet.py": "\n".join(lines) + "\n"},
            fields={"output": Field("text")},
            answer={"output": answer},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        code = compile(files["snippet.py"], "snippet.py", "exec")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(code, {"__name__": "__main__"})
        return {"output": buf.getvalue().strip()}


FAMILY = SnippetOutput()
