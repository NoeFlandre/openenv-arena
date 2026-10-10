# SPDX-License-Identifier: Apache-2.0

"""
off1: contact merge, field by field (office white-collar).

``contacts.csv`` holds rows from several sources for several people. For one
person, every field is merged on its own: the non-empty value with the latest
date wins, and a tie on date goes to the higher-ranked source. Recency alone,
source rank alone, file order alone, the oldest value, a majority vote and
copying one whole row each give a different record.

Each instance has a batch of four rows, one per source, that share the newest
date (one sync that touched the record from every source), and older rows that
carry values from higher-ranked sources. Four tied sources matter: a fixed
source order that differs from the documented one in any pair of sources is
wrong on some field, because the pair is compared on some field. The builder
rejects any instance where one of the simple rules below would still give the
right record, so each such rule is wrong on at least one field.
"""

import csv
import io
import itertools
import random
import re

from ..core.grading import Field
from .base import Built, Family

FIELDS = ("name", "email", "phone", "company", "city")
COLUMNS = ("person_id", "source", "date", "name", "email", "phone", "company", "city")
SOURCE_ORDER = ("crm", "web", "import", "card")
RANK = {s: len(SOURCE_ORDER) - i for i, s in enumerate(SOURCE_ORDER)}
DATES = ("2026-01-14", "2026-02-27", "2026-04-09", "2026-05-22", "2026-07-03", "2026-08-18", "2026-09-30")
DOMAINS = ("helixlabs.eu", "gmail.com", "outlook.fr", "vellum.fr")
COMPANIES = ("Helix Labs", "Helix Labs SAS", "Vellum Works", "Orca Health", "Northgate Partners", "Brightwell")
CITIES = ("Lyon", "Lille", "Nantes", "Grenoble", "Bordeaux", "Rennes", "Paris")
TARGET = "P-5083"
OTHER = "P-2217"
TARGET_PROFILE = {
    "names": ("Ana Ferreira", "Ana Ferreira-Lopez", "Ana F. Lopez", "Ana Lopez", "A. Ferreira"),
    "locals": ("ana.ferreira", "ana.lopez", "ana.f", "a.ferreira"),
}
OTHER_PROFILE = {
    "names": ("Ana Ferrer", "Ana Ferrari"),
    "locals": ("ana.ferrer", "a.ferrari"),
}
COUNTS = {1: 5, 2: 6, 3: 8}
BATCH = 4
FILL_BATCH = 0.75
FILL = 0.6
MAX_TRIES = 4000
SOURCE_PERMS = tuple(itertools.permutations(SOURCE_ORDER))
DATE_MODES = ("latest", "oldest", "any")
SIMPLE_TIES = ("first", "last", "longest", "shortest", "alpha_hi", "alpha_lo") + SOURCE_PERMS
DOCUMENTED = ("latest", SOURCE_ORDER)

RULES = (
    "Contact merge, rev 4 (current). Merge the rows of one person_id.\n"
    "1. Merge each field on its own. Never copy a whole row.\n"
    "2. For a field, take the non-empty value from the row with the latest date.\n"
    "3. If two non-empty values share the latest date, take the one from the higher source.\n"
    "4. Source rank, highest first: crm, web, import, card.\n"
    "5. A field that no row fills is an empty string.\n"
    "Output keys: name, email, phone, company, city.\n"
)
QUESTION = (
    "contacts.csv has rows for several people. Merge the rows for person P-5083 using "
    "merge_rules.txt. Set merged to an object with keys name, email, phone, company, city."
)


def _row(person, profile, fill, rng, source=None, date=None):
    def maybe(make):
        return make() if rng.random() < fill else ""

    return {
        "person_id": person,
        "source": source or rng.choice(SOURCE_ORDER),
        "date": date or rng.choice(DATES),
        "name": maybe(lambda: rng.choice(profile["names"])),
        "email": maybe(lambda: f"{rng.choice(profile['locals'])}@{rng.choice(DOMAINS)}"),
        "phone": maybe(
            lambda: "+33 " + rng.choice("67") + " " + " ".join(f"{rng.randint(0, 99):02d}" for _ in range(4))
        ),
        "company": maybe(lambda: rng.choice(COMPANIES)),
        "city": maybe(lambda: rng.choice(CITIES)),
    }


def _target_rows(n, rng):
    newest = rng.choice(DATES[3:])
    older = DATES[: DATES.index(newest)]
    rows = [_row(TARGET, TARGET_PROFILE, FILL_BATCH, rng, source=s, date=newest) for s in rng.sample(SOURCE_ORDER, BATCH)]
    rows += [_row(TARGET, TARGET_PROFILE, FILL, rng, date=rng.choice(older)) for _ in range(n - BATCH)]
    return rows


def _pool(rows, date_mode):
    """Rows that a date rule keeps: the latest, the oldest, or all of them."""
    if date_mode == "latest":
        top = max(r["date"] for r in rows)
        return [r for r in rows if r["date"] == top]
    if date_mode == "oldest":
        low = min(r["date"] for r in rows)
        return [r for r in rows if r["date"] == low]
    return rows


def _priority_pick(pool, order):
    """The row whose source ranks highest in ``order``. Equal sources fall to file order."""
    ranks = {s: len(order) - i for i, s in enumerate(order)}
    return max(pool, key=lambda r: ranks[r["source"]])


def _choose(pool, field, tie):
    if tie == "first":
        return pool[0]
    if tie == "last":
        return pool[-1]
    if tie == "longest":
        return max(pool, key=lambda r: len(r[field]))
    if tie == "shortest":
        return min(pool, key=lambda r: len(r[field]))
    if tie == "alpha_hi":
        return max(pool, key=lambda r: r[field])
    if tie == "alpha_lo":
        return min(pool, key=lambda r: r[field])
    return _priority_pick(pool, tie)


def _field_pick(rows, field, date_mode, tie):
    """One field under a simple rule. ``tie`` is a tie-break name or a fixed source order."""
    cands = [r for r in rows if r[field]]
    if not cands:
        return ""
    return _choose(_pool(cands, date_mode), field, tie)[field]


def _field_rank_date(rows, field):
    cands = [r for r in rows if r[field]]
    return max(cands, key=lambda r: (RANK[r["source"]], r["date"]))[field] if cands else ""


def _majority(rows, field):
    values = [r[field] for r in rows if r[field]]
    if not values:
        return ""
    return max(values, key=lambda v: (values.count(v), -values.index(v)))


def _whole_row(rows, date_mode, tie):
    """A whole row copied from the file. Empty cells are copied too."""
    return _choose(_pool(rows, date_mode), "source", tie)


def _simple_rules(rows):
    """Yield (name, merged) for every simple merge rule the builder checks. DOCUMENTED is one of them."""
    for date_mode in DATE_MODES:
        for tie in SIMPLE_TIES:
            yield (date_mode, tie), {"merged": {f: _field_pick(rows, f, date_mode, tie) for f in FIELDS}}
    yield ("any", "rank_date"), {"merged": {f: _field_rank_date(rows, f) for f in FIELDS}}
    yield ("majority", None), {"merged": {f: _majority(rows, f) for f in FIELDS}}
    for date_mode in DATE_MODES:
        for tie in ("first", "last") + SOURCE_PERMS:
            row = _whole_row(rows, date_mode, tie)
            yield ("row", date_mode, tie), {"merged": {f: row[f] for f in FIELDS}}
    rank_date_row = max(rows, key=lambda r: (RANK[r["source"]], r["date"]))
    yield ("row", "any", "rank_date"), {"merged": {f: rank_date_row[f] for f in FIELDS}}


def _tie_matters(rows):
    for f in FIELDS:
        cands = [r for r in rows if r[f]]
        if not cands:
            continue
        top = max(r["date"] for r in cands)
        if len({r[f] for r in cands if r["date"] == top}) > 1:
            return True
    return False


class ContactMerge(Family):
    id = "off1"
    domain = "office-white-collar"
    title = "Contact merge"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(MAX_TRIES):
            mine = _target_rows(COUNTS[level], rng)
            if len({(r["date"], r["source"]) for r in mine}) < len(mine):
                continue
            others = [_row(OTHER, OTHER_PROFILE, 0.9, rng) for _ in range(rng.randint(2, 4))]
            rows = mine + others
            rng.shuffle(rows)
            mine = [r for r in rows if r["person_id"] == TARGET]
            merged = {f: _field_pick(mine, f, *DOCUMENTED) for f in FIELDS}
            if sum(1 for f in FIELDS if merged[f]) < 4 or not _tie_matters(mine):
                continue
            answer = {"merged": merged}
            # Reject any instance that a simple rule still solves. The check stops at the first match.
            if any(value == answer for name, value in _simple_rules(mine) if name != DOCUMENTED):
                continue
            decoys: list[dict] = []
            for name, value in _simple_rules(mine):
                if name != DOCUMENTED and value not in decoys:
                    decoys.append(value)
            if len(decoys) < 3:
                continue
            lines = [",".join(COLUMNS)]
            lines += [",".join(r[k] for k in COLUMNS) for r in rows]
            return Built(
                question=QUESTION,
                files={
                    "contacts.csv": "\n".join(lines) + "\n",
                    "merge_rules.txt": RULES,
                },
                fields={"merged": Field("object")},
                answer=answer,
                decoys=decoys,
            )
        raise RuntimeError("off1: no valid instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        person = re.search(r"P-\d{4}", question).group(0)
        order = re.search(r"highest first: ([a-z, ]+)\.", files["merge_rules.txt"]).group(1).split(", ")
        rank = {s: len(order) - i for i, s in enumerate(order)}
        rows = [
            row
            for row in csv.DictReader(io.StringIO(files["contacts.csv"]))
            if row["person_id"] == person
        ]
        merged = {}
        for f in ("name", "email", "phone", "company", "city"):
            cands = [row for row in rows if row[f] != ""]
            if not cands:
                merged[f] = ""
                continue
            best = max(cands, key=lambda row: (row["date"], rank[row["source"]]))
            merged[f] = best[f]
        return {"merged": merged}


FAMILY = ContactMerge()
