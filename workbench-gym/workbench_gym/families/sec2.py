# SPDX-License-Identifier: Apache-2.0

"""
sec2: two-hop auth log (cybersecurity).

``auth.log`` records logins that pass through a gateway. Each line gives time,
user, result and ``via`` = client>gateway (two hops). ``policy.txt`` defines an
alarm: an OK that follows K or more consecutive FAIL lines from the same client,
where the client is the first address in ``via``. The gateway is shared by many
clients, so counting by it raises false alarms. Decoys: the user of the alarm
when counted per gateway, when K-1 suffices, when failures need not be
consecutive, and the latest alarm instead of the earliest.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

K_BY_LEVEL = {1: 3, 2: 4, 3: 5}
EDGE_GW = "10.0.0.1"
TRAP_GW = "10.0.0.2"
CLIENT_GW = "10.0.0.3"
NAMES = (
    "amy", "bo", "chen", "dara", "eli", "fay", "gus", "hana", "ivo", "jo",
    "kim", "lea", "max", "nia", "omar", "pia", "quin", "rosa", "sol", "tia",
    "uma", "vic", "wes", "xan", "yara", "zed", "ada", "ben", "cy", "ned",
)
LINE = re.compile(r"^(\d+) (\S+) (OK|FAIL) (\S+)>(\S+)$")


def _alarms(events, key, need, consecutive=True):
    """Users whose OK follows ``need`` FAILs under ``key``, in event order."""
    run: dict = {}
    total: dict = {}
    hits: list[str] = []
    for user, result, client, gw in events:
        k = key(client, gw)
        if result == "FAIL":
            run[k] = run.get(k, 0) + 1
            total[k] = total.get(k, 0) + 1
        else:
            count = run.get(k, 0) if consecutive else total.get(k, 0)
            if count >= need:
                hits.append(user)
            run[k] = 0
    return hits


def _render(events, rng):
    lines = ["# time user result via(client>gateway)"]
    t = 0
    for user, result, client, gw in events:
        t += rng.randint(1, 4)
        lines.append(f"{t:04d} {user} {result} {client}>{gw}")
    return "\n".join(lines)


class TwoHopAuth(Family):
    id = "sec2"
    domain = "cybersecurity"
    title = "Two-hop auth log"

    def build(self, level: int, rng: random.Random) -> Built:
        k = K_BY_LEVEL[level]
        clients_pool = [f"198.51.100.{i}" for i in range(1, 255)] + [
            f"203.0.113.{i}" for i in range(1, 255)
        ]
        while True:
            names = rng.sample(NAMES, len(NAMES))
            x1, x2, target, trap_user, latest = names[:5]
            noise_names = names[5:]
            ips = rng.sample(clients_pool, 4 + k + 6)
            f, c, h, d = ips[:4]
            attackers = ips[4:4 + k]
            spare = ips[4 + k:]

            # Shared client f: K-1 fails then OK by x1, then one fail and OK by x2.
            block_f = [(x1, "FAIL", f, CLIENT_GW)] * (k - 1)
            block_f += [(x1, "OK", f, CLIENT_GW), (x2, "FAIL", f, CLIENT_GW), (x2, "OK", f, CLIENT_GW)]
            # Gateway trap: K distinct clients fail through TRAP_GW, then trap_user succeeds.
            block_gw = [(rng.choice(noise_names), "FAIL", a, TRAP_GW) for a in attackers]
            block_gw += [(trap_user, "OK", d, TRAP_GW)]
            # Real alarm: target fails K times from c, then succeeds.
            block_c = [(target, "FAIL", c, EDGE_GW)] * k + [(target, "OK", c, EDGE_GW)]
            # Later alarm: latest, same shape from h.
            block_h = [(latest, "FAIL", h, EDGE_GW)] * k + [(latest, "OK", h, EDGE_GW)]
            events = block_f + block_gw + block_c + block_h

            for i in range(3):
                client = spare[i]
                user = rng.choice(noise_names)
                gw = rng.choice((EDGE_GW, CLIENT_GW))
                runs = rng.randint(0, k - 1)
                block = [(user, "FAIL", client, gw)] * runs + [(user, "OK", client, gw)]
                pos = rng.randint(0, len(events))
                events[pos:pos] = block

            correct = _alarms(events, lambda c_, g: c_, k)
            if not correct or correct[0] != target:
                continue
            decoys = [
                {"user": _first(_alarms(events, lambda c_, g: g, k))},
                {"user": _first(_alarms(events, lambda c_, g: c_, k - 1))},
                {"user": _first(_alarms(events, lambda c_, g: c_, k, consecutive=False))},
                {"user": correct[-1]},
            ]
            if any(d_["user"] in (None, target) for d_ in decoys):
                continue
            break

        policy = "\n".join(
            [
                "Lockout policy v3. via lists hops, client first, gateway last.",
                "Per client: a FAIL extends its run; any OK from that client resets it.",
                "Alarm: an OK that follows K or more consecutive FAILs from that client.",
                f"K = {k}",
            ]
        )
        log = _render(events, rng)
        return Built(
            question=(
                "auth.log lists logins through gateways. Under the alarm rule in policy.txt, "
                "which user raised the earliest alarm?"
            ),
            files={"auth.log": log + "\n", "policy.txt": policy + "\n"},
            fields={"user": Field("text")},
            answer={"user": target},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        k = int(re.search(r"K = (\d+)", files["policy.txt"]).group(1))
        events = []
        for line in files["auth.log"].split("\n"):
            m = LINE.match(line.strip())
            if not m:
                continue
            _, user, result, client, gateway = m.groups()
            events.append((user, result, client, gateway))
        hits = _alarms(events, lambda c_, g: c_, k)
        return {"user": hits[0]}


def _first(hits):
    return hits[0] if hits else None


FAMILY = TwoHopAuth()
