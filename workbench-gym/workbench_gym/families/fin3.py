# SPDX-License-Identifier: Apache-2.0

"""
fin3: accounting formats (finance-economics).

``ledger.txt`` is an export with mixed amount formats: plain "1,234.50",
negatives in parentheses "(1,234.50)" and negatives with a trailing minus
"87.00-". Each row is in its own currency. ``rates.txt`` gives units of currency
per 1 EUR on business days only, so weekend and holiday rows have no rate of
their own. ``policy.txt`` says to use the most recent earlier rate for such a
row, divide, round each row to the cent (half away from zero), then add.

Decoys: parentheses and trailing minus read as positive, the next rate instead
of the previous one, multiplying instead of dividing, and rows on days without
a rate dropped.
"""

import datetime
import math
import random
import re
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family

ROWS = {1: 10, 2: 20, 3: 30}
WINDOW_DAYS = 14
START = datetime.date(2026, 7, 1)
RATE_RANGE = {"USD": (10500, 12000), "GBP": (8200, 9000)}  # ten-thousandths of a unit per EUR
REF_PREFIX = ("INV", "PMT", "CRN")
ACCOUNTS = ("Services", "Freight", "Supplies", "Refund", "Bank")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROW = re.compile(r"^(\d{4}-\d{2}-\d{2}) \S+ \S+ (\S+) ([A-Z]{3})$")


def _round(value: Fraction) -> int:
    """Round half away from zero to a whole cent."""
    sign = -1 if value < 0 else 1
    return sign * math.floor(abs(value) + Fraction(1, 2))


def _amount(token: str) -> Fraction:
    """Signed cents from an export token: plain, (parentheses) or trailing minus."""
    if token.startswith("(") and token.endswith(")"):
        return -Fraction(token[1:-1].replace(",", "")) * 100
    if token.endswith("-"):
        return -Fraction(token[:-1].replace(",", "")) * 100
    return Fraction(token.replace(",", "")) * 100


def _money(cents: int) -> str:
    whole, frac = divmod(abs(cents), 100)
    return f"{whole:,}.{frac:02d}"


def _net(rows: list[dict], rates: dict[str, dict[str, int]], mode: str) -> int:
    """Net EUR cents under one rule set. ``correct`` is the policy; the rest are decoys."""
    total = 0
    for row in rows:
        cents = row["cents"]
        if mode == "positive":
            cents = abs(cents)
        if row["ccy"] == "EUR":
            total += cents
            continue
        if mode == "drop" and row["date"] not in rates:
            continue
        if mode == "next":
            key = min(d for d in rates if d >= row["date"])
        else:
            key = max(d for d in rates if d <= row["date"])
        rate = Fraction(rates[key][row["ccy"]], 10000)
        if mode == "multiply":
            total += _round(Fraction(cents) * rate)
        else:
            total += _round(Fraction(cents) / rate)
    return total


class LedgerFormats(Family):
    id = "fin3"
    domain = "finance-economics"
    title = "Accounting formats"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(300):
            built = self._attempt(level, rng)
            if built is not None:
                return built
        raise AssertionError(f"fin3 level {level}: no instance found")

    def _attempt(self, level: int, rng: random.Random) -> Built | None:
        n = ROWS[level]
        base = {c: rng.randint(lo, hi) for c, (lo, hi) in RATE_RANGE.items()}
        rates: dict[str, dict[str, int]] = {}
        day = START - datetime.timedelta(days=4)
        end = START + datetime.timedelta(days=WINDOW_DAYS + 3)
        while day <= end:
            if day.weekday() < 5:
                for c, (lo, hi) in RATE_RANGE.items():
                    base[c] = min(hi, max(lo, base[c] + rng.randint(-60, 60)))
                rates[day.isoformat()] = dict(base)
            day += datetime.timedelta(days=1)
        window = [
            (START + datetime.timedelta(days=k)).isoformat()
            for k in range(1, WINDOW_DAYS)
            if (START + datetime.timedelta(days=k)).weekday() < 5
        ]
        del rates[rng.choice(window)]  # a holiday: no rate published

        refs = rng.sample(range(1000, 9999), n)
        rows: list[dict] = []
        for num in refs:
            day_i = (START + datetime.timedelta(days=rng.randrange(WINDOW_DAYS))).isoformat()
            ccy = rng.choice(["USD", "GBP", "EUR", "EUR"])
            cents = rng.randint(5000, 250000)
            negative = rng.random() < 0.3
            style = rng.choice(["paren", "trail"])
            signed = -cents if negative else cents
            if not negative:
                token = _money(cents)
            elif style == "paren":
                token = f"({_money(cents)})"
            else:
                token = f"{_money(cents)}-"
            rows.append(
                {
                    "date": day_i,
                    "ref": f"{rng.choice(REF_PREFIX)}-{num:04d}",
                    "account": rng.choice(ACCOUNTS),
                    "cents": signed,
                    "ccy": ccy,
                    "token": token,
                }
            )
        rows.sort(key=lambda r: (r["date"], r["ref"]))
        if not any(r["cents"] < 0 for r in rows):
            return None
        if all(r["date"] in rates for r in rows if r["ccy"] != "EUR"):
            return None

        want = _net(rows, rates, "correct")
        decoys: list[dict] = []
        for mode in ("positive", "next", "multiply", "drop"):
            cand = {"net_cents": _net(rows, rates, mode)}
            if cand["net_cents"] != want and cand not in decoys:
                decoys.append(cand)
        if len(decoys) < 3:
            return None

        ledger = "Export 2026-Q3, amounts in row currency\n"
        ledger += "date ref account amount ccy\n"
        for r in rows:
            ledger += f"{r['date']} {r['ref']} {r['account']} {r['token']} {r['ccy']}\n"
        rate_lines = "Reference rates, units of currency per 1 EUR, business days only\n"
        for day_s in sorted(rates):
            usd = rates[day_s]["USD"]
            gbp = rates[day_s]["GBP"]
            rate_lines += (
                f"{day_s} USD {usd // 10000}.{usd % 10000:04d} GBP {gbp // 10000}.{gbp % 10000:04d}\n"
            )
        policy = (
            "FX and sign rules, export 2026-Q3\n"
            "1. Base currency is EUR. Each row is in its own currency. EUR rows need no rate.\n"
            "2. rates.txt gives units of currency per 1 EUR. EUR = amount / rate.\n"
            "3. A row whose day has no rate (weekend, holiday) uses the most recent earlier rate.\n"
            "4. Parentheses or a trailing minus mean a negative amount.\n"
            "5. Round each row to the cent, half away from zero, then add the rows.\n"
        )
        return Built(
            question=(
                "Convert every row of ledger.txt to EUR under policy.txt. "
                "What is the net total in EUR cents?"
            ),
            files={"ledger.txt": ledger, "rates.txt": rate_lines, "policy.txt": policy},
            fields={"net_cents": Field("int")},
            answer={"net_cents": want},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        rates: dict[str, dict[str, Fraction]] = {}
        for line in files["rates.txt"].split("\n"):
            parts = line.split()
            if len(parts) >= 3 and ISO.match(parts[0]):
                pairs = parts[1:]
                rates[parts[0]] = {
                    pairs[i]: Fraction(pairs[i + 1]) for i in range(0, len(pairs) - 1, 2)
                }
        total = 0
        for line in files["ledger.txt"].split("\n"):
            match = ROW.match(line.strip())
            if match is None:
                continue
            day, token, ccy = match.groups()
            cents = _amount(token)
            if ccy == "EUR":
                total += _round(cents)
                continue
            earlier = [d for d in rates if d <= day and ccy in rates[d]]
            rate = rates[max(earlier)][ccy]
            total += _round(cents / rate)
        return {"net_cents": total}


FAMILY = LedgerFormats()
