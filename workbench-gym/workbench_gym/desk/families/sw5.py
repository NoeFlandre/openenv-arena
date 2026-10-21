# SPDX-License-Identifier: Apache-2.0

"""
sw5: dependency vulnerability audit of a lock file (software-engineering).

``requirements.lock`` pins packages (name==version). ``advisories.json`` lists
advisories with an affected range and a fixed version. A pin is vulnerable when
its version lies in an affected range. Names are compared after PEP 503
normalization, versions numerically segment by segment, and pre-releases are
lower than their release. Level 2 adds extras in brackets, pre-release pins,
several ranges joined by "||", and withdrawn advisories (ignored).

Decoys: comparing versions as text, using only the first range, counting
withdrawn advisories, and matching names exactly.
"""

import json
import random
import re
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import csv_text

OUT = "output/vulnerable.csv"
HEADER = ["package", "installed", "advisory_id", "fixed_in"]
PRE = re.compile(r"^(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?$")
CONDITION = re.compile(r"^(>=|<=|==|!=|>|<)(.+)$")
NAMES = [
    "requests",
    "urllib3",
    "pyyaml",
    "jinja2",
    "python-dateutil",
    "django",
    "cryptography",
    "pillow",
    "google-auth",
    "lxml",
    "sqlalchemy",
    "flask-login",
    "paramiko",
    "idna",
    "markupsafe",
]


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _key(version: str, pre_rank: bool) -> tuple:
    match = PRE.match(version)
    if not match:
        raise ValueError(version)
    release = tuple(int(x) for x in match.group(1).split("."))
    if not pre_rank:
        return release, 0, 0
    if match.group(2):
        return release, 0, ({"a": 1, "b": 2, "rc": 3}[match.group(2)], int(match.group(3)))
    return release, 1, (0, 0)


def _compare(a: str, b: str) -> int:
    ka, kb = _key(a, True), _key(b, True)
    width = max(len(ka[0]), len(kb[0]))
    ra = ka[0] + (0,) * (width - len(ka[0]))
    rb = kb[0] + (0,) * (width - len(kb[0]))
    if ra != rb:
        return -1 if ra < rb else 1
    if ka[1:] != kb[1:]:
        return -1 if ka[1:] < kb[1:] else 1
    return 0


def _in_range(version: str, clause: str, textual: bool) -> bool:
    for cond in clause.split(","):
        m = CONDITION.match(cond.strip())
        if not m:
            return False
        op, bound = m.group(1), m.group(2).strip()
        if textual:
            c = (version > bound) - (version < bound)
        else:
            c = _compare(version, bound)
        ok = {">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0, "==": c == 0, "!=": c != 0}[op]
        if not ok:
            return False
    return True


def _audit(
    lock_text: str,
    advisories: list[dict],
    first_range_only: bool = False,
    keep_withdrawn: bool = False,
    textual: bool = False,
    exact_names: bool = False,
) -> list[list]:
    pins = []
    for line in lock_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        name = re.sub(r"\[.*\]", "", name).strip()
        pins.append((name, version.strip()))
    rows = []
    for adv in advisories:
        if adv.get("withdrawn") and not keep_withdrawn:
            continue
        ranges = adv["affected"].split("||")
        if first_range_only:
            ranges = ranges[:1]
        for name, version in pins:
            same = (
                name == adv["package"]
                if exact_names
                else _normalize(name) == _normalize(adv["package"])
            )
            if not same:
                continue
            if any(_in_range(version, clause, textual) for clause in ranges):
                rows.append([_normalize(name), version, adv["id"], adv["fixed_in"]])
    rows.sort(key=lambda r: (r[0], r[2]))
    return rows


class Sw5(DeskFamily):
    id = "sw5"
    domain = "software-engineering"
    title = "Dependency vulnerability audit of a lock file"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        names = rng.sample(NAMES, 9)
        lines = ["# pinned by the release bot", ""]
        pins = []
        for name in names:
            version = f"{rng.randint(0, 3)}.{rng.randint(0, 19)}.{rng.randint(0, 12)}"
            shown = name
            if rng.random() < 0.3:
                shown = name.replace("-", "_").title() if rng.random() < 0.5 else name.upper()
            if level == 2 and rng.random() < 0.2:
                shown = f"{shown}[socks]"
            if level == 2 and rng.random() < 0.15:
                version += rng.choice(["rc1", "b2"])
            pins.append((shown, version))
            lines.append(f"{shown}=={version}")
        advisories = []
        for i, name in enumerate(names[: rng.randint(6, 8)]):
            base = rng.randint(0, 3)
            cut = f"{base}.{rng.randint(1, 15)}.0"
            fixed = f"{base}.{rng.randint(16, 19)}.{rng.randint(0, 9)}"
            clause = f">={base}.0.0,<{cut}"
            affected = clause
            if level == 2 and rng.random() < 0.4:
                affected = f"{clause}||>={fixed},<{base}.{rng.randint(20, 25)}.0"
            advisories.append(
                {
                    "id": f"ADV-{2026000 + i * 7 + rng.randint(1, 6)}",
                    "package": name,
                    "affected": affected,
                    "fixed_in": fixed,
                    "withdrawn": level == 2 and rng.random() < 0.2,
                }
            )
        rng.shuffle(advisories)
        lock_text = "\n".join(lines) + "\n"
        truth = _audit(lock_text, advisories)
        if not truth:
            return None
        decoys = [
            _audit(lock_text, advisories, textual=True),
            _audit(lock_text, advisories, exact_names=True),
        ]
        if level == 2:
            decoys.append(_audit(lock_text, advisories, first_range_only=True))
            decoys.append(_audit(lock_text, advisories, keep_withdrawn=True))
        if any(d == truth for d in decoys):
            return None

        adv_text = json.dumps(advisories, indent=1) + "\n"
        rules = (
            "1. Names match after normalization: lowercase, and each run of '-', '_' or '.' counts "
            "as one '-'. "
            "Extras in brackets (requests[socks]) are ignored.\n"
            "2. Compare versions number by number (1.10 is higher than 1.9). A pre-release such as "
            "2.0rc1, "
            "2.0b2 or 2.0a1 is lower than the release with the same numbers.\n"
            "3. An affected range is conditions separated by commas, all of which must hold "
            "(operators >=, >, "
            "<=, <, ==, !=). Several ranges are separated by ||, and any one of them may hold. A "
            "pinned version "
            "in an affected range is vulnerable.\n"
            "4. Advisories marked withdrawn true were retracted and do not count."
            if level == 2
            else "1. Names match after lowercasing. Versions compare number by number "
            "(1.10 is higher than 1.9).\n"
            "2. An affected range is conditions separated by commas, all of which must hold "
            "(operators >=, >, "
            "<=, <, ==, !=). A pinned version in an affected range is vulnerable."
        )
        instruction = (
            "Security wants the vulnerable pins of the Python service before the release. "
            "{root}/requirements.lock "
            "pins packages as name==version, one per line; lines starting with # are comments. "
            "{root}/advisories.json lists the advisories: id, package, affected (the affected "
            "version range), "
            "fixed_in and withdrawn.\n\n"
            "Rules:\n" + rules + "\n\n"
            "Output: a CSV at {root}/output/vulnerable.csv with the exact header line "
            "package,installed,advisory_id,fixed_in and one row per vulnerable pin and advisory. "
            "package is the "
            "normalized name, installed the pinned version as written in the lock file. Sort the "
            "rows by package, "
            "then by advisory_id (plain text order). Create the output folder if needed."
        )
        files = {"requirements.lock": lock_text, "advisories.json": adv_text}
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                CsvOut(
                    path=OUT,
                    header=tuple(HEADER),
                    columns=tuple(Check("text") for _ in HEADER),
                    rows=tuple(tuple(r) for r in truth),
                )
            ],
            oracle={OUT: csv_text(truth, HEADER)},
            decoys=[{OUT: csv_text(d, HEADER)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"vulnerable\.csv", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        advisories = json.loads(text("advisories.json"))
        ignore_withdrawn = "withdrawn true were retracted" in instruction
        rows = _audit(text("requirements.lock"), advisories, keep_withdrawn=not ignore_withdrawn)
        return {OUT: csv_text(rows, HEADER)}


FAMILY = Sw5()
