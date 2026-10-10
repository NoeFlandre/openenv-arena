# SPDX-License-Identifier: Apache-2.0

"""
off3: expense audit with FX rounding and receipt-date caps (office white-collar).

``receipts.csv`` lists claims in several currencies. Each non-EUR amount is
converted with the latest rate dated on or before the receipt date, rounded half
up to the cent per receipt, then checked against the cap table in force on the
receipt date. Truncating instead of rounding, converting at the submission date,
rounding only the total, or using the old caps each gives a different answer.
"""

import csv
import io
import math
import random
import re
from datetime import date, timedelta
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family

COUNTS = {1: 8, 2: 12, 3: 16}
CUTOFF = "2026-07-01"
CATS = ("meal", "taxi", "hotel", "train")
CAPS_BEFORE = {"meal": 6000, "taxi": 8000, "hotel": 18000, "train": 15000}
CAPS_FROM = {"meal": 5500, "taxi": 9000, "hotel": 17000, "train": 14000}
RATE_DATES = ("2026-06-01", "2026-06-22", "2026-07-06")
BASE_RATES = {"GBP": (11500, 300), "USD": (9200, 400), "CHF": (10500, 300), "SEK": (900, 6)}
CURRENCIES = ("EUR", "GBP", "USD", "CHF", "SEK")
MAX_TRIES = 300

POLICY = (
    "Expense policy, rev 5. Money is in EUR unless a currency is named.\n"
    "1. Non-EUR: use the latest rate in rates.csv on or before the receipt date.\n"
    "2. Round each converted receipt to the cent, half up, before any other step.\n"
    "3. Caps per receipt in EUR, by receipt date.\n"
    "Before 2026-07-01: meal 60, taxi 80, hotel 180, train 150.\n"
    "From 2026-07-01: meal 55, taxi 90, hotel 170, train 140.\n"
    "4. Reject a receipt above its cap. Equal is accepted.\n"
    "5. Output the rejected ids and the total of accepted receipts in EUR cents.\n"
)
QUESTION = (
    "receipts.csv lists expense claims in several currencies. Under policy.txt, which "
    "receipt ids are rejected, and what is the total of accepted receipts in EUR cents?"
)


def _caps(iso):
    return CAPS_FROM if iso >= CUTOFF else CAPS_BEFORE


def _rate_date(iso):
    return max(d for d in RATE_DATES if d <= iso)


def _money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def _outcome(receipts, rates, rate_key="rdate", stale_caps=False, rounding="half", total_round=False):
    rejected = []
    total = 0
    exact_total = Fraction(0)
    for r in receipts:
        rate = Fraction(1) if r["cur"] == "EUR" else Fraction(rates[(_rate_date(r[rate_key]), r["cur"])], 10000)
        exact = Fraction(r["amount"]) * rate * 100
        cents = math.floor(exact + Fraction(1, 2)) if rounding == "half" else math.floor(exact)
        caps = CAPS_BEFORE if stale_caps else _caps(r["rdate"])
        if cents > caps[r["cat"]]:
            rejected.append(r["id"])
        else:
            total += cents
            exact_total += exact
    if total_round:
        total = math.floor(exact_total + Fraction(1, 2))
    return {"rejected": sorted(rejected), "total_cents": total}


def _distinct(candidates, answer):
    out = []
    for cand in candidates:
        if cand != answer and cand not in out:
            out.append(cand)
    return out


class ExpenseAudit(Family):
    id = "off3"
    domain = "office-white-collar"
    title = "Expense audit"

    def build(self, level: int, rng: random.Random) -> Built:
        n = COUNTS[level]
        for _ in range(MAX_TRIES):
            rates = {}
            for d in RATE_DATES:
                for cur, (base, spread) in BASE_RATES.items():
                    rates[(d, cur)] = base + rng.randint(-spread, spread)
            receipts = []
            for rid in rng.sample(range(1000, 2000), n):
                rdate = date(2026, 6, 3) + timedelta(days=rng.randint(0, 41))
                sdate = rdate + timedelta(days=rng.randint(0, 6))
                cat = rng.choice(CATS)
                cur = rng.choice(CURRENCIES)
                target = _caps(rdate.isoformat())[cat] * rng.randint(55, 135) // 100
                if cur == "EUR":
                    amount = _money(target)
                else:
                    rate = rates[(_rate_date(rdate.isoformat()), cur)]
                    amount = _money((target * 10000 + rate // 2) // rate)
                receipts.append(
                    {
                        "id": f"R-{rid}",
                        "rdate": rdate.isoformat(),
                        "sdate": sdate.isoformat(),
                        "cat": cat,
                        "cur": cur,
                        "amount": amount,
                    }
                )
            answer = _outcome(receipts, rates)
            if not 1 <= len(answer["rejected"]) <= n - 2:
                continue
            decoys = _distinct(
                [
                    _outcome(receipts, rates, rounding="floor"),
                    _outcome(receipts, rates, rate_key="sdate"),
                    _outcome(receipts, rates, stale_caps=True),
                    _outcome(receipts, rates, total_round=True),
                ],
                answer,
            )
            if len(decoys) < 3:
                continue
            lines = ["id,receipt_date,submitted,category,currency,amount"]
            lines += [
                f"{r['id']},{r['rdate']},{r['sdate']},{r['cat']},{r['cur']},{r['amount']}"
                for r in receipts
            ]
            rate_lines = ["date,currency,eur_per_unit"]
            for d in RATE_DATES:
                for cur in BASE_RATES:
                    value = rates[(d, cur)]
                    rate_lines.append(f"{d},{cur},{value // 10000}.{value % 10000:04d}")
            return Built(
                question=QUESTION,
                files={
                    "receipts.csv": "\n".join(lines) + "\n",
                    "rates.csv": "\n".join(rate_lines) + "\n",
                    "policy.txt": POLICY,
                },
                fields={"rejected": Field("set"), "total_cents": Field("int")},
                answer=answer,
                decoys=decoys,
            )
        raise RuntimeError("off3: no valid instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        policy = files["policy.txt"]
        cutoff = re.search(r"From (\d{4}-\d{2}-\d{2})", policy).group(1)
        cats = ("meal", "taxi", "hotel", "train")
        before_row, from_row = re.findall(r"meal (\d+), taxi (\d+), hotel (\d+), train (\d+)", policy)
        cap_before = dict(zip(cats, (int(v) * 100 for v in before_row)))
        cap_from = dict(zip(cats, (int(v) * 100 for v in from_row)))
        rates = {}
        for row in csv.DictReader(io.StringIO(files["rates.csv"])):
            rates.setdefault(row["currency"], []).append((row["date"], Fraction(row["eur_per_unit"])))
        rejected = []
        total = 0
        for row in csv.DictReader(io.StringIO(files["receipts.csv"])):
            cur = row["currency"]
            if cur == "EUR":
                rate = Fraction(1)
            else:
                rate = max((d, r) for d, r in rates[cur] if d <= row["receipt_date"])[1]
            cents = math.floor(Fraction(row["amount"]) * rate * 100 + Fraction(1, 2))
            caps = cap_from if row["receipt_date"] >= cutoff else cap_before
            if cents > caps[row["category"]]:
                rejected.append(row["id"])
            else:
                total += cents
        return {"rejected": sorted(rejected), "total_cents": total}


FAMILY = ExpenseAudit()
