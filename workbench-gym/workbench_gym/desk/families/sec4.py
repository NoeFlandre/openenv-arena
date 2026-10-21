# SPDX-License-Identifier: Apache-2.0

"""
sec4: SSH brute-force sources and the logins that followed (cybersecurity).

``auth.log`` is an sshd syslog excerpt for 2026 (syslog lines carry no year).
A source is a brute-force source when it has at least five failed logins within
any 600 s window. It is compromised when a successful login from that address
happens at or after its burst time. Level 2 adds internal traffic that must be
ignored and noise lines from other daemons.

Decoys: counting only "Failed password" lines, a 3600 s window, counting logins
from before the burst, and counting internal failures.
"""

import datetime as dt
import ipaddress
import json
import random
import re
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match

OUT = "output/ssh_report.json"
WINDOW_S = 600
THRESHOLD = 5
INTERNAL = ipaddress.ip_network("10.0.0.0/8")
LINE = re.compile(r"^(\w{3})\s+(\d{1,2}) (\d{2}:\d{2}:\d{2}) \S+ sshd\[\d+\]: (.*)$")
FAILED = re.compile(r"Failed password for (?:invalid user )?(\S+) from (\S+) port")
INVALID = re.compile(r"Invalid user (\S+) from (\S+)")
ACCEPTED = re.compile(r"Accepted (?:password|publickey) for (\S+) from (\S+) port")
BASE = dt.datetime(2026, 1, 1)


def _when(mon: str, day: str, hms: str) -> float:
    stamp = dt.datetime.strptime(f"2026 {mon} {day} {hms}", "%Y %b %d %H:%M:%S")
    return (stamp - BASE).total_seconds()


def _analyse(
    text: str,
    window: int = WINDOW_S,
    count_invalid: bool = True,
    keep_internal: bool = False,
    early_logins: bool = False,
) -> dict:
    fails: dict[str, list[float]] = {}
    logins: dict[str, list[tuple[float, str]]] = {}
    failed_total = 0
    for raw in text.splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        when = _when(m.group(1), m.group(2), m.group(3))
        msg = m.group(4)
        ip = user = None
        fm = FAILED.search(msg)
        im = INVALID.search(msg) if count_invalid else None
        am = ACCEPTED.search(msg)
        if fm:
            user, ip = fm.group(1), fm.group(2)
        elif im:
            user, ip = im.group(1), im.group(2)
        elif am:
            user, ip = am.group(1), am.group(2)
        if ip is None or user is None:
            continue
        if not keep_internal and ipaddress.ip_address(ip) in INTERNAL:
            continue
        if fm or im:
            fails.setdefault(ip, []).append(when)
            failed_total += 1
        else:
            logins.setdefault(ip, []).append((when, user))
    bursts: dict[str, float] = {}
    for ip, times in fails.items():
        times.sort()
        for i in range(len(times) - THRESHOLD + 1):
            if times[i + THRESHOLD - 1] - times[i] <= window:
                bursts[ip] = times[i + THRESHOLD - 1]
                break
    compromised = set()
    for ip, burst in bursts.items():
        for when, user in logins.get(ip, []):
            if early_logins or when >= burst:
                compromised.add(f"{user}@{ip}")
    return {
        "bruteforce_ips": sorted(bursts),
        "compromised": sorted(compromised),
        "failed_total": failed_total,
    }


def _fmt(when: float) -> str:
    """A syslog stamp: "Oct  3 10:01:02" (the day is space-padded)."""
    stamp = BASE + dt.timedelta(seconds=when)
    return f"{stamp:%b} {stamp.day:>2} {stamp:%H:%M:%S}"


class Sec4(DeskFamily):
    id = "sec4"
    domain = "cybersecurity"
    title = "SSH brute-force sources and logins"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        events: list[tuple[float, str]] = []
        day0 = (dt.date(2026, 10, 3) - BASE.date()).days * 86400
        public = [
            f"{rng.choice([203, 198, 192])}.{rng.randint(0, 255)}.{rng.randint(0, 255)}"
            f".{rng.randint(1, 254)}"
            for _ in range(12)
        ]
        rng.shuffle(public)
        attackers, benign = public[:3], public[3:9]
        users = ["root", "admin", "deploy", "ubuntu", "git"]
        for ip in attackers:
            start = day0 + rng.randint(3600, 70000)
            count = rng.randint(THRESHOLD, THRESHOLD + 4)
            spread = rng.randint(120, WINDOW_S - 60)
            times = sorted(start + rng.uniform(0, spread) for _ in range(count))
            for t in times:
                if rng.random() < 0.3:
                    events.append(
                        (
                            t,
                            f"Invalid user {rng.choice(users)} from {ip} port "
                            f"{rng.randint(20000, 60000)}",
                        )
                    )
                else:
                    events.append(
                        (
                            t,
                            f"Failed password for {rng.choice(users)} from {ip} port "
                            f"{rng.randint(20000, 60000)} ssh2",
                        )
                    )
            burst = times[THRESHOLD - 1]
            if rng.random() < 0.6:
                when = burst + rng.randint(30, 3000)
                events.append(
                    (
                        when,
                        f"Accepted password for {rng.choice(users)} from {ip} port "
                        f"{rng.randint(20000, 60000)} ssh2",
                    )
                )
            else:
                when = times[0] - rng.randint(60, 900)
                events.append(
                    (
                        when,
                        f"Accepted password for {rng.choice(users)} from {ip} port "
                        f"{rng.randint(20000, 60000)} ssh2",
                    )
                )
        slow_ip = benign[0]
        for k in range(THRESHOLD):
            events.append(
                (
                    day0 + 7200 + k * 900,
                    f"Failed password for ubuntu from {slow_ip} port 40000 ssh2",
                )
            )
        for ip in benign[1:]:
            for _ in range(rng.randint(1, 3)):
                events.append(
                    (
                        day0 + rng.randint(3600, 80000),
                        f"Failed password for git from {ip} port 4001 ssh2",
                    )
                )
            if rng.random() < 0.5:
                events.append(
                    (
                        day0 + rng.randint(3600, 80000),
                        f"Accepted publickey for git from {ip} port 4002 ssh2",
                    )
                )
        if level == 2:
            internal = f"10.{rng.randint(0, 9)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
            for k in range(THRESHOLD + 2):
                events.append(
                    (
                        day0 + 30000 + k * 40,
                        f"Failed password for deploy from {internal} port 5000 ssh2",
                    )
                )
            events.append(
                (day0 + 31000, f"Accepted password for deploy from {internal} port 5001 ssh2")
            )
            for _ in range(20):
                events.append(
                    (
                        day0 + rng.randint(0, 86000),
                        "pam_unix(cron:session): session opened for user root",
                    )
                )
        events.sort()
        lines = []
        for when, msg in events:
            lines.append(
                f"{_fmt(when)} web1 sshd[{rng.randint(1000, 9999)}]: {msg}"
                if "Failed" in msg or "Invalid" in msg or "Accepted" in msg
                else f"{_fmt(when)} web1 cron[{rng.randint(1000, 9999)}]: {msg}"
            )
        text = "\n".join(lines) + "\n"

        truth = _analyse(text)
        decoys = [
            _analyse(text, count_invalid=False),
            _analyse(text, window=3600),
            _analyse(text, early_logins=True),
        ]
        if level == 2:
            decoys.append(_analyse(text, keep_internal=True))
        if any(d == truth for d in decoys) or not truth["bruteforce_ips"]:
            return None

        internal_rule = (
            " Ignore every line whose source address is in the internal network 10.0.0.0/8, "
            "for all rule counts."
            if level == 2
            else ""
        )
        instruction = (
            "The SOC wants the SSH sources that guessed passwords on web1 in the last two days. "
            "{root}/auth.log is the sshd syslog excerpt for 2026 (the lines have no year). Cron "
            "and "
            "other daemons also log there; ignore lines that are not from sshd.\n\n"
            "Rules:\n"
            "1. A failure is a line that contains 'Failed password for' or 'Invalid user'. The "
            "source "
            "is the address after 'from'." + internal_rule + "\n"
            f"2. A source is a brute-force source when it has at least {THRESHOLD} failures within "
            "any "
            f"{WINDOW_S}-second window. Its burst time is the time of the failure that first makes "
            f"a {WINDOW_S}-second window hold {THRESHOLD} failures.\n"
            "3. A source is compromised when a successful login ('Accepted password' or 'Accepted "
            "publickey') from that address happens at or after its burst time. Report it as "
            "user@ip.\n"
            "4. failed_total is the number of failure lines counted under rule 1.\n\n"
            "Output: a JSON object at {root}/output/ssh_report.json with the keys bruteforce_ips "
            "(list "
            "of addresses), compromised (list of user@ip strings) and failed_total (integer). "
            "Order "
            "of the lists does not matter. Create the output folder if needed."
        )
        return DeskTask(
            instruction=instruction,
            files={"auth.log": text},
            outputs=[
                JsonOut(
                    path=OUT,
                    checks={
                        "bruteforce_ips": Check("set"),
                        "compromised": Check("set"),
                        "failed_total": Check("int"),
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
        must_match(r"ssh_report\.json", instruction)
        text = files["auth.log"]
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        internal = (
            "Ignore every line whose source address is in the internal network" in instruction
        )
        return {OUT: json.dumps(_analyse(text, keep_internal=not internal))}


FAMILY = Sec4()
