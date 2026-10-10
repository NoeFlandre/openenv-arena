# SPDX-License-Identifier: Apache-2.0

"""
Quality gates every family must pass. ``check_family`` returns a list of failure
strings, so an empty list means the family passes.

Gates, all over every level and every seed:
  size       files, question and reset text within the protocol caps
  oracle     the reference solver, run on the text alone, scores 1.0 on the answer
  decoys     at least 3 plausible wrong answers, each scoring below 1.0
  equiv      the answer re-serialised differently (key order, sets, 1.0 for 1,
             unreduced fractions) still scores 1.0
  leak       answer values do not appear in the question
  prior      the single most common answer solves at most 10% of instances

Run for one family:  python -m tests.gates sw1 [seeds]
"""

import collections
import json
import random
import sys
from fractions import Fraction

from workbench_gym.core.grading import Field, score_answer
from workbench_gym.core.protocol import (
    FILES_MAX_COUNT,
    FILES_MAX_TOTAL_CHARS,
    QUESTION_CHARS,
    RESET_CHARS,
    reset_text,
)
from workbench_gym.families import load_families

PRIOR_LIMIT = 0.10
PRIOR_SAMPLES = 1000


def _reserialise(answer: dict, fields: dict[str, Field]) -> dict:
    out = {}
    for name in reversed(list(answer)):
        value = answer[name]
        spec = fields[name]
        if spec.kind == "int":
            value = float(value)
        elif spec.kind == "set" and isinstance(value, list):
            value = list(reversed(value))
        elif spec.kind == "object" and isinstance(value, dict):
            value = dict(reversed(list(value.items())))
        elif spec.kind == "text" and isinstance(value, str):
            value = f"  {value}  "
        elif spec.kind == "fraction":
            p, q = Fraction(str(value)).numerator, Fraction(str(value)).denominator
            value = f"{p * 2}/{q * 2}"
        out[name] = value
    return out


def check_family(family, seeds: int = 200) -> list[str]:
    failures: list[str] = []

    def fail(where: str, msg: str) -> None:
        if len(failures) < 40:
            failures.append(f"{family.id} {where}: {msg}")

    modal: collections.Counter = collections.Counter()
    canon_answer: dict[str, dict] = {}
    for level in family.levels:
        for seed in range(seeds):
            where = f"L{level} seed {seed}"
            try:
                built = family.build(level, random.Random(f"{family.id}-{level}-{seed}"))
            except Exception as exc:  # noqa: BLE001 - report any builder crash
                fail(where, f"build raised {exc!r}")
                continue

            total = sum(len(v) for v in built.files.values())
            if total > FILES_MAX_TOTAL_CHARS:
                fail(where, f"files total {total} chars > {FILES_MAX_TOTAL_CHARS}")
            if len(built.files) > FILES_MAX_COUNT:
                fail(where, f"{len(built.files)} files > {FILES_MAX_COUNT}")
            if len(built.question) > QUESTION_CHARS:
                fail(where, f"question {len(built.question)} chars > {QUESTION_CHARS}")
            text = reset_text(f"{family.id}-L{level}", built.question, built.fields)
            if len(text) > RESET_CHARS:
                fail(where, f"reset text {len(text)} chars > {RESET_CHARS}")

            if set(built.answer) != set(built.fields):
                fail(where, "answer keys differ from field names")
                continue
            if score_answer(built.answer, built.fields, built.answer) != 1.0:
                fail(where, "the builder's own answer does not score 1.0")

            try:
                solved = family.solve(dict(built.files), built.question)
            except Exception as exc:  # noqa: BLE001
                fail(where, f"solve raised {exc!r}")
                solved = None
            if solved is not None and score_answer(solved, built.fields, built.answer) != 1.0:
                fail(where, f"reference solver disagrees: solver={solved} builder={built.answer}")

            if len(built.decoys) < 3:
                fail(where, f"only {len(built.decoys)} decoys (need 3)")
            for decoy in built.decoys:
                if set(decoy) != set(built.fields):
                    fail(where, f"decoy keys differ: {decoy}")
                elif score_answer(decoy, built.fields, built.answer) >= 1.0:
                    fail(where, f"decoy scores 1.0: {decoy}")

            if score_answer(_reserialise(built.answer, built.fields), built.fields, built.answer) != 1.0:
                fail(where, "re-serialised answer does not score 1.0")

            for name, value in built.answer.items():
                if isinstance(value, str) and len(value) >= 3 and value in built.question:
                    fail(where, f"answer text {value!r} appears in the question")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if len(str(value)) >= 3 and str(value) in built.question:
                        fail(where, f"answer {value} appears in the question")

            key = json.dumps(built.answer, sort_keys=True)
            modal[(level, key)] += 1
            canon_answer.setdefault(key, built.answer)

    # The prior is estimated on more instances than the other gates use, so the
    # modal answer of a small answer space is not inflated by sampling noise.
    prior_seeds = max(seeds, PRIOR_SAMPLES)
    for level in family.levels:
        counts: collections.Counter = collections.Counter()
        for seed in range(prior_seeds):
            built = family.build(level, random.Random(f"prior-{family.id}-{level}-{seed}"))
            counts[json.dumps(built.answer, sort_keys=True)] += 1
        key, count = counts.most_common(1)[0]
        rate = count / prior_seeds
        if rate > PRIOR_LIMIT:
            fail(f"L{level}", f"most common answer {key} solves {rate:.0%} (limit {PRIOR_LIMIT:.0%})")
    return failures


def main(argv: list[str]) -> int:
    families = load_families()
    ids = argv[1:2] or sorted(families)
    seeds = int(argv[2]) if len(argv) > 2 else 200
    status = 0
    for family_id in ids:
        if family_id not in families:
            print(f"{family_id}: not registered")
            status = 1
            continue
        problems = check_family(families[family_id], seeds)
        print(f"{family_id}: {'PASS' if not problems else 'FAIL'}")
        for problem in problems:
            print("  " + problem)
        status |= bool(problems)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
