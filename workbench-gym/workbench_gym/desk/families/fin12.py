# SPDX-License-Identifier: Apache-2.0

"""
fin12: recover missing cells in a budget workbook (finance-economics).

``budget.xlsx`` has a Budget sheet (divisions by fiscal year, in $M, with a
Total row), a YoY Change (%) sheet and a Shares (%) sheet; level 2 adds a Growth
sheet (CAGR and average YoY change). Some cells hold "???". Every one of them
follows from the others through the sheets' own definitions, sometimes in a
chain (a missing total from its YoY change, then a missing division from that
total). The answer is the workbook saved under a new name with numbers in place
of every "???".

Decoys: YoY change computed against the later year, shares as fractions instead
of percent, CAGR over n years instead of n - 1, and a division recovered with
the share rule but no rounding to whole $M.
"""

import random
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, XlsxOut, must_match
from ._common import read_xlsx, xlsx_bytes

OUT = "budget_recovered.xlsx"
DIVISIONS = [
    "Science",
    "Aeronautics",
    "Exploration",
    "Space Operations",
    "Education",
    "Safety and Mission",
    "Technology",
    "Facilities",
    "Construction",
    "Agency Support",
]
MISSING = "???"
BUDGET, YOY, SHARES, GROWTH = "Budget", "YoY Change (%)", "Shares (%)", "Growth"


def _tables(budget: dict[str, list[int]], years: list[str], growth: bool) -> dict[str, dict]:
    """Every derived value from complete budgets: {sheet: {(row, col): value}}."""
    rows = list(budget)
    total = [sum(budget[r][t] for r in rows) for t in range(len(years))]
    full = dict(budget, Total=total)
    tables: dict[str, dict] = {BUDGET: {}, YOY: {}, SHARES: {}}
    for r, vals in full.items():
        for t, y in enumerate(years):
            tables[BUDGET][(r, y)] = vals[t]
            if t:
                tables[YOY][(r, y)] = (vals[t] / vals[t - 1] - 1) * 100
    for r in rows:
        for t, y in enumerate(years):
            tables[SHARES][(r, y)] = budget[r][t] / total[t] * 100
    if growth:
        tables[GROWTH] = {}
        n = len(years)
        for r, vals in full.items():
            tables[GROWTH][(r, "CAGR (%)")] = ((vals[-1] / vals[0]) ** (1 / (n - 1)) - 1) * 100
            yoys = [tables[YOY][(r, y)] for y in years[1:]]
            tables[GROWTH][(r, "Avg YoY (%)")] = sum(yoys) / len(yoys)
    return tables


def _sheet_rows(tables: dict, sheet: str, years: list[str], growth_cols: list[str]) -> list[list]:
    cells = tables[sheet]
    cols = growth_cols if sheet == GROWTH else (years[1:] if sheet == YOY else years)
    names = []
    for r, _ in cells:
        if r not in names:
            names.append(r)
    rows: list[list] = [["Division", *cols]]
    for r in names:
        rows.append([r, *[cells.get((r, c)) for c in cols]])
    return rows


def _col_letter(index: int) -> str:
    return "ABCDEFGHIJ"[index]


def _recover(sheets: dict[str, list[list]]) -> dict[str, dict]:
    """Fill every "???" from the sheet definitions. Returns {sheet: {(row, col): value}}."""
    grid: dict[str, dict] = {}
    for name, rows in sheets.items():
        header = [str(h) for h in rows[0]]
        grid[name] = {}
        for row in rows[1:]:
            for j, col in enumerate(header[1:], start=1):
                value = row[j]
                grid[name][(str(row[0]), col)] = None if value == MISSING else value
    budget, yoy, shares = grid[BUDGET], grid[YOY], grid[SHARES]
    growth = grid.get(GROWTH)
    years = [str(h) for h in sheets[BUDGET][0][1:]]
    divs = [str(r[0]) for r in sheets[BUDGET][1:] if str(r[0]) != "Total"]

    def known(*vals) -> bool:
        return all(v is not None for v in vals)

    for _ in range(12):
        for t, y in enumerate(years):
            col = [budget[(d, y)] for d in divs]
            tot = budget[("Total", y)]
            if tot is None and known(*col):
                budget[("Total", y)] = sum(col)
            missing = [d for d in divs if budget[(d, y)] is None]
            if len(missing) == 1 and tot is not None:
                budget[(missing[0], y)] = tot - sum(budget[(d, y)] for d in divs if d != missing[0])
            for r in [*divs, "Total"]:
                if t and budget[(r, y)] is None:
                    prev, ch = budget[(r, years[t - 1])], yoy[(r, y)]
                    if known(prev, ch):
                        budget[(r, y)] = round(prev * (1 + ch / 100))
                if t + 1 < len(years) and budget[(r, y)] is None:
                    nxt, ch = budget[(r, years[t + 1])], yoy[(r, years[t + 1])]
                    if known(nxt, ch):
                        budget[(r, y)] = round(nxt / (1 + ch / 100))
        for (r, y), v in yoy.items():
            if v is None:
                t = years.index(y)
                cur, prev = budget[(r, y)], budget[(r, years[t - 1])]
                if known(cur, prev):
                    yoy[(r, y)] = (cur / prev - 1) * 100
        for (r, y), v in shares.items():
            if v is None and known(budget[(r, y)], budget[("Total", y)]):
                shares[(r, y)] = budget[(r, y)] / budget[("Total", y)] * 100
        if growth is not None:
            for (r, c), v in growth.items():
                if v is not None:
                    continue
                vals = [budget[(r, y)] for y in years]
                if c.startswith("CAGR") and known(vals[0], vals[-1]):
                    growth[(r, c)] = ((vals[-1] / vals[0]) ** (1 / (len(years) - 1)) - 1) * 100
                elif c.startswith("Avg") and known(*[yoy[(r, y)] for y in years[1:]]):
                    ys = [yoy[(r, y)] for y in years[1:]]
                    growth[(r, c)] = sum(ys) / len(ys)
    return grid


def _ref(sheet: str, rows: list[list], row_name: str, col: str) -> str:
    header = [str(h) for h in rows[0]]
    i = next(k for k, r in enumerate(rows) if str(r[0]) == row_name)
    return f"{sheet}!{_col_letter(header.index(col))}{i + 1}"


class Fin12(DeskFamily):
    id = "fin12"
    domain = "finance-economics"
    title = "Recover missing budget cells"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        growth = level == 2
        n_years = rng.randint(5, 6)
        first = rng.randint(2012, 2019)
        years = [f"FY{first + i}" for i in range(n_years)]
        divs = rng.sample(DIVISIONS, rng.randint(5, 7))
        budget = {}
        for d in divs:
            vals = [rng.randint(300, 6000)]
            for _ in range(n_years - 1):
                vals.append(max(100, round(vals[-1] * (1 + rng.uniform(-0.08, 0.12)))))
            budget[d] = vals
        truth = _tables(budget, years, growth)
        gcols = ["CAGR (%)", "Avg YoY (%)"]
        sheets = {s: _sheet_rows(truth, s, years, gcols) for s in truth}

        # Choose the "???" cells.
        holes: list[tuple[str, str, str]] = []
        used_years: set[str] = set()
        for _ in range(rng.randint(2, 3)):
            y = rng.choice([y for y in years if y not in used_years])
            used_years.add(y)
            holes.append((BUDGET, rng.choice(divs), y))
        holes += [(YOY, rng.choice(divs), y) for y in rng.sample(years[1:], 2)]
        holes += [(SHARES, rng.choice(divs), y) for y in rng.sample(years, 2)]
        if level == 2:
            # A chain: a total from its YoY change, then a division from that total.
            y = rng.choice([y for y in years[1:] if y not in used_years])
            holes += [(BUDGET, "Total", y), (BUDGET, rng.choice(divs), y)]
            holes.append((GROWTH, rng.choice(divs), "CAGR (%)"))
            holes.append((GROWTH, rng.choice([*divs, "Total"]), "Avg YoY (%)"))
        holes = list(dict.fromkeys(holes))
        masked = {s: [list(r) for r in rows] for s, rows in sheets.items()}
        for sheet, r, c in holes:
            rows = masked[sheet]
            header = [str(h) for h in rows[0]]
            i = next(k for k, row in enumerate(rows) if str(row[0]) == r)
            rows[i][header.index(c)] = MISSING
        # The instance must be recoverable from the sheet definitions alone.
        got = _recover(masked)
        for sheet, r, c in holes:
            v = got[sheet][(r, c)]
            if v is None or abs(v - truth[sheet][(r, c)]) > 1e-6:
                return None

        def checks(values: dict) -> dict[str, tuple[Check, float]]:
            out = {}
            for sheet, r, c in holes:
                check = Check("num", tol=0.5) if sheet == BUDGET else Check("num", tol=0.01)
                out[_ref(sheet, sheets[sheet], r, c)] = (check, values[sheet][(r, c)])
            return out

        def workbook(values: dict) -> bytes:
            filled = {s: [list(r) for r in rows] for s, rows in masked.items()}
            for sheet, r, c in holes:
                rows = filled[sheet]
                header = [str(h) for h in rows[0]]
                i = next(k for k, row in enumerate(rows) if str(row[0]) == r)
                rows[i][header.index(c)] = values[sheet][(r, c)]
            return xlsx_bytes(filled)

        def variant(**kw) -> dict:
            wrong = {s: dict(v) for s, v in truth.items()}
            for sheet, r, c in holes:
                if sheet == YOY and kw.get("yoy_backwards"):
                    t = years.index(c)
                    cur, prev = budget_of(r, c), budget_of(r, years[t - 1])
                    wrong[sheet][(r, c)] = (prev / cur - 1) * 100
                if sheet == SHARES and kw.get("fractions"):
                    wrong[sheet][(r, c)] = truth[sheet][(r, c)] / 100
                if sheet == GROWTH and c.startswith("CAGR") and kw.get("cagr_n"):
                    vals = [budget_of(r, y) for y in years]
                    wrong[sheet][(r, c)] = ((vals[-1] / vals[0]) ** (1 / len(years)) - 1) * 100
                if sheet == BUDGET and kw.get("budget_off"):
                    wrong[sheet][(r, c)] = truth[sheet][(r, c)] + 7
            return wrong

        def budget_of(r: str, y: str) -> float:
            return truth[BUDGET][(r, y)]

        decoy_values = [
            variant(yoy_backwards=True),
            variant(fractions=True),
            variant(budget_off=True),
        ]
        if level == 2:
            decoy_values.append(variant(cagr_n=True))
        growth_text = (
            " The Growth sheet gives, per row, the compound annual growth rate from the first "
            "to the last fiscal year (CAGR (%), over the number of years minus one) and the "
            "average of that row's YoY changes (Avg YoY (%))."
            if growth
            else ""
        )
        instruction = (
            "Finance asked you to repair a damaged budget workbook before the board pack goes "
            "out. {root}/budget.xlsx has a Budget sheet (each division's budget per fiscal year "
            "in whole $M, plus a Total row that is the sum of the divisions), a YoY Change (%) "
            "sheet (change from the previous fiscal year, in percent) and a Shares (%) sheet "
            f"(each division's share of that year's Total, in percent).{growth_text} Some cells "
            'were lost and now hold the text "???". Every lost value can be worked out from the '
            "other cells with these definitions; some only after another lost value is found.\n\n"
            f"Replace every ??? with its number and save the workbook as {{root}}/{OUT} (same "
            "sheets, same layout). Write plain numbers, not Excel formulas: budgets as whole "
            "$M, percentages in percent units (4.27 means 4.27%) with at least 2 decimals."
        )
        return DeskTask(
            instruction=instruction,
            files={"budget.xlsx": xlsx_bytes(masked)},
            outputs=[XlsxOut(path=OUT, cells=checks(truth))],
            oracle={OUT: workbook(truth)},
            decoys=[{OUT: workbook(v)} for v in decoy_values],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"budget_recovered\.xlsx", instruction)
        data = files["budget.xlsx"]
        assert isinstance(data, bytes)
        sheets = read_xlsx(data)
        grid = _recover(sheets)
        filled = {}
        for name, rows in sheets.items():
            header = [str(h) for h in rows[0]]
            new = [list(rows[0])]
            for row in rows[1:]:
                new.append([row[0], *[grid[name][(str(row[0]), c)] for c in header[1:]]])
            filled[name] = new
        return {OUT: xlsx_bytes(filled)}


FAMILY = Fin12()
