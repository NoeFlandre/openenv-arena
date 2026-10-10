# SPDX-License-Identifier: Apache-2.0

"""
fin2: loan rate reset (finance-economics).

``terms.txt`` gives the loan facts: principal, term, starting rate, reset rate
and month, the payment before the reset, and extra principal payments.
``rules.txt`` gives the servicing order. An extra principal payment posts before
that month's interest, so it saves interest in its own month. At the reset the
payment is recast over the months left in the term. Each interest and recast
amount is rounded half up to the cent. The answer is the principal balance after
the horizon month, read from the question.

Decoys: extra payment after interest, reset one month late, no recast at the
reset, and the reset ignored.
"""

import random
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

from ..core.grading import Field
from .base import Built, Family

TERM = 360
HORIZON = {1: 12, 2: 24, 3: 36}


def _grab(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return match.group(1)


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _recast(balance: Decimal, annual: Decimal, months: int) -> Decimal:
    """Level payment that clears ``balance`` over ``months`` at ``annual`` (fraction per year)."""
    with localcontext() as ctx:
        ctx.prec = 50
        i = annual / 12
        return _cents(balance * i / (1 - (1 + i) ** (-months)))


def _simulate(
    principal: int,
    rate0: Decimal,
    rate1: Decimal,
    term: int,
    reset: int,
    pay0: int,
    extras: dict[int, int],
    horizon: int,
    mode: str,
) -> int:
    """Balance in cents after ``horizon`` months. ``mode`` picks the rule under test."""
    with localcontext() as ctx:
        ctx.prec = 50
        balance = Decimal(principal)
        rate = rate0
        pay = Decimal(pay0)
        at = reset + 1 if mode == "late_reset" else reset
        for m in range(1, horizon + 1):
            extra = Decimal(extras.get(m, 0))
            if mode != "extra_after":
                balance -= extra
            if mode != "ignore_reset" and m == at:
                rate = rate1
                if mode != "no_recast":
                    pay = _recast(balance, rate, term - m + 1)
            interest = _cents(balance * rate / 12)
            balance -= pay - interest
            if mode == "extra_after":
                balance -= extra
        return int(balance)


RULES = (
    "Servicing rules, loan 88-310\n"
    "1. Month m, step 1: post that month's extra principal payment, if any.\n"
    "2. Reset month only, step 2: recast the payment on the balance after step 1.\n"
    "   New payment = balance x i / (1 - (1 + i)^-n), i = reset rate / 12,\n"
    "   n = term - m + 1 (months left, this one included).\n"
    "3. Step 3: interest = balance x APR / 12. From the reset month on, use the reset rate.\n"
    "4. Step 4: payment minus interest reduces the balance.\n"
    "5. Money is in cents. Each interest and recast amount is rounded half up to the cent.\n"
)


def _fmt(hundredths: int) -> str:
    return f"{hundredths // 100}.{hundredths % 100:02d}"


class LoanRateReset(Family):
    id = "fin2"
    domain = "finance-economics"
    title = "Loan rate reset"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(200):
            built = self._attempt(level, rng)
            if built is not None:
                return built
        raise AssertionError(f"fin2 level {level}: no instance found")

    def _attempt(self, level: int, rng: random.Random) -> Built | None:
        horizon = HORIZON[level]
        principal = rng.randrange(15_000_000, 45_000_000)
        rate0_h = rng.randrange(450, 700)
        rate1_h = rate0_h + rng.randrange(80, 230)
        reset = rng.randint(3, horizon - 2)
        months = rng.sample(range(1, horizon + 1), rng.randint(2, 3))
        extras = {m: rng.randrange(50_000, 300_000) for m in sorted(months)}
        rate0 = Decimal(rate0_h) / 10000
        rate1 = Decimal(rate1_h) / 10000
        pay0 = int(_recast(Decimal(principal), rate0, TERM))

        want = _simulate(principal, rate0, rate1, TERM, reset, pay0, extras, horizon, "correct")
        decoys: list[dict] = []
        for mode in ("extra_after", "late_reset", "no_recast", "ignore_reset"):
            value = _simulate(principal, rate0, rate1, TERM, reset, pay0, extras, horizon, mode)
            cand = {"balance_cents": value}
            if abs(value - want) > 1 and cand not in decoys:
                decoys.append(cand)
        if len(decoys) < 3:
            return None

        terms = (
            "Loan 88-310, variable-rate home loan\n"
            f"Principal at month 0: {principal} cents\n"
            f"Term: {TERM} months\n"
            f"Start rate: {_fmt(rate0_h)} % APR\n"
            f"Monthly payment before reset: {pay0} cents\n"
            f"Reset rate: {_fmt(rate1_h)} % APR, reset month {reset}\n"
        )
        for m, amount in sorted(extras.items()):
            terms += f"Extra principal payment, month {m}: {amount} cents\n"
        return Built(
            question=(
                "Using terms.txt and rules.txt, what is the principal balance in cents "
                f"after month {horizon} is posted?"
            ),
            files={"terms.txt": terms, "rules.txt": RULES},
            fields={"balance_cents": Field("number", abs_tol=1.0)},
            answer={"balance_cents": want},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        terms = files["terms.txt"]
        principal = int(_grab(r"Principal at month 0: (\d+) cents", terms))
        term = int(_grab(r"Term: (\d+) months", terms))
        rate0 = Decimal(_grab(r"Start rate: ([\d.]+) % APR", terms)) / 100
        rate1 = Decimal(_grab(r"Reset rate: ([\d.]+) % APR", terms)) / 100
        pay0 = int(_grab(r"Monthly payment before reset: (\d+) cents", terms))
        reset = int(_grab(r"reset month (\d+)", terms))
        extras = {
            int(m): int(a)
            for m, a in re.findall(r"Extra principal payment, month (\d+): (\d+) cents", terms)
        }
        horizon = int(_grab(r"after month (\d+) is posted", question))
        value = _simulate(principal, rate0, rate1, term, reset, pay0, extras, horizon, "correct")
        return {"balance_cents": value}


FAMILY = LoanRateReset()
