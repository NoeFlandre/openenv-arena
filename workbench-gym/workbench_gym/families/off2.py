# SPDX-License-Identifier: Apache-2.0

"""
off2: meeting slot from an inbox log (office white-collar).

``inbox.log`` holds one message per line. A Q4 review proposal names a slot. A
proposal is voided only by a later "Re: availability" reply that names the same
slot for the Q4 review. Earlier replies, replies about other meetings and the
latest proposal all mislead. The answer is the latest open proposal.
"""

import random

from ..core.grading import Field
from .base import Built, Family

COUNTS = {1: 8, 2: 14, 3: 20}
PROPOSALS = {1: 4, 2: 6, 3: 8}
BOARD = {1: 1, 2: 2, 3: 2}
SENDERS = ("Dana Ruiz", "Marc Lind", "Priya Nair", "Tom Okafor", "Ines Moreau", "Yusuf Demir")
FILLER = (
    ("Lunch menu", "see attached"),
    ("Printer toner", "no action"),
    ("Parking badge", "reminder"),
    ("Fire drill", "Thu 11:00"),
    ("Expenses due", "reminder"),
)
SLOT_POOL = [
    f"2026-10-{d:02d} {h:02d}:{m:02d}"
    for d in (8, 9, 12, 13, 14, 15, 16)
    for h in range(9, 17)
    for m in (0, 30)
]
GRID = 6000
MAX_TRIES = 400
RULES = (
    "Q4 review scheduling, rev 2. inbox.log holds one message per line: date | sender | subject | body.\n"
    "1. Count only Q4 review messages. A proposal has subject \"Q4 review slot\" and body "
    "\"propose <slot>\". A reply has subject \"Re: availability\" and body \"Q4 review unavailable <slot>\".\n"
    "2. A reply counts only if it is dated after the proposal for the same slot.\n"
    "3. A proposal is open unless a counting reply names its slot.\n"
    "4. The meeting takes the open proposal with the latest date.\n"
    "5. Answer the slot as YYYY-MM-DD HH:MM.\n"
)
QUESTION = (
    "inbox.log holds one message per line. Using rules.txt, which slot does the Q4 review "
    "meeting take? Give it as YYYY-MM-DD HH:MM."
)


def _stamp(m):
    day = 1 + m // 600
    within = m % 600
    return f"2026-10-{day:02d} {8 + within // 60:02d}:{within % 60:02d}"


def _free(rng, low, high, used):
    for _ in range(300):
        m = rng.randrange(low, high)
        if m not in used:
            used.add(m)
            return m
    return None


class MeetingSlot(Family):
    id = "off2"
    domain = "office-white-collar"
    title = "Meeting slot"

    def build(self, level: int, rng: random.Random) -> Built:
        n = COUNTS[level]
        p = PROPOSALS[level]
        board = BOARD[level]
        for _ in range(MAX_TRIES):
            a = rng.randint(2, p - 2)
            late = list(range(a + 1, p))
            extra = [i for i in range(1, a) if rng.random() < 0.5]
            filler_count = n - p - len(late) - len(extra) - 1 - board
            if filler_count < 0:
                continue
            slots = rng.sample(SLOT_POOL, p)
            times = sorted(rng.sample(range(4000), p))
            used = set(times)
            msgs = [(times[i], rng.choice(SENDERS), "Q4 review slot", f"propose {slots[i]}") for i in range(p)]

            ok = True
            for i in late + extra:
                m = _free(rng, times[i] + 1, GRID, used)
                if m is None:
                    ok = False
                    break
                msgs.append((m, rng.choice(SENDERS), "Re: availability", f"Q4 review unavailable {slots[i]}"))
            if not ok:
                continue
            early = _free(rng, 0, times[a], used)
            if early is None:
                continue
            msgs.append((early, rng.choice(SENDERS), "Re: availability", f"Q4 review unavailable {slots[a]}"))

            for j in range(board):
                m = _free(rng, 0, GRID, used)
                if m is None:
                    ok = False
                    break
                if j == 0:
                    msgs.append((m, rng.choice(SENDERS), "Board prep slot", f"propose {rng.choice(SLOT_POOL)}"))
                else:
                    msgs.append((m, rng.choice(SENDERS), "Re: availability", f"Board prep unavailable {rng.choice(SLOT_POOL)}"))
            if not ok:
                continue
            for _ in range(filler_count):
                m = _free(rng, 0, GRID, used)
                if m is None:
                    ok = False
                    break
                subject, body = rng.choice(FILLER)
                msgs.append((m, "Ops Bot", subject, body))
            if not ok:
                continue

            decoy_slots = [
                slots[p - 1],
                slots[0],
                slots[max(i for i in range(a) if i not in extra)],
            ]
            if len(set(decoy_slots)) < 3:
                continue

            msgs.sort(key=lambda item: item[0])
            lines = [f"{_stamp(m)} | {sender} | {subject} | {body}" for m, sender, subject, body in msgs]
            return Built(
                question=QUESTION,
                files={"inbox.log": "\n".join(lines) + "\n", "rules.txt": RULES},
                fields={"slot": Field("text")},
                answer={"slot": slots[a]},
                decoys=[{"slot": s} for s in decoy_slots],
            )
        raise RuntimeError("off2: no valid instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        proposals = {}
        replies = []
        for line in files["inbox.log"].splitlines():
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 4:
                continue
            when, _sender, subject, body = parts
            if subject == "Q4 review slot" and body.startswith("propose "):
                proposals[body[len("propose "):]] = when
            elif subject == "Re: availability" and body.startswith("Q4 review unavailable "):
                replies.append((body[len("Q4 review unavailable "):], when))
        open_slots = [
            (when, slot)
            for slot, when in proposals.items()
            if not any(s == slot and reply_when > when for s, reply_when in replies)
        ]
        return {"slot": max(open_slots)[1]}


FAMILY = MeetingSlot()
