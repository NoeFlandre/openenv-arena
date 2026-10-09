# SPDX-License-Identifier: Apache-2.0

"""
Tasks for the Derivation Check environment.

Two families: a worked calculation with some wrong equations (math and formal
reasoning), and a list of social media captions with a length limit (media and
content production). Each task builds one log from its seed. The answer is the
first line that breaks the rule, computed when the task is built.

Levels 0-2 are easy, 3-5 medium and 6-7 hard. Harder levels have more lines,
more wrong equations or captions that sit close to the limit.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

FAMILIES = ("math", "caption")
TASKS_PER_FAMILY = 8

PROTOCOL = (
    'Reply {"grep": "<text>"} to search the log (up to 10 matching lines), '
    'or {"answer": "<value>"} to finish.'
)


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    level: int
    seed: int


@dataclass(frozen=True)
class Built:
    lines: list[str]
    answer: str
    question: str
    seed: int


def _task_table() -> dict[str, Task]:
    table: dict[str, Task] = {}
    for family_index, family in enumerate(FAMILIES):
        for level in range(TASKS_PER_FAMILY):
            task_id = f"{family}-{level:02d}"
            table[task_id] = Task(task_id, family, level, 3000 + 10 * family_index + level)
    return table


TASKS = _task_table()


def _tier(level: int) -> int:
    return 0 if level < 3 else 1 if level < 6 else 2


def _ask(body: str, reply: str) -> str:
    return f"{body} Answer with {reply} only. {PROTOCOL}"


# ---------------------------------------------------------------- math


MATH_STEPS = (20, 32, 44)
MATH_WRONG = (1, 2, 3)


def _equation(rng: random.Random) -> tuple[int, str, int, int]:
    op = rng.choice("+-*")
    if op == "*":
        a, b = rng.randint(12, 98), rng.randint(3, 9)
    elif op == "+":
        a, b = rng.randint(100, 899), rng.randint(100, 899)
    else:
        a = rng.randint(200, 999)
        b = rng.randint(100, a - 1)
    result = a * b if op == "*" else a + b if op == "+" else a - b
    return a, op, b, result


def _make_math(level: int, rng: random.Random) -> Built:
    tier = _tier(level)
    count = MATH_STEPS[tier] + rng.randint(0, 4)
    wrong = set(rng.sample(range(1, count + 1), MATH_WRONG[tier]))
    lines = []
    first_wrong = 0
    for step in range(1, count + 1):
        a, op, b, result = _equation(rng)
        shown = result
        if step in wrong:
            shown = result + rng.choice([d for d in range(-9, 10) if d != 0])
            if not first_wrong:
                first_wrong = step
        lines.append(f"step {step:02d}: {a} {op} {b} = {shown}")
    question = _ask(
        "Each line is one step of a calculation. Some equations are wrong. Which step is the "
        "first wrong equation?",
        "the step number as written, for example 07",
    )
    return Built(lines, f"{first_wrong:02d}", question, 0)


# ---------------------------------------------------------------- caption


CAPTION_LIMIT = 90
CAPTION_COUNTS = (12, 16, 20)
WORDS = [
    "a",
    "to",
    "in",
    "on",
    "we",
    "our",
    "new",
    "day",
    "post",
    "video",
    "photo",
    "launch",
    "team",
    "story",
    "behind",
    "scenes",
    "today",
    "fresh",
    "local",
    "market",
    "guide",
    "tips",
    "for",
    "your",
    "weekend",
    "trip",
    "with",
    "friends",
    "every",
    "morning",
    "coffee",
    "garden",
    "update",
    "result",
    "thanks",
    "everyone",
    "who",
    "joined",
    "us",
    "this",
    "week",
    "special",
    "offer",
    "read",
    "more",
    "link",
    "bio",
    "share",
    "love",
]


def _caption_text(target: int, rng: random.Random) -> str:
    """Build text of exactly ``target`` characters from words, ending with a full stop if needed."""
    text = ""
    while True:
        room = target - len(text)
        if room == 0:
            return text
        if room == 1:
            return text + "."
        fits = [w for w in WORDS if (len(w) if not text else len(w) + 1) <= room]
        word = rng.choice(fits)
        text = word if not text else f"{text} {word}"


def _make_caption(level: int, rng: random.Random) -> Built:
    tier = _tier(level)
    count = CAPTION_COUNTS[tier]
    first_over = rng.randint(2, count - 2)
    low = {0: 60, 1: 80, 2: 84}[tier]
    lengths = []
    for index in range(count):
        if index < first_over:
            lengths.append(rng.randint(low, CAPTION_LIMIT))
        elif index == first_over:
            lengths.append(
                rng.randint(CAPTION_LIMIT + 1, CAPTION_LIMIT + {0: 10, 1: 4, 2: 3}[tier])
            )
        else:
            lengths.append(rng.randint(low, CAPTION_LIMIT + 10))
    texts = [_caption_text(length, rng) for length in lengths]
    lines = [f'cap {index + 1:02d} text="{text}"' for index, text in enumerate(texts)]
    answer_index = next(i for i, text in enumerate(texts) if len(text) > CAPTION_LIMIT)
    question = _ask(
        f"Each line is a social post caption. The limit is {CAPTION_LIMIT} characters, counting "
        "spaces and punctuation, and a caption is over the limit when it has more than "
        f"{CAPTION_LIMIT} characters. Which caption is the first one over the limit?",
        "the caption number as written, for example 07",
    )
    return Built(lines, f"{answer_index + 1:02d}", question, 0)


# ---------------------------------------------------------------- public


_MAKERS: dict[str, Callable[[int, random.Random], Built]] = {
    "math": _make_math,
    "caption": _make_caption,
}


def build(task_id: str) -> Built:
    """Build the log, the answer, the question and the accepted seed for one task."""
    task = TASKS[task_id]
    built = _MAKERS[task.family](task.level, random.Random(task.seed))
    return Built(built.lines, built.answer, built.question, task.seed)
