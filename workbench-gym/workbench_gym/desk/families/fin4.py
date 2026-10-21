# SPDX-License-Identifier: Apache-2.0

"""
fin4: loan servicing balances (finance-economics).

``loans.csv`` lists amortizing loans and ``events.csv`` the servicing events:
extra principal payments and, from level 2, rate resets and cancelled rows.
``servicing_rules.md`` gives the monthly order: a reset recasts the payment over
the months left, interest is rounded half up to the cent, the scheduled payment
pays interest first, and extra principal posts after it. The answer is each
loan's principal balance after the reporting month and their total.

Decoys: extras ignored, extras posted before the month's interest, the
reporting month's payment left out, and from level 2 cancelled events applied,
no recast at a reset (old payment kept) and a reset applied one month late.
"""

import csv
import io
import json
import random
from decimal import ROUND_HALF_UP, Decimal

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match

CENT = Decimal("0.01")
START_RATES = [3.25, 3.9, 4.5, 4.75, 5.1, 5.6, 6.25, 6.8, 7.4]
OUT = "output/balances.json"


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _month_index(ym: str) -> int:
    year, month = ym.split("-")
    return int(year) * 12 + int(month) - 1


def _ym(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _payment(balance: Decimal, annual_pct: Decimal, months: int) -> Decimal:
    r = annual_pct / Decimal(1200)
    if r == 0:
        return _cents(balance / months)
    return _cents(balance * r / (1 - (1 + r) ** -months))


def _balances(
    loans: list[dict],
    events: list[dict],
    as_of: str,
    *,
    use_extras: bool = True,
    recast: bool = True,
    use_cancelled: bool = False,
    reset_shift: int = 0,
    extra_first: bool = False,
    end_shift: int = 0,
) -> dict[str, Decimal]:
    end = _month_index(as_of) + end_shift
    out: dict[str, Decimal] = {}
    for loan in loans:
        balance = Decimal(loan["principal"])
        rate = Decimal(loan["annual_rate_pct"])
        term = int(loan["term_months"])
        start = _month_index(loan["first_payment"])
        payment = _payment(balance, rate, term)
        mine = [
            e
            for e in events
            if e["loan_id"] == loan["loan_id"] and (use_cancelled or e["status"] != "CANCELLED")
        ]
        for paid, month in enumerate(range(start, min(end, start + term - 1) + 1)):
            for e in mine:
                if e["type"] == "RATE_RESET" and _month_index(e["month"]) + reset_shift == month:
                    rate = Decimal(e["value"])
                    if recast:
                        payment = _payment(balance, rate, term - paid)
            extras = [
                Decimal(e["value"])
                for e in mine
                if use_extras and e["type"] == "EXTRA" and _month_index(e["month"]) == month
            ]
            if extra_first:
                balance = max(Decimal(0), balance - sum(extras, Decimal(0)))
            interest = _cents(balance * rate / Decimal(1200))
            due = min(payment, balance + interest)
            balance = balance - (due - interest)
            if not extra_first:
                balance = max(Decimal(0), balance - sum(extras, Decimal(0)))
        out[loan["loan_id"]] = _cents(balance)
    return out


def _answer(balances: dict[str, Decimal]) -> dict:
    return {
        "balances": {k: float(v) for k, v in balances.items()},
        "total": float(sum(balances.values(), Decimal(0))),
    }


def _csv(rows: list[dict], header: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


RULES = """# Servicing rules (rev 4)

Apply these steps to every loan, month by month, from its first payment month
through the reporting month:

1. If a RATE_RESET event takes effect this month, the new annual rate applies
   from this month's interest on, and the scheduled payment is recast: the
   level payment that pays off the current balance over the months left in the
   term (term_months minus the payments already made), rounded half up to the
   cent.
2. Interest for the month = balance x annual_rate_pct / 1200, rounded half up
   to the cent.
3. The scheduled payment pays the month's interest first; the rest reduces the
   balance. The last payment never exceeds balance + interest.
4. EXTRA events are extra principal payments. They post after the scheduled
   payment of the same month and reduce the balance by their value.

The first scheduled payment is the level payment for the full term at the
starting rate, rounded half up to the cent.
"""

RULES_CANCELLED = """
Events whose status is CANCELLED were reversed by operations and must be
ignored. Only POSTED events count.
"""


class Fin4(DeskFamily):
    id = "fin4"
    domain = "finance-economics"
    title = "Loan servicing balances"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        n_loans = rng.randint(4, 6) if level == 1 else rng.randint(6, 9)
        base = _month_index(f"{rng.randint(2021, 2023)}-{rng.randint(1, 12):02d}")
        as_of = _ym(base + rng.randint(20, 30))
        loans, events = [], []
        for i in range(n_loans):
            loan_id = f"LN-{rng.randint(1000, 9999)}"
            if any(x["loan_id"] == loan_id for x in loans):
                return None
            start = base + rng.randint(0, 8)
            loan = {
                "loan_id": loan_id,
                "principal": f"{rng.randint(80, 900) * 100}.00",
                "annual_rate_pct": str(rng.choice(START_RATES)),
                "term_months": str(rng.choice([36, 48, 60, 84, 120])),
                "first_payment": _ym(start),
            }
            loans.append(loan)
            span = _month_index(as_of) - start
            for _ in range(rng.randint(1, 3)):
                month = start + rng.randint(0, span)
                events.append(
                    {
                        "month": _ym(month),
                        "loan_id": loan_id,
                        "type": "EXTRA",
                        "value": f"{rng.randint(5, 60) * 50}.00",
                        "status": "POSTED",
                    }
                )
            if level == 2 and i % 2 == 0:
                month = start + rng.randint(3, max(3, span - 2))
                events.append(
                    {
                        "month": _ym(month),
                        "loan_id": loan_id,
                        "type": "RATE_RESET",
                        "value": f"{rng.choice([2.9, 3.6, 5.25, 6.1, 7.15, 7.9])}",
                        "status": "POSTED",
                    }
                )
        if level == 2:
            for e in rng.sample(events, k=min(3, len(events))):
                dup = dict(e)
                dup["status"] = "CANCELLED"
                if dup["type"] == "EXTRA":
                    dup["value"] = f"{rng.randint(5, 60) * 50}.00"
                else:
                    dup["value"] = f"{rng.choice([4.4, 8.2, 9.0])}"
                events.append(dup)
        events.sort(key=lambda e: (e["month"], e["loan_id"]))

        truth = _balances(loans, events, as_of)
        decoys_raw = [
            _balances(loans, events, as_of, use_extras=False),
            _balances(loans, events, as_of, extra_first=True),
            _balances(loans, events, as_of, end_shift=-1),
        ]
        if level == 2:
            decoys_raw.append(_balances(loans, events, as_of, use_cancelled=True))
            decoys_raw.append(_balances(loans, events, as_of, recast=False))
            decoys_raw.append(_balances(loans, events, as_of, reset_shift=1))
        # Every decoy must miss by more than the grading tolerance on some loan.
        for d in decoys_raw:
            if max(abs(d[k] - truth[k]) for k in truth) <= Decimal("0.25"):
                return None

        files = {
            "loans.csv": _csv(
                loans, ["loan_id", "principal", "annual_rate_pct", "term_months", "first_payment"]
            ),
            "events.csv": _csv(events, ["month", "loan_id", "type", "value", "status"]),
            "servicing_rules.md": RULES + (RULES_CANCELLED if level == 2 else ""),
        }
        instruction = (
            "You are closing the month for the consumer lending desk. The loan book is "
            "in {root}/loans.csv (principal in dollars, annual_rate_pct, term_months, "
            "first_payment as YYYY-MM) and every servicing event is in {root}/events.csv "
            f"(month, loan_id, type, value, status). Follow {{root}}/servicing_rules.md "
            "exactly: it fixes the order of the monthly steps and the rounding.\n\n"
            f"Compute each loan's principal balance right after its {as_of} payment "
            f"(month {as_of} included). Write the result to {{root}}/{OUT} as a JSON "
            'object with two keys: "balances", mapping every loan_id to its balance in '
            'dollars rounded to the cent, and "total", the sum of those balances. Example '
            'shape: {"balances": {"LN-1234": 10512.33}, "total": 10512.33}. Create the '
            "output folder if it does not exist."
        )
        answer = _answer(truth)
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                JsonOut(
                    path=OUT,
                    checks={"balances": Check("map", tol=0.05), "total": Check("num", tol=0.1)},
                    want=answer,
                )
            ],
            oracle={OUT: json.dumps(answer)},
            decoys=[{OUT: json.dumps(_answer(d))} for d in decoys_raw],
        )

    def solve(self, files: dict[str, str | bytes], instruction: str) -> dict[str, str]:
        as_of = must_match(r"right after its (\d{4}-\d{2}) payment", instruction).group(1)
        loans = list(csv.DictReader(io.StringIO(str(files["loans.csv"]))))
        events = list(csv.DictReader(io.StringIO(str(files["events.csv"]))))
        return {OUT: json.dumps(_answer(_balances(loans, events, as_of)))}


FAMILY = Fin4()
