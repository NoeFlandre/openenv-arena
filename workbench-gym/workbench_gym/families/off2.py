# SPDX-License-Identifier: Apache-2.0

"""
off2: meeting slot from an inbox log (office white-collar).

``inbox.log`` holds one message per line. A Q4 review proposal names a slot. A
proposal is voided only by a later "Re: availability" reply that names the same
slot for the Q4 review. Earlier replies, replies about other meetings and the
latest proposal all mislead. The answer is the latest open proposal.

The answer's position among the Q4 proposals is uniform over every position
that has a voided proposal after it (PROPOSALS - 1 positions), so no fixed rank
("second latest", "first", "third latest") is right on more than about one seed
in PROPOSALS - 1.
"""

import random

from ..core.grading import Field
from .base import Built, Family

PROPOSALS = {1: 15, 2: 15, 3: 16}
BOARD = {1: 1, 2: 2, 3: 2}
# Every proposal can be voided, plus one early reply and the board lines.
COUNTS = {level: 2 * PROPOSALS[level] + BOARD[level] for level in PROPOSALS}
SENDERS = ("DR", "ML", "PN", "TO", "IM", "YD")
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
TIMES = 4000
GRID = 6000
MAX_TRIES = 400
RULES = (
    "Q4 review scheduling. inbox.log has one message per line: date | sender | subject | body.\n"
    "1. Proposal: subject \"Q4 review slot\", body \"propose <slot>\". "
    "Reply: subject \"Re: availability\", body \"Q4 review unavailable <slot>\".\n"
    "2. A reply counts only if dated after the proposal for its slot.\n"
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
    if high <= low:
        return None
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
        p = PROPOSALS[level]
        n = COUNTS[level]
        for _ in range(MAX_TRIES):
            # Uniform over every position with a later proposal to void. Position 0 is the
            # earliest proposal; position p - 1 (the latest) is always voided.
            a = rng.randrange(p - 1)
            slots = rng.sample(SLOT_POOL, p)
            times = sorted(rng.sample(range(TIMES), p))
            used = set(times)
            msgs = [(times[i], rng.choice(SENDERS), "Q4 review slot", f"propose {slots[i]}") for i in range(p)]

            # Every later proposal is voided by a reply dated after it. Some earlier ones are too.
            voided = list(range(a + 1, p)) + [i for i in range(1, a) if rng.random() < 0.5]
            ok = True
            for i in voided:
                m = _free(rng, times[i] + 1, GRID, used)
                if m is None:
                    ok = False
                    break
                msgs.append((m, rng.choice(SENDERS), "Re: availability", f"Q4 review unavailable {slots[i]}"))
            if not ok:
                continue

            # The answer's own reply comes before its proposal, so it does not void it.
            early = _free(rng, 0, times[a], used)
            if early is None:
                continue
            msgs.append((early, rng.choice(SENDERS), "Re: availability", f"Q4 review unavailable {slots[a]}"))

            board_slot = rng.choice(SLOT_POOL)
            for j in range(BOARD[level]):
                m = _free(rng, 0, GRID, used)
                if m is None:
                    ok = False
                    break
                if j == 0:
                    msgs.append((m, rng.choice(SENDERS), "Board prep slot", f"propose {board_slot}"))
                else:
                    msgs.append((m, rng.choice(SENDERS), "Re: availability", f"Board prep unavailable {rng.choice(SLOT_POOL)}"))
            if not ok:
                continue

            while len(msgs) < n:
                m = _free(rng, 0, GRID, used)
                if m is None:
                    ok = False
                    break
                subject, body = rng.choice(FILLER)
                msgs.append((m, "OPS", subject, body))
            if not ok or len(msgs) != n:
                continue

            # Plausible wrong slots: the stale latest, the slot just after the answer, the
            # earliest proposal, and two more Q4 proposals. Each is a real Q4 slot.
            decoy_slots: list[str] = []
            for j in (p - 1, a + 1, 0, p - 2, 1):
                if 0 <= j < p and j != a and slots[j] not in decoy_slots:
                    decoy_slots.append(slots[j])
            if len(decoy_slots) < 3:
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
