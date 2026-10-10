# SPDX-License-Identifier: Apache-2.0

"""
med3: copyedit against a multi-page style guide (media-content-production).

``draft.txt`` is a manuscript, one paragraph per line. ``style_p1.txt`` holds the
base rules R1 to R5. Each later page adds addenda: exemptions that lift a rule
for some lines, and reinstatements that apply it again. Later clauses override
earlier ones, so a page-2 exemption overrides page 1, and a page-3 reinstatement
overrides page 2. The answer is the set of lines that break a rule in force
after the last page.

Decoys: the base rules alone, first match wins, dropping the last page, dropping
one clause, and 0-based line numbers.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family, must_match

LINES = 14
PAGES = {1: 2, 2: 3, 3: 4}
RULE_IDS = (1, 2, 3, 4, 5)
# Addenda by page: (kind, rule, prefix). A prefix of None means "contains a double quote".
ADDENDA = {
    2: [("exempt", 1, "Table"), ("exempt", 4, None)],
    3: [("exempt", 2, "Fig."), ("apply", 1, "Table 4")],
    4: [("exempt", 5, "Note"), ("apply", 2, "Fig. 9")],
}
PAGE_TITLES = {2: "captions and tables", 3: "figures", 4: "notes"}

BASE_PAGE = """Copy style guide, Northgate Media, page 1 of {n}
Base rules, applied to every line of draft.txt unless a later clause says otherwise.
R1 Write "percent", not the % sign.
R2 Spell out the whole numbers one to nine. A standalone digit 1-9 breaks R2.
R3 No ampersand in running text. Write "and".
R4 No contractions. A line with n't breaks R4.
R5 One space after a full stop, never two.
Later clauses override earlier ones. Where two clauses match a line, the later one applies.
"""

PREFIXES = ("", "", "", "Table rows: ", "Table 4 shows ", "Fig. 3: ", "Fig. 9: ", "Note: ")
CLEAN = (
    "The crew logged the rushes.",
    "Titles followed the cut.",
    "Color was checked on set.",
    "The mix came next.",
    "The cut locks in May.",
    "Dailies ran until noon.",
)
PCT = ("Sales rose {p}% in June.", "Uptake reached {p}%.")
DIGIT = ("We filmed {d} episodes.", "There were {d} cuts.", "Pick {d} takes.")
AMP = ("Editing & grading took two days.", "Music & sound were mixed.")
CONTR = ("The edit didn't lock.", "We won't reshoot.", "It isn't final.")
DBL = ("Audio was mixed.  Titles followed.",)
QUOTE = (
    'The host said "we begin now" and left.',
    'Her note read "it isn\'t ready".',
    'He wrote "the cut is done."',
)

_CLAUSE_RE = re.compile(
    r"(Exemption|Reinstatement): R(\d) (?:does not apply to|applies again to) lines that "
    r'(?:start with "([^"]+)"|contain a double quote)\.'
)


def _violates(rule: int, line: str) -> bool:
    if rule == 1:
        return "%" in line
    if rule == 2:
        return re.search(r"(?<![\w.])[1-9](?!\w|\.\d)", line) is not None
    if rule == 3:
        return "&" in line
    if rule == 4:
        return "n't" in line
    return ".  " in line


def _matches(prefix: str | None, line: str) -> bool:
    return '"' in line if prefix is None else line.startswith(prefix)


def _applies(rule: int, line: str, clauses: list, first: bool = False) -> bool:
    """Whether ``rule`` applies to ``line``. The last matching clause decides,
    or the first if ``first``."""
    decided = True
    for kind, clause_rule, prefix in clauses:
        if clause_rule != rule or not _matches(prefix, line):
            continue
        decided = kind == "apply"
        if first:
            break
    return decided


def _broken(lines: list[str], clauses: list, first: bool = False) -> list[int]:
    out: list[int] = []
    for number, line in enumerate(lines, start=1):
        if any(_violates(r, line) and _applies(r, line, clauses, first) for r in RULE_IDS):
            out.append(number)
    return out


def _fragment(rng: random.Random) -> str:
    kind = rng.choice(("clean", "clean", "pct", "digit", "amp", "contr", "dbl", "quote"))
    if kind == "pct":
        return rng.choice(PCT).format(p=rng.randint(5, 95))
    if kind == "digit":
        return rng.choice(DIGIT).format(d=rng.randint(1, 9))
    if kind == "amp":
        return rng.choice(AMP)
    if kind == "contr":
        return rng.choice(CONTR)
    if kind == "dbl":
        return rng.choice(DBL)
    if kind == "quote":
        return rng.choice(QUOTE)
    return rng.choice(CLEAN)


def _draft_line(rng: random.Random) -> str:
    prefix = rng.choice(PREFIXES)
    return prefix + " ".join(_fragment(rng) for _ in range(rng.choice((1, 1, 2))))


def _addendum_page(page: int, n_pages: int) -> str:
    lines = [
        f"Copy style guide, Northgate Media, page {page} of {n_pages}, "
        f"addendum: {PAGE_TITLES[page]}"
    ]
    for i, (kind, rule, prefix) in enumerate(ADDENDA[page], start=1):
        tag = f"X{page}.{i}"
        if kind == "exempt" and prefix is None:
            lines.append(
                f"{tag} Exemption: R{rule} does not apply to lines that contain a double quote."
            )
        elif kind == "exempt":
            lines.append(
                f'{tag} Exemption: R{rule} does not apply to lines that start with "{prefix}".'
            )
        else:
            lines.append(
                f'{tag} Reinstatement: R{rule} applies again to lines that start with "{prefix}".'
            )
    return "\n".join(lines) + "\n"


class CopyeditStyle(Family):
    id = "med3"
    domain = "media-content-production"
    title = "Copyedit"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(400):
            built = self._attempt(level, rng)
            if built is not None:
                return built
        raise AssertionError(f"med3 level {level}: no instance found")

    def _attempt(self, level: int, rng: random.Random) -> Built | None:
        n_pages = PAGES[level]
        addenda = [c for page in range(2, n_pages + 1) for c in ADDENDA[page]]
        lines = [_draft_line(rng) for _ in range(LINES)]
        answer = _broken(lines, addenda)
        if not 2 <= len(answer) <= LINES - 2:
            return None

        candidates: list[list[int]] = [
            _broken(lines, []),
            _broken(lines, addenda, first=True),
            _broken(lines, [c for page in range(2, n_pages) for c in ADDENDA[page]]),
            [n - 1 for n in answer],
        ]
        for j in range(len(addenda)):
            candidates.append(_broken(lines, addenda[:j] + addenda[j + 1 :]))

        decoys: list[dict] = []
        for cand in candidates:
            item = {"lines": sorted(cand)}
            if sorted(cand) != answer and item not in decoys and cand:
                decoys.append(item)
        if len(decoys) < 3:
            return None

        files = {"draft.txt": "\n".join(lines) + "\n"}
        files["style_p1.txt"] = BASE_PAGE.format(n=n_pages)
        for page in range(2, n_pages + 1):
            files[f"style_p{page}.txt"] = _addendum_page(page, n_pages)
        return Built(
            question=(
                "draft.txt is a copy-edit draft, one paragraph per line. The style_p pages, "
                "read in page order, set the rules. Which draft lines break a rule in force "
                "after the last page? Count lines from the top, starting at one."
            ),
            files=files,
            fields={"lines": Field("set")},
            answer={"lines": answer},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        pages = sorted(
            (name for name in files if re.fullmatch(r"style_p\d+\.txt", name)),
            key=lambda name: int(must_match(r"\d+", name).group()),
        )
        clauses: list[tuple[str, int, str | None]] = []
        for name in pages:
            for match in _CLAUSE_RE.finditer(files[name]):
                kind = "exempt" if match.group(1) == "Exemption" else "apply"
                clauses.append((kind, int(match.group(2)), match.group(3)))
        lines = files["draft.txt"].split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        return {"lines": _broken(lines, clauses)}


FAMILY = CopyeditStyle()
