# SPDX-License-Identifier: Apache-2.0

"""
fin11: net exports share of GDP by year (finance-economics).

``trade.xlsx`` (sheet Data) holds exports, imports and GDP per country and year, in bn
or mn, with a revision and a status. The instruction's steps drop EXCLUDED rows, keep the
highest revision, drop empty GDP cells and convert mn to bn. Each year gets the min, max,
median, mean, p25 and p75 of the net exports shares, and their GDP-weighted mean.

Decoys: the plain mean in the weighted column, exports and imports swapped, nearest-rank
percentiles; from level 2 also EXCLUDED rows kept, the first revision used, and mn GDP
used unconverted as a weight.
"""

import math
import random
from collections import Counter
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import read_xlsx, xlsx_bytes

OUT = "output/net_exports_by_year.csv"
HEADER = ("year", "min", "max", "median", "mean", "p25", "p75", "weighted_mean")
COLUMNS = (Check("text"), *([Check("num", tol=0.011)] * 7))
HEADER_IN = ["country", "year", "exports_usd", "imports_usd", "gdp", "unit", "rev", "status"]
COUNTRIES = (
    "DEU FRA ITA ESP NLD BEL SWE NOR IRL POL CZE AUT PRT GRC FIN DNK CHE KOR JPN VNM MYS "
    "THA IDN KEN GHA ZAF EGY MAR CHL PER"
).split()
INSTRUCTION = (
    "You are helping the macro desk prepare the net exports table for the annual outlook. "
    "{root}/trade.xlsx (sheet Data) has one row per country and year. Its columns: country "
    "(ISO3 code), year, exports_usd and imports_usd (exports and imports), gdp, unit (bn or "
    "mn: the unit of that row's exports_usd, imports_usd and gdp, billions or millions of US "
    "dollars), rev (revision number; a higher number is a later revision) and status (OK or "
    "EXCLUDED). A gdp cell may be empty.\n\n"
    "Apply these steps in this order:\n"
    "1. Drop every row whose status is EXCLUDED.\n"
    "2. For each country and year, keep the remaining row with the highest rev.\n"
    "3. Drop each country-year whose kept row has an empty gdp cell.\n"
    "4. For each kept row whose unit is mn, divide exports_usd, imports_usd and gdp by 1000.\n"
    "5. Net exports share (%) = (exports_usd - imports_usd) / gdp x 100, for each country-year.\n"
    "\n"
    "For each year, over the countries left in that year, compute the min, max, median, mean "
    "(a plain average of the shares), p25 and p75 of the shares. Percentiles use linear "
    "interpolation between sorted values (the numpy and pandas default); the median is the "
    "50th percentile. Also compute weighted_mean = sum(share x gdp) / sum(gdp) over the same "
    "countries, with gdp in bn.\n\n"
    "Write {root}/output/net_exports_by_year.csv (create the output folder if needed) with the "
    "exact header line year,min,max,median,mean,p25,p75,weighted_mean and one row per year, "
    "years ascending. Round every number to 2 decimals and write plain numbers."
)


def _economy(rng: random.Random) -> tuple[float, float, float]:
    """GDP, exports and imports of one country-year in bn, to the cent."""
    gdp = round(math.exp(rng.uniform(math.log(3.0), math.log(20000.0))), 2)
    exports = round(gdp * rng.uniform(0.25, 0.65), 2)
    imports = round(exports - gdp * rng.uniform(-0.14, 0.18), 2)
    return gdp, exports, imports


def _row(cell, econ, unit, rev, status, blank=False) -> list:
    """One input row. An mn row holds the bn values times 1000, one decimal kept."""
    gdp, exports, imports = econ
    scale, places = (1000, 1) if unit == "mn" else (1, 2)
    return [
        cell[0],
        cell[1],
        round(exports * scale, places),
        round(imports * scale, places),
        None if blank else round(gdp * scale, places),
        unit,
        rev,
        status,
    ]


def _kept(sheet: list[list], keep_excluded=False, first_rev=False) -> list[dict]:
    """The rows that enter the statistics, after steps 1 to 3 of the instruction."""
    names = [str(h).strip() for h in sheet[0]]
    body = [cells for cells in sheet[1:] if any(c is not None for c in cells)]
    rows = [dict(zip(names, cells, strict=False)) for cells in body]
    if not keep_excluded:
        rows = [r for r in rows if str(r["status"]).strip() != "EXCLUDED"]
    groups: dict[tuple[str, int], list[dict]] = {}
    for r in rows:
        groups.setdefault((str(r["country"]).strip(), int(r["year"])), []).append(r)
    pick = min if first_rev else max
    kept = [pick(group, key=lambda r: int(r["rev"])) for group in groups.values()]
    return [r for r in kept if r["gdp"] not in (None, "")]


def _pct(values: list[float], q: float, nearest_rank: bool = False) -> float:
    """Percentile q (0-100) of sorted values: linear interpolation, or nearest rank."""
    if nearest_rank:
        return values[max(0, math.ceil(q / 100 * len(values)) - 1)]
    pos = (len(values) - 1) * q / 100
    lo = math.floor(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _table(sheet: list[list], decoy: str = "") -> list[list]:
    """The answer table, or a decoy: plain, swap, nearest, keep, first or raw."""
    years: dict[int, list[tuple[float, float]]] = {}
    for r in _kept(sheet, decoy == "keep", decoy == "first"):
        scale = 0.001 if str(r["unit"]).strip() == "mn" else 1.0
        exports, imports, gdp = (float(r[k]) * scale for k in ("exports_usd", "imports_usd", "gdp"))
        sign = -1 if decoy == "swap" else 1
        share = sign * (exports - imports) / gdp * 100
        weight = float(r["gdp"]) if decoy == "raw" else gdp
        years.setdefault(int(r["year"]), []).append((share, weight))
    near = decoy == "nearest"
    table: list[list] = []
    for year in sorted(years):
        pairs = years[year]
        shares = sorted(s for s, _ in pairs)
        n = len(shares)
        if decoy == "plain":
            weighted = sum(shares) / n
        else:
            weighted = sum(s * w for s, w in pairs) / sum(w for _, w in pairs)
        stats = [shares[0], shares[-1], _pct(shares, 50, near), sum(shares) / n]
        stats += [_pct(shares, 25, near), _pct(shares, 75, near), weighted]
        table.append([str(year), *(round(v, 2) for v in stats)])
    return table


def _csv_text(table: list[list]) -> str:
    rows = [",".join([str(row[0]), *(f"{v:.2f}" for v in row[1:])]) for row in table]
    return "\n".join([",".join(HEADER), *rows]) + "\n"


def _gap(a: list[list], b: list[list]) -> float:
    """Largest difference between two tables (1e9 when their years differ)."""
    if len(a) != len(b) or any(x[0] != y[0] for x, y in zip(a, b, strict=True)):
        return 1e9
    return max(
        abs(u - v) for x, y in zip(a, b, strict=True) for u, v in zip(x[1:], y[1:], strict=True)
    )


class Fin11(DeskFamily):
    id = "fin11"
    domain = "finance-economics"
    title = "Net exports share of GDP by year"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        trap = level == 2
        n_years = rng.randint(8, 11) if trap else rng.randint(6, 8)
        n_countries = rng.randint(14, 20) if trap else rng.randint(10, 14)
        first = rng.randint(2008, 2016)
        years = [first + i for i in range(n_years)]
        countries = rng.sample(COUNTRIES, n_countries)
        keep = 0.8 if trap else 0.9
        cells = [(c, y) for y in years for c in countries if rng.random() < keep]
        rng.shuffle(cells)
        n_revised = rng.randint(4, 7) if trap else 0
        revised = set(cells[:n_revised])
        excluded = set(cells[n_revised : n_revised + 3]) if trap else set()
        blanks = set(cells[n_revised + 3 : n_revised + 6]) if trap else set()
        rows: list[list] = []
        for cell in cells:
            econ = _economy(rng)
            unit = "mn" if trap and rng.random() < 0.3 else "bn"
            status = "EXCLUDED" if cell in excluded else "OK"
            rows.append(_row(cell, econ, unit, 1, status, cell in blanks))
            if cell in revised:
                factors = [1 + rng.uniform(-0.04, 0.04) for _ in econ]
                revision = tuple(round(v * f, 2) for v, f in zip(econ, factors, strict=True))
                unit2 = "mn" if rng.random() < 0.3 else "bn"
                rows.append(_row(cell, revision, unit2, 2, "OK"))
        rng.shuffle(rows)
        sheet = [HEADER_IN, *rows]
        counts = Counter(int(r["year"]) for r in _kept(sheet))
        if len(counts) != n_years or min(counts.values()) < 3:
            return None
        truth = _table(sheet)
        variants = ["plain", "swap", "nearest"] + (["keep", "first", "raw"] if trap else [])
        decoys = [_table(sheet, v) for v in variants]
        if any(_gap(truth, d) <= 0.05 for d in decoys):
            return None
        out = CsvOut(path=OUT, header=HEADER, columns=COLUMNS, rows=tuple(map(tuple, truth)), key=0)
        return DeskTask(
            instruction=INSTRUCTION,
            files={"trade.xlsx": xlsx_bytes({"Data": sheet})},
            outputs=[out],
            oracle={OUT: _csv_text(truth)},
            decoys=[{OUT: _csv_text(d)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"net_exports_by_year\.csv", instruction)
        data = files["trade.xlsx"]
        assert isinstance(data, bytes)
        return {OUT: _csv_text(_table(read_xlsx(data)["Data"]))}


FAMILY = Fin11()
