# SPDX-License-Identifier: Apache-2.0

"""
fin2: loan rate reset (finance-economics).

``terms.txt`` gives the loan facts: principal, term, starting rate, reset rate
and month, the payment before the reset, and extra principal payments.
``rules.txt`` gives the servicing order. An extra principal payment posts before
that month's interest, so it saves interest in its own month. At the reset the
payment is recast over the months left in the term. Each interest and recast
amount is rounded half up to the cent, and the question states that rule. The
answer is the principal balance after the horizon month, read from the question.

The principal is chosen so that month 1's interest is an exact half cent with an
even whole part. Half up rounds that step up. Floor, ceiling, half even and half
down do not, so the cent carries through to the answer. The builder redraws any
instance where one of those other roundings still gives the same answer.

Decoys: extra payment after interest, reset one month late, no recast at the
reset, the reset ignored, floor at every step, and half even at every step.
"""

import math
import random
import re
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    Decimal,
    localcontext,
)

from ..core.grading import Field
from .base import Built, Family

TERM = 360
HORIZON = {1: 12, 2: 24, 3: 36}
ROUNDING = {
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "half_down": ROUND_HALF_DOWN,
    "floor": ROUND_FLOOR,
    "ceil": ROUND_CEILING,
}
# Roundings the question does not state. None of them may reproduce the answer.
ALTERNATIVES = ("floor", "ceil", "half_even", "half_down")


def _grab(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return match.group(1)


def _cents(value: Decimal, rounding: str = "half_up") -> Decimal:
    return value.quantize(Decimal(1), rounding=ROUNDING[rounding])


def _recast(balance: Decimal, annual: Decimal, months: int, rounding: str = "half_up") -> Decimal:
    """Level payment that clears ``balance`` over ``months`` at ``annual`` (fraction per year)."""
    with localcontext() as ctx:
        ctx.prec = 50
        i = annual / 12
        return _cents(balance * i / (1 - (1 + i) ** (-months)), rounding)


def _tied_principal(start: int, rate_h: int, extra_1: int) -> int | None:
    """Smallest principal at or above ``start`` whose month-1 interest is an exact half cent.

    Month 1 interest is (principal - extra_1) x rate_h / 120000 cents, where rate_h is the
    start rate in hundredths of a percent. An exact half cent with an even whole part is a
    numerator of 60000 mod 240000. Returns None when no principal in one cycle works.
    """
    g = math.gcd(rate_h, 240_000)
    if 60_000 % g:
        return None
    mod = 240_000 // g
    residue = (60_000 // g) * pow(rate_h // g, -1, mod) % mod
    return start + (residue + extra_1 - start) % mod


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
    rounding: str = "half_up",
    recast_rounding: str = "half_up",
) -> int:
    """Balance in cents after ``horizon`` months. ``mode`` picks the rule under test.

    ``rounding`` applies to each monthly interest step, ``recast_rounding`` to the recast.
    """
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
                    pay = _recast(balance, rate, term - m + 1, recast_rounding)
            interest = _cents(balance * rate / 12, rounding)
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
    "5. Money is in cents. Each interest and recast amount is rounded half up to the cent "
    "(0.5 rounds up).\n"
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
        rate0_h = rng.randrange(450, 700)
        rate1_h = rate0_h + rng.randrange(80, 230)
        reset = rng.randint(3, horizon - 2)
        months = rng.sample(range(1, horizon + 1), rng.randint(2, 3))
        extras = {m: rng.randrange(50_000, 300_000) for m in sorted(months)}
        start = rng.randrange(15_000_000, 45_000_000)
        principal = _tied_principal(start, rate0_h, extras.get(1, 0))
        if principal is None:
            return None
        rate0 = Decimal(rate0_h) / 10000
        rate1 = Decimal(rate1_h) / 10000
        pay0 = int(_recast(Decimal(principal), rate0, TERM))

        def run(
            mode: str = "correct", rounding: str = "half_up", recast_rounding: str = "half_up"
        ) -> int:
            return _simulate(
                principal,
                rate0,
                rate1,
                TERM,
                reset,
                pay0,
                extras,
                horizon,
                mode,
                rounding,
                recast_rounding,
            )

        want = run()
        # Each other rounding, applied to every step or to the interest steps alone, must miss.
        for alt in ALTERNATIVES:
            if run(rounding=alt, recast_rounding=alt) == want or run(rounding=alt) == want:
                return None
        decoys: list[dict] = []
        candidates = [
            run(mode=mode) for mode in ("extra_after", "late_reset", "no_recast", "ignore_reset")
        ]
        candidates.append(run(rounding="floor", recast_rounding="floor"))
        candidates.append(run(rounding="half_even", recast_rounding="half_even"))
        for value in candidates:
            cand = {"balance_cents": value}
            if value != want and cand not in decoys:
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
                f"after month {horizon} is posted? Round each interest and recast amount "
                "half up to the cent (0.5 rounds up)."
            ),
            files={"terms.txt": terms, "rules.txt": RULES},
            fields={"balance_cents": Field("int")},
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
