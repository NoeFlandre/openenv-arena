# SPDX-License-Identifier: Apache-2.0

"""
sw3: introduced bug (software engineering).

``crash.txt`` is a traceback from a deployed build. Its last frame is where the
KeyError surfaces, in the rate table, and the frame above it is the caller in
checkout. ``history.txt`` lists commits, oldest first, and only src/ is deployed.
Every row of the table was renamed by a "tidy" commit, so the current
table alone cannot say which row the crashing code became: the new code is only
in history.txt. The answer is one text field, "path:line": path is the src/ file
the bug commit changed (as written in history.txt), and line is the row of the
new code in that file's current table.
Traps: the traceback names the caller and the crash site, a legacy copy carries
the same rename, and other codes were renamed by unrelated commits.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family, must_match

TABLE_PATHS = [
    "src/rates.py",
    "src/vat.py",
    "src/pricing/rates.py",
    "src/tax/table.py",
    "src/config/rates.py",
]
PREFIXES = [
    "EU",
    "US",
    "CA",
    "AU",
    "NZ",
    "JP",
    "KR",
    "IN",
    "BR",
    "MX",
    "CH",
    "NO",
    "SE",
    "FI",
    "DK",
    "PL",
]
SUFFIXES = ["AT", "BE", "CA", "DE", "NY", "ON"]
CODES = [f"{p}-{s}" for p in PREFIXES for s in SUFFIXES]
RATE_CHOICES = [0.05, 0.07, 0.08, 0.10, 0.13, 0.17, 0.19, 0.20, 0.21, 0.24, 0.25, 0.27]
FUNCS = ["add", "merge", "count", "split", "pack"]
QUESTION = (
    "crash.txt is a traceback from a deployed build. history.txt lists the commits. Which commit "
    "introduced this bug? Answer location as path:line: the path as written in history.txt, and "
    "the line of that row in the current table."
)
RENAME_MSG = "tidy"


def _hash(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(7))


def _table_lines(names: list[str], values: list[float]) -> list[str]:
    lines = ["# VAT rate by region code", "RATES = {"]
    for key, value in zip(names, values, strict=False):
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
        n = rng.randint(15, 16)
        keys = rng.sample(CODES, n)  # codes before the cleanup
        fresh = rng.sample([c for c in CODES if c not in keys], n)  # codes after it
        values = [rng.choice(RATE_CHOICES) for _ in keys]
        t_pos = rng.randrange(n)
        others = [i for i in range(n) if i != t_pos]
        o_pos = rng.choice(others)
        target, new_target = keys[t_pos], fresh[t_pos]
        v = values[t_pos]
        prev_target = rng.choice([x for x in RATE_CHOICES if x != v])
        rate_rows = set(rng.sample(others, 1))
        target_line = 3 + t_pos
        table_lines = _table_lines(fresh, values)
        table_text = "\n".join(table_lines) + "\n"
        crash_line = len(table_lines)
        caller_line = 2

        # One chain per row: an optional rate fix, then the rename. The target's chain
        # starts with a VAT update that changes its value, not its code.
        chains = []
        for i in range(n):
            if i == t_pos:
                chains.append(
                    [
                        (
                            tp,
                            f'"{target}": {prev_target:.2f}',
                            f'"{target}": {v:.2f}',
                            "VAT update",
                        ),
                        (tp, f'"{target}"', f'"{new_target}"', RENAME_MSG),
                    ]
                )
                continue
            chain = []
            if i in rate_rows:
                prev = rng.choice([x for x in RATE_CHOICES if x != values[i]])
                chain.append(
                    (tp, f'"{keys[i]}": {prev:.2f}', f'"{keys[i]}": {values[i]:.2f}', "rate fix")
                )
            chain.append((tp, f'"{keys[i]}"', f'"{fresh[i]}"', RENAME_MSG))
            chains.append(chain)
        rng.shuffle(chains)
        seq = [c for chain in chains for c in chain]

        built_files = {tp: table_text}
        if level >= 2:
            legacy_path = "legacy/" + tp
            built_files[legacy_path] = table_text
            cut_at = next(
                i for i, c in enumerate(seq) if c[1] == f'"{target}"' and c[2] == f'"{new_target}"'
            )
            seq.insert(
                rng.randint(cut_at + 1, len(seq)),
                (legacy_path, f'"{target}"', f'"{new_target}"', RENAME_MSG),
            )
            built_files["src/checkout.py"] = (
                "def total(item, region):\n"
                "    rate = vat_rate(region)\n"
                "    return item.price * (1 + rate)\n"
            )
            head, text, old = _small_module(rng)
            built_files["src/cart.py"] = text
            pass_region = (
                "src/checkout.py",
                "    rate = vat_rate(item.region)",
                "    rate = vat_rate(region)",
                "pass region",
            )
            seq.insert(rng.randint(0, len(seq)), pass_region)
            seq.insert(rng.randint(0, len(seq)), ("src/cart.py", old, head, "qty"))
        if level >= 3:
            for path in ("src/util.py", "src/log.py"):
                head, text, old = _small_module(rng)
                built_files[path] = text
                seq.insert(rng.randint(0, len(seq)), (path, old, head, "qty"))
            built_files["src/api.py"] = "def handle(req):\n    return req\n"

        history = ["# git log -p, oldest first; only src/ is deployed"]
        for path, old, new, msg in seq:
            history.append(f"{_hash(rng)} {path}  {old.strip()} -> {new.strip()}  # {msg}")

        crash = (
            "Deploy 2026-10-09 22:14 failed.\n"
            "Traceback (most recent call last):\n"
            f'  File "src/checkout.py", line {caller_line}, in total\n'
            "    rate = vat_rate(region)\n"
            f'  File "{tp}", line {crash_line}, in vat_rate\n'
            "    return RATES[region]\n"
            f"KeyError: '{target}'\n"
        )
        built_files["crash.txt"] = crash
        built_files["history.txt"] = "\n".join(history) + "\n"
        legacy_decoy = f"legacy/{tp}:{target_line}" if level >= 2 else f"{tp}:{target_line + 1}"
        return Built(
            question=QUESTION,
            files=built_files,
            fields={"location": Field("text")},
            answer={"location": f"{tp}:{target_line}"},
            decoys=[
                {"location": f"{tp}:{crash_line}"},
                {"location": f"{tp}:{3 + o_pos}"},
                {"location": f"src/checkout.py:{caller_line}"},
                {"location": legacy_decoy},
            ],
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        key = must_match(r"KeyError: '([^']+)'", files["crash.txt"]).group(1)
        line_re = re.compile(r"^\S+ (\S+)  (.+?) -> (.+?)  # ")
        found = None
        for line in files["history.txt"].split("\n"):
            match = line_re.match(line)
            if not match:
                continue
            path, old, new = match.groups()
            if not path.startswith("src/"):
                continue
            if f'"{key}"' in old and f'"{key}"' not in new:
                found = (path, must_match(r'"([^"]+)"', new).group(1))
        if found is None:
            return {"location": ""}
        path, code = found
        for number, text in enumerate(files[path].split("\n"), start=1):
            if f'"{code}":' in text:
                return {"location": f"{path}:{number}"}
        return {"location": ""}


FAMILY = IntroducedBug()
