# SPDX-License-Identifier: Apache-2.0

"""
med1: edit timeline (media-content-production).

``edl.txt`` is an edit decision list: one edit per line, with a source IN and
OUT in seconds. ``spec.txt`` holds the conform rules. Times fall on a frame
grid, and an edit whose IN or OUT lands between frames is rejected in full.
The conform tool never rounds. total_frames is the sum of the valid lengths.

Decoys: rounding or truncating each point (accepts what must be rejected),
checking only the length, checking only OUT, and counting rejected edits in
the total.
"""

import math
import random
import re
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family, must_match

EDITS = {1: 3, 2: 5, 3: 7}
FPS_CHOICES = (24, 25, 30)
TITLES = ("harbor_cut_v3", "fieldnotes_v2", "market_ep4", "longform_rough")
SOURCES = ("rush_0412.mov", "cam_b_0931.mov", "drone_0218.mov")

SPEC = """Conform rules C-2, timeline spec for the edit decision list
C1. Times in edl.txt are seconds on the source clip named by SOURCE.
C2. Frame position = seconds x FPS. Edits sit on whole frames.
C3. An edit is valid only if its IN and its OUT are both whole frames.
C4. An edit with a fractional IN or OUT is rejected in full. Never round a point.
C5. Edit length = OUT minus IN, in frames, for each valid edit.
C6. total_frames = sum of the lengths of the valid edits.
C7. Rejected edits are left out of total_frames and listed in rejected.
"""


def _fmt(k: int) -> str:
    """Thousandths of a second, written as seconds with three decimals."""
    return f"{k // 1000}.{k % 1000:03d}"


def _half_up(value: Fraction) -> int:
    return math.floor(value + Fraction(1, 2))


def _snap(target: int, good: bool, unit: int) -> int:
    """A whole-frame point at or after ``target`` when ``good``, else a point off the grid."""
    if good:
        return unit * -(-target // unit)
    return target + 1 if target % unit == 0 else target


def _timeline(edits: list, fps: int, rule: str) -> tuple[int, list[str]]:
    """Total frames and rejected IDs under one rule. ``exact`` is the policy."""
    total = 0
    rejected: list[str] = []
    for eid, k_in, k_out in edits:
        f_in = Fraction(k_in * fps, 1000)
        f_out = Fraction(k_out * fps, 1000)
        length = f_out - f_in
        if rule == "exact":
            if f_in.denominator != 1 or f_out.denominator != 1:
                rejected.append(eid)
                continue
            total += int(length)
        elif rule == "round":
            total += _half_up(f_out) - _half_up(f_in)
        elif rule == "trunc":
            total += math.floor(f_out) - math.floor(f_in)
        elif rule == "length_only":
            if length.denominator != 1:
                rejected.append(eid)
                continue
            total += int(length)
        elif rule == "out_only":
            if f_out.denominator != 1:
                rejected.append(eid)
                continue
            total += _half_up(length)
    return total, sorted(rejected)


class EditTimeline(Family):
    id = "med1"
    domain = "media-content-production"
    title = "Edit timeline"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(400):
            built = self._attempt(level, rng)
            if built is not None:
                return built
        raise AssertionError(f"med1 level {level}: no instance found")

    def _attempt(self, level: int, rng: random.Random) -> Built | None:
        fps = rng.choice(FPS_CHOICES)
        unit = 1000 // math.gcd(fps, 1000)  # thousandths between whole frames
        n = EDITS[level]
        edits: list[tuple[str, int, int]] = []
        for i in range(1, n + 1):
            good_in = rng.random() < 0.7
            good_out = rng.random() < 0.7
            k_in = _snap(rng.randint(1000, 180000), good_in, unit)
            k_out = _snap(k_in + rng.randint(1000, 20000), good_out, unit)
            edits.append((f"E{i:02d}", k_in, k_out))

        want_total, want_rej = _timeline(edits, fps, "exact")
        if not 1 <= len(want_rej) <= n - 1:
            return None
        answer = {"total_frames": want_total, "rejected": want_rej}

        candidates = []
        for rule in ("round", "trunc", "length_only", "out_only"):
            total, rej = _timeline(edits, fps, rule)
            candidates.append({"total_frames": total, "rejected": rej})
        sum_all = sum(_half_up(Fraction((k_out - k_in) * fps, 1000)) for _, k_in, k_out in edits)
        candidates.append({"total_frames": sum_all, "rejected": want_rej})
        decoys: list[dict] = []
        for cand in candidates:
            if cand != answer and cand not in decoys:
                decoys.append(cand)
        if len(decoys) < 3:
            return None

        edl_lines = [
            f"EDL {rng.choice(TITLES)}",
            f"SOURCE {rng.choice(SOURCES)}",
            f"FPS {fps}",
        ]
        edl_lines += [f"{eid} IN {_fmt(k_in)} OUT {_fmt(k_out)}" for eid, k_in, k_out in edits]
        return Built(
            question=(
                "Apply spec.txt to edl.txt. What is total_frames for the valid timeline, "
                "and which edit IDs are rejected? Give rejected as a list of IDs."
            ),
            files={"edl.txt": "\n".join(edl_lines) + "\n", "spec.txt": SPEC},
            fields={"total_frames": Field("int"), "rejected": Field("set")},
            answer=answer,
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        edl = files["edl.txt"]
        fps = int(must_match(r"^FPS (\d+)$", edl, re.M).group(1))
        total = 0
        rejected: list[str] = []
        for line in edl.split("\n"):
            match = re.fullmatch(r"(E\d+) IN (\d+\.\d+) OUT (\d+\.\d+)", line.strip())
            if match is None:
                continue
            eid = match.group(1)
            f_in = Fraction(match.group(2)) * fps
            f_out = Fraction(match.group(3)) * fps
            if f_in.denominator != 1 or f_out.denominator != 1:
                rejected.append(eid)
                continue
            total += int(f_out - f_in)
        return {"total_frames": total, "rejected": sorted(rejected)}


FAMILY = EditTimeline()
