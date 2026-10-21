# SPDX-License-Identifier: Apache-2.0

"""
med5: citation audit of a manuscript against its bibliography (media-content-production).

``manuscript.md`` cites sources Pandoc-style: [@key], [@key1; @key2] or
[@key, p. 4]. ``refs.bib`` holds BibTeX entries. Brackets without an @key item
(such as [Table 1] or [1]) are not citations. Level 2 adds fenced code blocks and
HTML comments that cite keys (they do not count), e-mail addresses (not
citations) and a duplicated bibliography entry.

The answer: keys cited but missing from the bibliography, bibliography keys
never cited, the most cited key, and the number of distinct keys cited.

Decoys: accepting any bracket item as a citation, counting citations in code and
comments, counting every @ token as a citation, and dropping the missing keys
from the distinct count.
"""

import collections
import json
import random
import re
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match

OUT = "output/citation_audit.json"
KEY = r"@([A-Za-z][A-Za-z0-9_-]*\d{4}[a-z]?)"
AUTHORS = [
    "lopez",
    "kim",
    "okafor",
    "haddad",
    "novak",
    "silva",
    "moreau",
    "tanaka",
    "berg",
    "nair",
    "ruiz",
    "adler",
]


def _cited(
    text: str, strict: bool = True, skip_code_and_comments: bool = True, any_at: bool = False
) -> list[str]:
    if skip_code_and_comments:
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    if any_at:
        # Every @ token, e-mail domains included.
        return re.findall(r"@([A-Za-z][A-Za-z0-9_.-]*)", text)
    keys: list[str] = []
    for group in re.findall(r"\[([^\]\n]+)\]", text):
        for item in group.split(";"):
            item = item.strip()
            if strict:
                match = re.match(KEY, item)
                if match:
                    keys.append(match.group(1))
            else:
                keys.append(item.split(",")[0].strip().lstrip("@"))
    return keys


def _audit(
    manuscript: str,
    bib: str,
    strict: bool = True,
    skip: bool = True,
    any_at: bool = False,
    count_missing: bool = True,
) -> dict:
    bib_keys = set(re.findall(r"^@\w+\{([^,\s]+),", bib, flags=re.M))
    cited = _cited(manuscript, strict=strict, skip_code_and_comments=skip, any_at=any_at)
    counts = collections.Counter(cited)
    if count_missing:
        distinct = len(set(cited))
    else:
        distinct = len(set(cited) & bib_keys)
    top = counts.most_common()
    most = top[0][0] if top else ""
    return {
        "missing": sorted(set(cited) - bib_keys),
        "unused": sorted(bib_keys - set(cited)),
        "most_cited": most,
        "unique_cited": distinct,
    }


class Med5(DeskFamily):
    id = "med5"
    domain = "media-content-production"
    title = "Citation audit of a manuscript"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        entries = []
        keys = []
        for i in range(12):
            author = rng.choice(AUTHORS)
            year = rng.randint(2009, 2025)
            key = f"{author}{year}{'' if i % 3 else 'a'}"
            if key in keys:
                continue
            keys.append(key)
            entries.append(
                f"@article{{{key},\n"
                f"  author = {{{author.title()} and others}},\n"
                f"  title = {{Study {i + 1}}},\n"
                f"  year = {{{year}}}\n}}\n"
            )
        bib_entries = list(entries)
        if level == 2:
            bib_entries.append(entries[2])
        bib = "\n".join(bib_entries)
        cite_pool = keys[:9]
        missing = [f"{rng.choice(AUTHORS)}{rng.randint(1990, 2008)}" for _ in range(2)]
        paragraphs = []
        for _ in range(9):
            groups = []
            for _ in range(rng.randint(1, 3)):
                chosen = rng.sample(cite_pool + missing, k=rng.randint(1, 2))
                items = []
                for j, key in enumerate(chosen):
                    locator = (
                        f", p. {rng.randint(2, 40)}"
                        if rng.random() < 0.2 and j == len(chosen) - 1
                        else ""
                    )
                    items.append(f"@{key}{locator}")
                groups.append("[" + "; ".join(items) + "]")
            filler = rng.choice(
                ["[Table 1] shows the setup", "see [1] for context", "as reported before"]
            )
            paragraphs.append(f"{filler}. Results agree {' '.join(groups)}.")
        if level == 2:
            paragraphs.append("Contact: ana.lopez2019@example.org for the data.")
            paragraphs.append("```\nexample [@fakecode2001] inside a code block\n```")
            paragraphs.append("<!-- draft note: [@old1999] -->")
        manuscript = "# Draft\n\n" + "\n\n".join(paragraphs) + "\n"
        truth = _audit(manuscript, bib)
        if not truth["missing"] or not truth["unused"] or not truth["most_cited"]:
            return None
        counts = collections.Counter(_cited(manuscript))
        if (
            len(counts.most_common()) > 1
            and counts.most_common(2)[0][1] == counts.most_common(2)[1][1]
        ):
            return None
        decoys = [
            _audit(manuscript, bib, strict=False),
            _audit(manuscript, bib, count_missing=False),
        ]
        if level == 2:
            decoys.append(_audit(manuscript, bib, skip=False))
            decoys.append(_audit(manuscript, bib, any_at=True))
        if any(d == truth for d in decoys):
            return None

        instruction = (
            "Before submission the editor needs a citation audit. {root}/manuscript.md cites "
            "sources "
            "Pandoc-style: a bracket group such as [@key], [@key1; @key2] or [@key, p. 4], where "
            "each item starts "
            "with @ and the key is the text after @ up to a comma, a semicolon or a space. "
            "{root}/refs.bib holds "
            "the BibTeX entries; each entry starts with @type{key,.\n\n"
            "Rules:\n"
            "1. Only bracket groups with at least one @key item are citations. Other brackets, "
            "such as [Table 1] "
            "or [1], are not citations.\n"
            + (
                "2. Citations inside fenced code blocks (between lines of three backticks) and "
                "inside HTML comments "
                "(<!-- ... -->) do not count. An e-mail address is not a citation.\n"
                if level == 2
                else ""
            )
            + "3. Keys are case-sensitive. Count every citation, including repeated ones.\n\n"
            "Output: a JSON object at {root}/output/citation_audit.json with the keys missing "
            "(sorted list of "
            "cited keys that have no entry in refs.bib), unused (sorted list of refs.bib keys that "
            "are never "
            "cited), most_cited (the key with the most citations; the instance has a single top "
            "key) and "
            "unique_cited (the number of distinct keys cited, missing ones included). Create the "
            "output folder "
            "if needed."
        )
        return DeskTask(
            instruction=instruction,
            files={"manuscript.md": manuscript, "refs.bib": bib + "\n"},
            outputs=[
                JsonOut(
                    path=OUT,
                    checks={
                        "missing": Check("set"),
                        "unused": Check("set"),
                        "most_cited": Check("text"),
                        "unique_cited": Check("int"),
                    },
                    want=truth,
                )
            ],
            oracle={OUT: json.dumps(truth)},
            decoys=[{OUT: json.dumps(d)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"citation_audit\.json", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        return {OUT: json.dumps(_audit(text("manuscript.md"), text("refs.bib")))}


FAMILY = Med5()
