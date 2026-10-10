# SPDX-License-Identifier: Apache-2.0

"""
sw3: introduced bug (software engineering).

``crash.txt`` is a traceback from a deployed build. Its last frame is where the
KeyError surfaces, in the rate table, and the frame above it is the caller in
checkout. ``history.txt`` lists commits, oldest first, each changing one line
in place. Only src/ is deployed. The answer is the path and line of the
change that broke the key the crash looks up, in a commit under src/.
The traps: the traceback names the caller and the crash site, a legacy copy
carries the same typo, and another key was broken by an unrelated commit.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

TABLE_PATHS = [
    "src/rates.py", "src/vat.py", "src/pricing/rates.py",
    "src/tax/table.py", "src/config/rates.py",
]
KEYS = [
    "EU-AT", "EU-BE", "EU-DE", "EU-DK", "EU-ES", "EU-FI", "EU-FR", "EU-GR",
    "EU-IE", "EU-IT", "EU-NL", "EU-PL", "EU-PT", "EU-SE", "EU-SI", "US-CA",
    "US-NY", "US-TX", "US-WA", "US-FL", "CA-ON", "CA-QC", "CA-BC", "AU-NSW",
    "AU-VIC", "NZ-AUK", "JP-13", "KR-11", "IN-MH", "BR-SP", "MX-CMX",
]
RATE_CHOICES = [0.05, 0.07, 0.08, 0.10, 0.13, 0.17, 0.19, 0.20, 0.21, 0.24, 0.25, 0.27]
FUNCS = ["add", "merge", "count", "split", "pack"]
QUESTION = (
    "crash.txt is a traceback from a deployed build. Using history.txt, which file and line "
    "did the commit that introduced this bug change? Give the path as written in history.txt "
    "and the line number."
)


def _hash(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(7))


def _table_lines(head_keys: list[str], values: list[float]) -> list[str]:
    lines = ["# VAT rate by region code", "RATES = {"]
    for key, value in zip(head_keys, values):
        lines.append(f'    "{key}": {value:.2f},')
    lines += ["}", "", "def vat_rate(region):", "    return RATES[region]"]
    return lines


def _small_module(rng: random.Random) -> tuple[str, str, str]:
    fn = rng.choice(FUNCS)
    head = f"def {fn}(item, qty=1):"
    text = head + "\n    return item * qty\n"
    return head, text, f"def {fn}(item):"


class IntroducedBug(Family):
    id = "sw3"
    domain = "software-engineering"
    title = "Introduced bug"

    def build(self, level: int, rng: random.Random) -> Built:
        tp = rng.choice(TABLE_PATHS)
        n = rng.randint(7, 12)
        keys = rng.sample(KEYS, n)
        values = [rng.choice(RATE_CHOICES) for _ in keys]
        t_pos = rng.randrange(n)
        target = keys[t_pos]
        typo1 = target[:-1]
        options = [
            i for i in range(n)
            if i != t_pos and keys[i][:-1] not in keys and keys[i][:-1] != typo1
        ]
        o_pos = rng.choice(options)
        typo2 = keys[o_pos][:-1]
        o2 = rng.choice([i for i in range(n) if i not in (t_pos, o_pos)])
        prev_target = rng.choice([v for v in RATE_CHOICES if v != values[t_pos]])
        prev_o2 = rng.choice([v for v in RATE_CHOICES if v != values[o2]])
        head_keys = list(keys)
        head_keys[t_pos] = typo1
        head_keys[o_pos] = typo2
        table = _table_lines(head_keys, values)
        crash_line = len(table)
        caller_line = rng.randint(4, 8)
        legacy_path = "legacy/" + tp
        table_text = "\n".join(table) + "\n"
        target_line = 3 + t_pos
        v = values[t_pos]

        val_commit = (tp, target_line, f'"{target}": {prev_target:.2f}', f'"{target}": {v:.2f}', "VAT update")
        culprit = (tp, target_line, f'"{target}": {v:.2f}', f'"{typo1}": {v:.2f}', "tidy codes")
        legacy = (legacy_path, target_line, f'"{target}": {v:.2f}', f'"{typo1}": {v:.2f}', "tidy codes")
        typo_commit = (
            tp, 3 + o_pos, f'"{keys[o_pos]}": {values[o_pos]:.2f}',
            f'"{typo2}": {values[o_pos]:.2f}', "tidy codes",
        )
        rate_commit = (tp, 3 + o2, f'"{keys[o2]}": {prev_o2:.2f}', f'"{keys[o2]}": {values[o2]:.2f}', "rate fix")

        checkout_lines = (
            ["def total(item, region):"]
            + [f"    # step {i}" for i in range(2, caller_line)]
            + ["    rate = vat_rate(region)", "    return item.price * (1 + rate)"]
        )
        checkout_text = "\n".join(checkout_lines) + "\n"
        built_files = {tp: table_text}
        rest = [legacy, typo_commit, rate_commit]
        if level >= 2:
            rest.append(("src/checkout.py", caller_line, "    rate = vat_rate(item.region)",
                         "    rate = vat_rate(region)", "pass region"))
            head, text, old = _small_module(rng)
            built_files["src/checkout.py"] = checkout_text
            built_files["src/cart.py"] = text
            built_files[legacy_path] = table_text
            rest.append(("src/cart.py", 1, old, head, "qty"))
        if level >= 3:
            for path in ("src/util.py", "src/log.py"):
                head, text, old = _small_module(rng)
                built_files[path] = text
                rest.append((path, 1, old, head, "qty"))
            built_files["src/api.py"] = "def handle(req):\n    return req\n"
        rng.shuffle(rest)
        seq = [val_commit] + rest
        seq.insert(rng.randint(1, len(seq)), culprit)

        history = ["# git log -p, oldest first; only src/ is deployed"]
        for path, line, old, new, msg in seq:
            history.append(f"{_hash(rng)} {path}:{line}  {old} -> {new}  # {msg}")
        crash = (
            "Deploy 2026-10-09 22:14 failed on the first checkout request.\n"
            "Traceback (most recent call last):\n"
            f'  File "src/checkout.py", line {caller_line}, in total\n'
            "    rate = vat_rate(region)\n"
            f'  File "{tp}", line {crash_line}, in vat_rate\n'
            "    return RATES[region]\n"
            f"KeyError: '{target}'\n"
        )
        built_files["crash.txt"] = crash
        built_files["history.txt"] = "\n".join(history) + "\n"
        return Built(
            question=QUESTION,
            files=built_files,
            fields={"path": Field("text"), "line": Field("int")},
            answer={"path": tp, "line": target_line},
            decoys=[
                {"path": tp, "line": crash_line},
                {"path": "src/checkout.py", "line": caller_line},
                {"path": legacy_path, "line": target_line},
                {"path": tp, "line": 3 + o_pos},
            ],
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        key = re.search(r"KeyError: '([^']+)'", files["crash.txt"]).group(1)
        pattern = re.compile(r"^\S+\s+([^:\s]+):(\d+)\s+(.*?)\s->\s(.*?)\s+#")
        found = {"path": "", "line": 0}
        for line in files["history.txt"].split("\n"):
            match = pattern.match(line)
            if not match:
                continue
            path, number, old, new = match.group(1), int(match.group(2)), match.group(3), match.group(4)
            if not path.startswith("src/"):
                continue
            if f'"{key}":' in old and f'"{key}":' not in new:
                found = {"path": path, "line": number}
        return found


FAMILY = IntroducedBug()
