# SPDX-License-Identifier: Apache-2.0

"""
Select the shipped tasks from calibration runs.

Reads the JSONL files written by tools/calibrate.py and keeps a task when:
  - it has at least --min-n episodes with no error, and
  - its solve rate lies in [--lo, --hi] (the mixed-outcome band).

Writes one line per kept task to --out (task id, family, level, rate, counts) and
a per-task table to stdout. Nothing is kept by hand.

Usage:
  python tools/select.py --min-n 20 --lo 0.2 --hi 0.8 --out tasks.jsonl runs/*.jsonl
"""

import argparse
import collections
import json
import sys

from workbench_gym.families import load_families


def load(paths: list[str]) -> dict[str, list[dict]]:
    by_task: dict[str, list[dict]] = collections.defaultdict(list)
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                if "error" in record:
                    continue
                by_task[record["task_id"]].append(record)
    return by_task


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--min-n", type=int, default=20)
    parser.add_argument("--lo", type=float, default=0.2)
    parser.add_argument("--hi", type=float, default=0.8)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    families = load_families()
    by_task = load(args.runs)
    kept = []
    print(f"{'task':10} {'n':>4} {'solved':>6} {'rate':>6} {'invalid':>7} {'trunc':>5} {'tok':>6}  verdict")
    for task in sorted(by_task):
        records = by_task[task]
        n = len(records)
        solved = sum(1 for r in records if r.get("solved"))
        rate = solved / n if n else 0.0
        invalid = sum(r.get("invalid", 0) for r in records)
        trunc = sum(r.get("truncated", 0) for r in records)
        tokens = sum(r.get("completion_tokens", 0) for r in records) / max(n, 1)
        if n < args.min_n:
            verdict = f"short (n={n})"
        elif args.lo <= rate <= args.hi:
            verdict = "keep"
            family_id, level = task.split("-L")
            kept.append(
                {
                    "task_id": task,
                    "family": family_id,
                    "domain": families[family_id].domain,
                    "level": int(level),
                    "rate": round(rate, 3),
                    "n": n,
                }
            )
        else:
            verdict = "drop (too easy)" if rate > args.hi else "drop (too hard)"
        print(f"{task:10} {n:4d} {solved:6d} {rate:6.2f} {invalid:7d} {trunc:5d} {tokens:6.0f}  {verdict}")

    per_domain = collections.Counter(k["domain"] for k in kept)
    print(f"\nkept {len(kept)} tasks across {len(per_domain)} domains")
    for domain, count in sorted(per_domain.items()):
        print(f"  {domain}: {count}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            for item in kept:
                fh.write(json.dumps(item) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
