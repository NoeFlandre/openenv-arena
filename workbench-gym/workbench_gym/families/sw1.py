# SPDX-License-Identifier: Apache-2.0

"""
sw1: test cover (software engineering).

``changed.txt`` lists the modules changed in one commit, ``imports.txt`` the
direct internal imports of each module, and ``tests.txt`` each test file's
direct imports and runtime in milliseconds. A test must run when one of its
imports is changed or reaches a changed module through internal imports.
The traps: a test that imports only a top module still runs, and runtimes are
in milliseconds while the answer is whole seconds.
"""

import math
import random

from ..core.grading import Field
from .base import Built, Family

MODULES = {1: 6, 2: 10, 3: 14}
POOL = [
    "auth", "cart", "db", "api", "tax", "log", "util", "cache", "mail",
    "orders", "billing", "search", "export", "report", "ui", "jobs", "sync",
    "hooks", "forms", "rates", "email", "users", "pricing", "stock",
    "shipping", "tokens",
]
QUESTION = (
    "changed.txt lists the modules changed in one commit. A test must run when one of its "
    "imports is a changed module or reaches one through internal imports. Give tests (the "
    "test files to run) and test_cost (their total runtime in whole seconds, rounded down)."
)


def _lines(text: str) -> list[str]:
    keep = []
    for raw in text.split("\n"):
        line = raw.strip()
        if line and not line.startswith("#"):
            keep.append(line)
    return keep


def _affected(changed, deps: dict[str, list[str]]) -> set[str]:
    """Modules that are changed, or that import a changed module directly or not."""
    hit = set(changed)
    grew = True
    while grew:
        grew = False
        for mod in sorted(deps):
            if mod not in hit and any(dep in hit for dep in deps[mod]):
                hit.add(mod)
                grew = True
    return hit


def _instance(n: int, changed_count: int, rng: random.Random):
    order = rng.sample(POOL, n)
    deps: dict[str, list[str]] = {order[0]: []}
    for i in range(1, n):
        deps[order[i]] = rng.sample(order[:i], min(rng.choice((1, 1, 2)), i))
    tests: dict[str, list[str]] = {}
    for mod in order:
        imports = [mod]
        if rng.random() < 0.5:
            imports.append(rng.choice([m for m in order if m != mod]))
        tests[f"test_{mod}.py"] = sorted(set(imports))
    ms = {name: rng.randint(180, 9000) for name in sorted(tests)}
    candidates = [m for m in order if 3 <= len(_affected([m], deps)) <= n - 2]
    if len(candidates) < changed_count:
        return None
    changed = sorted(rng.sample(candidates, changed_count))
    aff = _affected(changed, deps)
    selected = sorted(t for t, imps in tests.items() if any(i in aff for i in imps))
    direct = sorted(t for t, imps in tests.items() if any(i in changed for i in imps))
    if selected == direct or len(selected) == len(tests):
        return None
    total = sum(ms[t] for t in selected)
    if total < 1000:
        return None
    if total % 1000 == 0:
        ms[selected[0]] += 1
        total += 1
    return {
        "deps": deps, "tests": tests, "ms": ms, "changed": changed,
        "selected": selected, "direct": direct, "total": total,
    }


class TestCoverCost(Family):
    id = "sw1"
    domain = "software-engineering"
    title = "Test cover and runtime"

    def build(self, level: int, rng: random.Random) -> Built:
        n = MODULES[level]
        changed_count = 1 if level == 1 else rng.choice((1, 2))
        inst = None
        for _ in range(500):
            inst = _instance(n, changed_count, rng)
            if inst is not None:
                break
        if inst is None:
            raise AssertionError("no valid instance")
        deps, tests, ms = inst["deps"], inst["tests"], inst["ms"]
        selected, direct, total = inst["selected"], inst["direct"], inst["total"]
        files = {
            "changed.txt": "# modules changed in this commit\n" + "\n".join(inst["changed"]) + "\n",
            "imports.txt": "# direct internal imports\n" + "\n".join(
                f"{m}: {' '.join(sorted(deps[m])) or '-'}" for m in sorted(deps)
            ) + "\n",
            "tests.txt": "# test file: direct imports | runtime\n" + "\n".join(
                f"{t}: {' '.join(tests[t])} | {ms[t]} ms" for t in sorted(tests)
            ) + "\n",
        }
        decoys = [
            {"tests": direct, "test_cost": sum(ms[t] for t in direct) // 1000},
            {"tests": selected, "test_cost": total},
            {"tests": selected, "test_cost": math.ceil(total / 1000)},
            {"tests": sorted(tests), "test_cost": sum(ms.values()) // 1000},
        ]
        return Built(
            question=QUESTION,
            files=files,
            fields={"tests": Field("set"), "test_cost": Field("int")},
            answer={"tests": selected, "test_cost": total // 1000},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        changed = _lines(files["changed.txt"])
        deps: dict[str, list[str]] = {}
        for line in _lines(files["imports.txt"]):
            mod, _, rest = line.partition(":")
            names = rest.split()
            deps[mod.strip()] = [] if not names or names == ["-"] else names
        tests: dict[str, tuple[list[str], int]] = {}
        for line in _lines(files["tests.txt"]):
            head, _, tail = line.partition(":")
            imports, _, runtime = tail.partition("|")
            tests[head.strip()] = (imports.split(), int(runtime.split()[0]))
        aff = _affected(changed, deps)
        selected = sorted(t for t, (imps, _) in tests.items() if any(i in aff for i in imps))
        total = sum(tests[t][1] for t in selected)
        return {"tests": selected, "test_cost": total // 1000}


FAMILY = TestCoverCost()
