# SPDX-License-Identifier: Apache-2.0

"""
med2: caption length (media and content production).

``captions.txt`` holds one caption per line. The agent must find the first line
longer than 90 characters. Characters are code points, not bytes. A decoy
caption has more than 90 bytes but at most 90 code points, so counting bytes
gives a wrong line.
"""

import random
import string

from ..core.grading import Field
from .base import Built, Family

LIMIT = 90
ALPHABET = string.ascii_lowercase + "     "
COUNTS = {1: 16, 2: 20, 3: 26}


def _caption(length: int, accents: int, rng: random.Random) -> str:
    chars = [rng.choice(ALPHABET) for _ in range(length)]
    chars[0] = rng.choice(string.ascii_lowercase)
    chars[-1] = rng.choice(string.ascii_lowercase)
    free = [i for i in range(1, length - 1) if chars[i] != " "]
    for i in rng.sample(free, min(accents, len(free))):
        chars[i] = "é"
    return "".join(chars)


class MediaCaptionLength(Family):
    id = "med2"
    domain = "media-content-production"
    title = "Caption length"

    def build(self, level: int, rng: random.Random) -> Built:
        n = COUNTS[level]
        target = rng.randint(3, n)
        trap = rng.randint(1, target - 2)
        lines: list[str] = []
        for i in range(1, n + 1):
            if i == target:
                lines.append(_caption(rng.randint(LIMIT + 1, LIMIT + 10), 0, rng))
            elif i == trap:
                # 84 code points but more than 90 bytes: byte counting says "long".
                lines.append(_caption(84, 12, rng))
            else:
                lines.append(_caption(rng.randint(30, LIMIT), rng.randint(0, 4), rng))
        if any(len(line) > LIMIT for line in lines[: target - 1]):
            raise AssertionError("builder put a long caption before the target")
        after = target + 1 if target < n else 1
        return Built(
            question=(
                "captions.txt holds one caption per line. Which line number is the first "
                "caption longer than 90 characters? Count code points, not bytes."
            ),
            files={"captions.txt": "\n".join(lines) + "\n"},
            fields={"index": Field("int")},
            answer={"index": target},
            decoys=[{"index": trap}, {"index": target - 1}, {"index": after}],
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        lines = files["captions.txt"].rstrip("\n").split("\n")
        for number, line in enumerate(lines, start=1):
            if len(line) > LIMIT:
                return {"index": number}
        return {"index": 0}


FAMILY = MediaCaptionLength()
