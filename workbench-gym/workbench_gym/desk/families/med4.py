# SPDX-License-Identifier: Apache-2.0

"""
med4: subtitle resync from two reference cues (media-content-production).

``captions.srt`` was timed on a drifting clock. The instruction gives the true
start of the first cue and of the last cue; a linear map t' = a*t + b through
those two points corrects every start and end time, rounded half up to the
millisecond. Level 2 adds sound-only cues ([MUSIC]) to drop, overlapping cues to
clip, and a renumbering of the cues that remain.

Decoys: a plain shift from the first cue (no scale), keeping the original cue
numbers, and skipping the level-2 steps.
"""

import random
import re
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import csv_text, half_up

OUT = "output/subtitles_resynced.csv"
HEADER = ["index", "start_ms", "end_ms"]
TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")
WORDS = [
    "We should go now.",
    "Did you hear that?",
    "The sea is calm tonight.",
    "Hold the line.",
    "Not yet.",
    "Look at the lights.",
    "Quiet, please.",
    "That was close.",
    "Here we are.",
]


def _close(answer: list[list], truth: list[list]) -> bool:
    """True when the grader would accept ``answer``: same rows, times within its 1 ms tolerance."""
    if len(answer) != len(truth):
        return False
    return all(
        a[0] == t[0] and abs(a[1] - t[1]) <= 1 and abs(a[2] - t[2]) <= 1
        for a, t in zip(answer, truth, strict=True)
    )


def _ms(text: str) -> int:
    match = TIME.match(text)
    if match is None:
        raise ValueError(text)
    h, m, s, ms = (int(x) for x in match.groups())
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def _fmt(ms: int) -> str:
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _cues(text: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        lines = block.split("\n")
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start, end = (part.strip() for part in lines[1].split("-->"))
        cues.append(
            {
                "index": int(lines[0]),
                "start": _ms(start),
                "end": _ms(end),
                "text": " ".join(lines[2:]).strip(),
            }
        )
    return cues


def _resync(
    cues: list[dict],
    first_true: int,
    last_true: int,
    clip_and_drop: bool = False,
    renumber: bool = True,
    shift_only: bool = False,
    correct_ends: bool = True,
) -> list[list]:
    o1, on = cues[0]["start"], cues[-1]["start"]
    a = (last_true - first_true) / (on - o1)
    b = first_true - a * o1
    if shift_only:
        a, b = 1.0, first_true - o1
    out = []
    for cue in cues:
        out.append(
            {
                "index": cue["index"],
                "start": half_up(a * cue["start"] + b, 0),
                "end": half_up(a * cue["end"] + b, 0) if correct_ends else cue["end"],
                "text": cue["text"],
            }
        )
    if clip_and_drop:
        for i in range(len(out) - 1):
            if out[i]["end"] >= out[i + 1]["start"]:
                out[i]["end"] = out[i + 1]["start"] - 1
        out = [c for c in out if c["text"] != "[MUSIC]"]
    rows = []
    for position, cue in enumerate(out, start=1):
        index = position if renumber else cue["index"]
        rows.append([index, int(cue["start"]), int(cue["end"])])
    return rows


def _srt(cues: list[dict]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(f"{i}\n{_fmt(cue['start'])} --> {_fmt(cue['end'])}\n{cue['text']}\n")
    return "\n".join(blocks)


class Med4(DeskFamily):
    id = "med4"
    domain = "media-content-production"
    title = "Subtitle resync from two reference cues"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        n = 60 if level == 1 else 90
        alpha = 1 + rng.uniform(0.0004, 0.002) * rng.choice([-1, 1])
        beta = rng.randint(-4000, 4000)
        t = rng.randint(6000, 9000)
        true_starts, true_ends = [], []
        for _ in range(n):
            true_starts.append(t)
            dur = rng.randint(1200, 4000)
            true_ends.append(t + dur)
            t += dur + rng.randint(200, 2000)
        words = [rng.choice(WORDS) for _ in range(n)]
        if level == 2:
            for i in rng.sample(range(1, n - 1), k=6):
                words[i] = "[MUSIC]"
            for i in rng.sample(range(1, n - 2), k=5):
                true_ends[i] = true_starts[i + 1] + rng.randint(100, 900)
        observed = []
        for i in range(n):
            s = round(alpha * true_starts[i] + beta)
            e = round(alpha * true_ends[i] + beta)
            observed.append({"start": s, "end": e, "text": words[i]})
        first_true = true_starts[0]
        last_true = true_starts[-1]
        srt = _srt(observed)
        cues = _cues(srt)

        truth = _resync(cues, first_true, last_true, clip_and_drop=level == 2)
        decoys = [
            _resync(cues, first_true, last_true, clip_and_drop=level == 2, shift_only=True),
            _resync(cues, first_true, last_true, clip_and_drop=level == 2, correct_ends=False),
        ]
        if level == 2:
            decoys.append(
                _resync(cues, first_true, last_true, clip_and_drop=level == 2, renumber=False)
            )
            decoys.append(_resync(cues, first_true, last_true, clip_and_drop=False))
        if any(_close(d, truth) for d in decoys):
            return None

        rules = (
            "1. Correct every start and end time with the linear map t' = a*t + b that sends the "
            "observed "
            f"start of cue 1 to {_fmt(first_true)} and the observed start of the last cue to "
            f"{_fmt(last_true)}. Round each corrected time to a whole millisecond (half up)."
        )
        if level == 2:
            rules += (
                "\n2. A cue that ends after the next cue starts ends 1 ms before that next cue "
                "starts "
                "(after step 1).\n"
                "3. Drop every cue whose whole text is [MUSIC]; they are not subtitles.\n"
                "4. Number the cues that remain from 1, in order."
            )
        else:
            rules += "\n2. Number the cues from 1, in order."
        instruction = (
            "Our subtitle file drifted during export. {root}/captions.srt is the file as exported "
            "(standard "
            "SRT: index, 'start --> end' times with a comma before the milliseconds, and text). "
            "The true "
            f"start of cue 1 is {_fmt(first_true)} and the true start of the last cue is "
            f"{_fmt(last_true)} "
            "(check the times of the first and last cue in the file to see what is observed).\n\n"
            "Rules:\n" + rules + "\n\n"
            "Output: a CSV at {root}/output/subtitles_resynced.csv with the exact header line "
            "index,start_ms,end_ms and one row per cue, times as whole milliseconds from "
            "00:00:00.000. "
            "Create the output folder if needed."
        )
        checks = [Check("int"), Check("num", tol=1.0), Check("num", tol=1.0)]
        return DeskTask(
            instruction=instruction,
            files={"captions.srt": srt},
            outputs=[
                CsvOut(
                    path=OUT,
                    header=tuple(HEADER),
                    columns=tuple(checks),
                    rows=tuple(tuple(r) for r in truth),
                )
            ],
            oracle={OUT: csv_text(truth, HEADER)},
            decoys=[{OUT: csv_text(d, HEADER)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"subtitles_resynced\.csv", instruction)
        raw = files["captions.srt"]
        srt = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        first_true = _ms(
            must_match(r"start of cue 1 is (\d{2}:\d{2}:\d{2},\d{3})", instruction).group(1)
        )
        last_true = _ms(
            must_match(
                r"true start of the last cue is (\d{2}:\d{2}:\d{2},\d{3})", instruction
            ).group(1)
        )
        level2 = "[MUSIC]" in instruction
        rows = _resync(_cues(srt), first_true, last_true, clip_and_drop=level2)
        return {OUT: csv_text(rows, HEADER)}


FAMILY = Med4()
