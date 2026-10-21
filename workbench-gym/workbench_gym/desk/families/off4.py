# SPDX-License-Identifier: Apache-2.0

"""
off4: quarterly sales pivot from an Excel workbook (office-white-collar).

``sales.xlsx`` has an "orders" sheet. Revenue of an order is units times
unit_price. For 2025 only: OK orders add, RETURNED orders subtract, CANCELLED
orders are left out. Level 2 adds a "price_corrections" sheet that overrides the
unit price of some orders. The answer is one row per region with the revenue of
each quarter and the total, sorted by total.

Decoys: counting cancelled orders, adding returns, taking every year, and
ignoring the price corrections.
"""

import random
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import csv_text, read_xlsx, xlsx_bytes

OUT = "output/sales_pivot.csv"
HEADER = ["region", "Q1", "Q2", "Q3", "Q4", "total"]
REGIONS = ["North", "South", "East", "West", "Central"]
PRODUCTS = ["Desk", "Chair", "Lamp", "Shelf", "Cabinet", "Rug"]
ORDER_HEADER = ["order_id", "order_date", "region", "product", "units", "unit_price", "status"]


def _pivot(
    orders: list[list],
    corrections: dict[str, int] | None,
    year: str = "2025",
    skip_cancelled: bool = True,
    returns_negative: bool = True,
) -> list[list]:
    """Rows of [region, Q1..Q4, total] in cents-exact arithmetic, shown in dollars."""
    cells: dict[tuple[str, int], int] = {}
    for order_id, date, region, _, units, unit_price, status in orders:
        if not str(date).startswith(year):
            continue
        if skip_cancelled and status == "CANCELLED":
            continue
        price = corrections.get(order_id, unit_price) if corrections else unit_price
        cents = int(units) * int(price)
        if status == "RETURNED":
            cents = -cents if returns_negative else cents
        quarter = (int(str(date)[5:7]) - 1) // 3 + 1
        cells[(region, quarter)] = cells.get((region, quarter), 0) + cents
    rows = []
    for region in sorted({r for r, _ in cells} | {r for r, _ in cells}):
        quarters = [cells.get((region, q), 0) for q in range(1, 5)]
        total = sum(quarters)
        rows.append([region, *[f"{c / 100:.2f}" for c in quarters], f"{total / 100:.2f}"])
    rows.sort(key=lambda r: -float(r[5]))
    return rows


class Off4(DeskFamily):
    id = "off4"
    domain = "office-white-collar"
    title = "Quarterly sales pivot from a workbook"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        n = 170 if level == 1 else 300
        regions = rng.sample(REGIONS, 4)
        orders: list[list] = []
        for i in range(n):
            year = "2025" if rng.random() < 0.85 else "2024"
            date = f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            status = rng.choices(["OK", "RETURNED", "CANCELLED"], [80, 10, 10])[0]
            orders.append(
                [
                    f"SO-{10000 + i}",
                    date,
                    rng.choice(regions),
                    rng.choice(PRODUCTS),
                    rng.randint(1, 40),
                    rng.randint(500, 20000),
                    status,
                ]
            )
        corrections = None
        correction_rows: list[list] = []
        if level == 2:
            for row in rng.sample(orders, k=n // 6):
                new_price = rng.randint(500, 20000)
                correction_rows.append([row[0], new_price])
            corrections = {r[0]: r[1] for r in correction_rows}

        truth = _pivot(orders, corrections)
        decoys = [
            _pivot(orders, corrections, skip_cancelled=False),
            _pivot(orders, corrections, returns_negative=False),
            _pivot(orders, corrections, year=""),
        ]
        if level == 2:
            decoys.append(_pivot(orders, None))
        if any(d == truth for d in decoys) or len(truth) < 3:
            return None

        sheets = {"orders": [ORDER_HEADER, *orders]}
        if level == 2:
            sheets["price_corrections"] = [["order_id", "unit_price"], *correction_rows]
        data = xlsx_bytes(sheets)
        extra = (
            " The sheet price_corrections gives a new unit_price in cents for some orders; use it "
            "instead of the price in the orders sheet for those orders."
            if level == 2
            else ""
        )
        instruction = (
            "Finance wants the 2025 quarterly revenue by region for the board pack. "
            "{root}/sales.xlsx has "
            "an orders sheet with order_id, order_date (text, YYYY-MM-DD), region, product, units, "
            "unit_price (in cents) and status (OK, RETURNED or CANCELLED)." + extra + "\n\nRules:\n"
            "1. Only orders dated in 2025 count. Quarter 1 is January to March, and so on.\n"
            "2. Revenue of an order = units x unit_price, in cents.\n"
            "3. OK orders add their revenue. RETURNED orders subtract it. CANCELLED orders count "
            "nothing.\n\n"
            "Output: a CSV at {root}/output/sales_pivot.csv with the exact header line "
            "region,Q1,Q2,Q3,Q4,total, one row per region, sorted by total from highest to lowest. "
            "Amounts are dollars with 2 decimal places (divide cents by 100); total is the sum of "
            "the four "
            "quarters. Create the output folder if needed."
        )
        checks = [Check("text")] + [Check("num", tol=0.011)] * 5
        return DeskTask(
            instruction=instruction,
            files={"sales.xlsx": data},
            outputs=[
                CsvOut(
                    path=OUT,
                    header=tuple(HEADER),
                    columns=tuple(checks),
                    rows=tuple(tuple(r[:1] + [float(x) for x in r[1:]]) for r in truth),
                    key=0,
                )
            ],
            oracle={OUT: csv_text(truth, HEADER)},
            decoys=[{OUT: csv_text(d, HEADER)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"sales_pivot\.csv", instruction)
        data = files["sales.xlsx"]
        assert isinstance(data, bytes)
        sheets = read_xlsx(data)
        orders = [list(r) for r in sheets["orders"][1:]]
        corrections = None
        if "price_corrections" in sheets:
            corrections = {str(r[0]): int(r[1]) for r in sheets["price_corrections"][1:]}
        return {OUT: csv_text(_pivot(orders, corrections), HEADER)}


FAMILY = Off4()
