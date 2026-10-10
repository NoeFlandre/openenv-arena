# SPDX-License-Identifier: Apache-2.0

"""
fin1: held reversals (finance-economics).

``statement.txt`` lists one account's entries in posting order: CHARGE and
PAYMENT lines, and REVERSE lines that cancel an earlier charge in full.
``policy.txt`` caps the total of accepted reversals. A reversal that would take
that total above the cap is held and rejected whole, and a rejected reversal
does not count toward the cap, so later reversals are still checked.

Decoys are the realistic misreadings: partial application up to the cap,
stopping at the first rejection, ignoring the cap, and applying the cap to each
reversal alone. The builder redraws any instance where the reversal-alone or the
stop-at-first-rejection reading gives the true answer, at every level, so those
two readings always score below 1.0.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

REVERSALS = {1: 3, 2: 5, 3: 7}


def _grab(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return match.group(1)


def _sequence(n_charge: int, n_pay: int, n_rev: int, rng: random.Random) -> list[dict]:
    """Entries in posting order. A REVERSE always names an earlier, not yet reversed CHARGE."""
    for _ in range(500):
        left = {"CHARGE": n_charge, "PAYMENT": n_pay, "REVERSE": n_rev}
        open_charges: list[dict] = []
        entries: list[dict] = []
        while any(left.values()):
            options = [k for k, v in left.items() if v and (k != "REVERSE" or open_charges)]
            if not options:
                break
            kind = rng.choice(options)
            left[kind] -= 1
            entry_id = f"E{len(entries) + 1:02d}"
            if kind == "CHARGE":
                entry = {"id": entry_id, "kind": kind, "amount": rng.randint(500, 15000)}
                open_charges.append(entry)
            elif kind == "PAYMENT":
                entry = {"id": entry_id, "kind": kind, "amount": rng.randint(2000, 9000)}
            else:
                target = open_charges.pop(rng.randrange(len(open_charges)))
                entry = {
                    "id": entry_id,
                    "kind": kind,
                    "amount": target["amount"],
                    "target": target["id"],
                }
            entries.append(entry)
        if not any(left.values()):
            return entries
    raise AssertionError("fin1: no posting order found")


def _post(entries: list[dict], opening: int, cap: int, rule: str) -> tuple[int, list[str]]:
    """Closing balance and rejected reversal IDs under one rule. ``held`` is the policy."""
    balance = opening
    accepted = 0
    rejected: list[str] = []
    blocked = False
    for entry in entries:
        if entry["kind"] == "CHARGE":
            balance += entry["amount"]
            continue
        if entry["kind"] == "PAYMENT":
            balance -= entry["amount"]
            continue
        amount = entry["amount"]
        room = cap - accepted
        reject = False
        take = amount
        if rule == "held":
            reject = amount > room
        elif rule == "stop":
            reject = blocked or amount > room
            blocked = blocked or reject
        elif rule == "alone":
            reject = amount > cap
        elif rule == "partial":
            take = max(min(amount, room), 0)
        # rule "ignore_cap" never rejects
        if reject:
            rejected.append(entry["id"])
            take = 0
        accepted += take
        balance -= take
    return balance, sorted(rejected)


class HeldReversals(Family):
    id = "fin1"
    domain = "finance-economics"
    title = "Held reversals"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(400):
            built = self._attempt(level, rng)
            if built is not None:
                return built
        raise AssertionError(f"fin1 level {level}: no instance found")

    def _attempt(self, level: int, rng: random.Random) -> Built | None:
        n_rev = REVERSALS[level]
        entries = _sequence(n_rev + rng.randint(3, 6), rng.randint(1, 3), n_rev, rng)
        opening = rng.randint(40_000, 300_000)
        reversed_total = sum(e["amount"] for e in entries if e["kind"] == "REVERSE")
        cap = rng.randint(max(1000, reversed_total // 4), reversed_total * 3 // 4)
        want_close, want_rej = _post(entries, opening, cap, "held")
        if not want_rej or len(want_rej) == n_rev:
            return None
        # The one-at-a-time reading (rule 2 applied to each reversal alone) and the
        # stop-at-first-rejection reading (rule 5 ignored) must not give the true
        # answer. An instance where either does is redrawn.
        for rule in ("alone", "stop"):
            if _post(entries, opening, cap, rule) == (want_close, want_rej):
                return None
        decoys: list[dict] = []
        for rule in ("partial", "stop", "ignore_cap", "alone"):
            close, rej = _post(entries, opening, cap, rule)
            cand = {"closing_cents": close, "rejected": rej}
            if (close != want_close or rej != want_rej) and cand not in decoys:
                decoys.append(cand)
        if len(decoys) < 3:
            return None

        lines = [
            "Account 4471-02, statement 2026-09",
            f"Opening balance: {opening} cents",
            "Entries, in posting order:",
        ]
        for e in entries:
            if e["kind"] == "REVERSE":
                lines.append(f"{e['id']} REVERSE {e['target']}")
            else:
                lines.append(f"{e['id']} {e['kind']} {e['amount']}")
        policy = (
            "Held reversals, statement 2026-09 (rule set R-4)\n"
            "1. A REVERSE line cancels the full amount of the CHARGE it names.\n"
            f"2. Reversal cap for this statement: {cap} cents, counted on accepted reversals.\n"
            "3. Entries are processed in file order.\n"
            "4. A reversal that would take accepted reversals above the cap is held and "
            "rejected in full. It is never partly applied.\n"
            "5. A rejected reversal does not count toward the cap. "
            "Later reversals are still checked.\n"
            "6. CHARGE and PAYMENT lines always post.\n"
        )
        return Built(
            question=(
                "Apply policy.txt to statement.txt. What is the closing balance in cents "
                "(opening, plus charges, minus payments and accepted reversals), and which "
                "REVERSE entries are held and rejected?"
            ),
            files={"statement.txt": "\n".join(lines) + "\n", "policy.txt": policy},
            fields={"closing_cents": Field("int"), "rejected": Field("set")},
            answer={"closing_cents": want_close, "rejected": want_rej},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        statement = files["statement.txt"]
        policy = files["policy.txt"]
        balance = int(_grab(r"Opening balance: (\d+) cents", statement))
        cap = int(_grab(r"Reversal cap for this statement: (\d+) cents", policy))
        amounts: dict[str, int] = {}
        accepted = 0
        rejected: list[str] = []
        for line in statement.split("\n"):
            match = re.match(r"^(E\d+) (CHARGE|PAYMENT|REVERSE) (\S+)$", line.strip())
            if match is None:
                continue
            entry_id, kind, arg = match.groups()
            if kind == "CHARGE":
                amounts[entry_id] = int(arg)
                balance += int(arg)
            elif kind == "PAYMENT":
                balance -= int(arg)
            else:
                amount = amounts[arg]
                if amount > cap - accepted:
                    rejected.append(entry_id)
                else:
                    accepted += amount
                    balance -= amount
        return {"closing_cents": balance, "rejected": sorted(rejected)}


FAMILY = HeldReversals()
