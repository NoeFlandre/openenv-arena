# SPDX-License-Identifier: Apache-2.0

"""
off1: contact merge, field by field (office white-collar).

``contacts.csv`` holds rows from several sources for several people. For one
person, every field is merged on its own: the non-empty value with the latest
date wins, and a tie on date goes to the higher-ranked source. Copying the newest
whole row, ranking sources before dates, breaking ties by file order, or taking
the oldest value each gives a different record.
"""

import csv
import io
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
COUNTS = {1: 3, 2: 5, 3: 7}
FILL = 0.6
MAX_TRIES = 400

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


def _row(person, profile, fill, rng):
    def maybe(make):
        return make() if rng.random() < fill else ""

    return {
        "person_id": person,
        "source": rng.choice(SOURCE_ORDER),
        "date": rng.choice(DATES),
        "name": maybe(lambda: rng.choice(profile["names"])),
        "email": maybe(lambda: f"{rng.choice(profile['locals'])}@{rng.choice(DOMAINS)}"),
        "phone": maybe(
            lambda: "+33 " + rng.choice("67") + " " + " ".join(f"{rng.randint(0, 99):02d}" for _ in range(4))
        ),
        "company": maybe(lambda: rng.choice(COMPANIES)),
        "city": maybe(lambda: rng.choice(CITIES)),
    }


def _latest_then_rank(cands):
    return max(cands, key=lambda r: (r["date"], RANK[r["source"]]))


def _rank_then_latest(cands):
    return max(cands, key=lambda r: (RANK[r["source"]], r["date"]))


def _first_in_file_latest(cands):
    top = max(r["date"] for r in cands)
    return next(r for r in cands if r["date"] == top)


def _oldest(cands):
    return min(cands, key=lambda r: r["date"])


def _pick(rows, field, choose):
    cands = [r for r in rows if r[field]]
    return choose(cands)[field] if cands else ""


def _tie_matters(rows):
    for f in FIELDS:
        cands = [r for r in rows if r[f]]
        if not cands:
            continue
        top = max(r["date"] for r in cands)
        if len({r[f] for r in cands if r["date"] == top}) > 1:
            return True
    return False


def _distinct(candidates, answer):
    out = []
    for cand in candidates:
        if cand != answer and cand not in out:
            out.append(cand)
    return out


class ContactMerge(Family):
    id = "off1"
    domain = "office-white-collar"
    title = "Contact merge"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(MAX_TRIES):
            target = [_row(TARGET, TARGET_PROFILE, FILL, rng) for _ in range(COUNTS[level])]
            if len({(r["date"], r["source"]) for r in target}) < len(target):
                continue
            others = [_row(OTHER, OTHER_PROFILE, 0.9, rng) for _ in range(rng.randint(2, 4))]
            rows = target + others
            rng.shuffle(rows)
            mine = [r for r in rows if r["person_id"] == TARGET]
            merged = {f: _pick(mine, f, _latest_then_rank) for f in FIELDS}
            if sum(1 for f in FIELDS if merged[f]) < 4 or not _tie_matters(mine):
                continue
            latest = max(mine, key=lambda r: r["date"])
            answer = {"merged": merged}
            decoys = _distinct(
                [
                    {"merged": {f: latest[f] for f in FIELDS}},
                    {"merged": {f: _pick(mine, f, _rank_then_latest) for f in FIELDS}},
                    {"merged": {f: _pick(mine, f, _first_in_file_latest) for f in FIELDS}},
                    {"merged": {f: _pick(mine, f, _oldest) for f in FIELDS}},
                ],
                answer,
            )
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
