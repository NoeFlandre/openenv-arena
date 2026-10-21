# SPDX-License-Identifier: Apache-2.0

"""
Quality gates for Workbench Desk families. ``check_family`` returns failure
strings, so an empty list means the family passes.

Gates, over every level and every seed:
  text     the instruction names {root}, every input file and every output path
  size     input files total at most MAX_INPUT_BYTES
  oracle   the oracle output files score 1.0
  solver   the family's solver, run on the files and the instruction text, scores 1.0
  decoys   at least 2 decoys, each scoring below 1.0
  empty    no output files score 0.0
  prior    the most common oracle output appears in at most 10% of instances

Run for one family:  python -m tests.desk_gates fin4 [seeds]
"""

import collections
import random
import sys

from workbench_gym.desk.families import load_families
from workbench_gym.desk.spec import grade_texts

MAX_INPUT_BYTES = 400_000
MIN_CHARS, MAX_CHARS = 300, 2400
PRIOR_LIMIT = 0.10


def check_family(family, seeds: int = 60) -> list[str]:
    failures: list[str] = []
    for level in family.levels:
        seen: collections.Counter[str] = collections.Counter()
        for seed in range(seeds):
            where = f"{family.id}-L{level} seed {seed}"
            task = family.build(level, random.Random(seed))
            text = task.instruction
            if "{root}" not in text:
                failures.append(f"{where}: instruction has no {{root}}")
            if not MIN_CHARS <= len(text) <= MAX_CHARS:
                failures.append(f"{where}: instruction has {len(text)} characters")
            for name in task.files:
                if "{root}/" + name not in text and name not in _named_by_files(task):
                    failures.append(f"{where}: input {name} is not named")
            for out in task.outputs:
                if "{root}/" + out.path not in text:
                    failures.append(f"{where}: output {out.path} is not named")
            size = sum(len(v) for v in task.files.values())
            if size > MAX_INPUT_BYTES:
                failures.append(f"{where}: inputs are {size} bytes")
            reward, note = grade_texts(task.outputs, dict(task.oracle))
            if reward != 1.0:
                failures.append(f"{where}: oracle scores {reward} ({note})")
            solved = family.solve(dict(task.files), text.replace("{root}", "/root/task-x"))
            reward, note = grade_texts(task.outputs, dict(solved))
            if reward != 1.0:
                failures.append(f"{where}: solver scores {reward} ({note})")
            if len(task.decoys) < 2:
                failures.append(f"{where}: only {len(task.decoys)} decoys")
            for i, decoy in enumerate(task.decoys):
                reward, _ = grade_texts(task.outputs, dict(decoy))
                if reward >= 1.0:
                    failures.append(f"{where}: decoy {i} scores {reward}")
            if grade_texts(task.outputs, {})[0] != 0.0:
                failures.append(f"{where}: no outputs does not score 0")
            seen[repr(sorted(task.oracle.items()))] += 1
        top = seen.most_common(1)[0][1] if seen else 0
        if top > PRIOR_LIMIT * seeds:
            failures.append(f"{family.id}-L{level}: one answer in {top} of {seeds} instances")
    return failures


def _named_by_files(task) -> set[str]:
    """Inputs may be named by another input (a README that lists them), not the instruction."""
    named: set[str] = set()
    for content in task.files.values():
        if isinstance(content, str):
            for name in task.files:
                if name in content:
                    named.add(name)
    return named


def main() -> None:
    families = load_families()
    ids = sys.argv[1:2] or sorted(families)
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    bad = 0
    for fid in ids:
        failures = check_family(families[fid], seeds)
        bad += len(failures)
        print(f"{fid}: {'ok' if not failures else f'{len(failures)} failures'}")
        for line in failures[:20]:
            print("  ", line)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
