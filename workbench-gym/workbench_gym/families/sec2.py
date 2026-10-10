# SPDX-License-Identifier: Apache-2.0

"""
sec2: two-hop auth log (cybersecurity).

``auth.log`` records logins that pass through a gateway. Each line gives time,
user, result and ``via`` = client>gateway (two hops). ``policy.txt`` defines an
alarm: an OK that follows K or more consecutive FAIL lines from the same client,
where the client is the first address in ``via``. The gateway is shared by many
clients, so counting by it raises false alarms, and a user can fail from several
clients, so counting by user raises false alarms too. Decoys: the user of the
alarm when counted per gateway, per user, when K-1 suffices, when failures need
not be consecutive, and the latest alarm instead of the earliest. The user with
the most FAIL lines never succeeds, so the answer is never that user.
"""

import random
import re
from collections import Counter

from ..core.grading import Field
from .base import Built, Family, must_match

K_BY_LEVEL = {1: 3, 2: 4, 3: 5}
EDGE_GW = "10.0.0.1"
TRAP_GW = "10.0.0.2"
CLIENT_GW = "10.0.0.3"
NAMES = (
    "amy",
    "bo",
    "chen",
    "dara",
    "eli",
    "fay",
    "gus",
    "hana",
    "ivo",
    "jo",
    "kim",
    "lea",
    "max",
    "nia",
    "omar",
    "pia",
    "quin",
    "rosa",
    "sol",
    "tia",
    "uma",
    "vic",
    "wes",
    "xan",
    "yara",
    "zed",
    "ada",
    "ben",
    "cy",
    "ned",
)
LINE = re.compile(r"^(\d+) (\S+) (OK|FAIL) (\S+)>(\S+)$")


def by_client(event):
    return event[2]


def by_gateway(event):
    return event[3]


def by_user(event):
    return event[0]


def _alarms(events, key, need, consecutive=True):
    """Users whose OK follows ``need`` FAILs under ``key(event)``, in event order."""
    run: dict = {}
    total: dict = {}
    hits: list[str] = []
    for event in events:
        user, result = event[0], event[1]
        k = key(event)
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


def _first(hits):
    return hits[0] if hits else None


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
            x1, x2, target, trap_user, latest, chatty, multi = names[:7]
            noise_names = names[7:]
            ips = rng.sample(clients_pool, 12 + k)
            f, c, h, d, z, p, q = ips[:7]
            spare = ips[7:12]
            attackers = ips[12:]
            attacker_users = rng.sample(noise_names, k)

            # Shared client f: K-1 fails then OK by x1, then one fail and OK by x2.
            block_f = [(x1, "FAIL", f, CLIENT_GW)] * (k - 1)
            block_f += [
                (x1, "OK", f, CLIENT_GW),
                (x2, "FAIL", f, CLIENT_GW),
                (x2, "OK", f, CLIENT_GW),
            ]
            # Chatty: many fails from one client through the trap gateway, never a success.
            block_z = [(chatty, "FAIL", z, TRAP_GW)] * (k + 2)
            # Multi: one user fails K-1 times from p and once from q, then succeeds from p.
            block_m = [(multi, "FAIL", p, CLIENT_GW)] * (k - 1)
            block_m += [(multi, "FAIL", q, EDGE_GW), (multi, "OK", p, CLIENT_GW)]
            # Gateway trap: K distinct clients fail through TRAP_GW, then trap_user succeeds.
            block_gw = [(attacker_users[i], "FAIL", attackers[i], TRAP_GW) for i in range(k)]
            block_gw += [(trap_user, "OK", d, TRAP_GW)]
            # Real alarm: target fails K times from c, then succeeds.
            block_c = [(target, "FAIL", c, EDGE_GW)] * k + [(target, "OK", c, EDGE_GW)]
            # Later alarm: latest, same shape from h.
            block_h = [(latest, "FAIL", h, EDGE_GW)] * k + [(latest, "OK", h, EDGE_GW)]
            events = block_f + block_z + block_m + block_gw + block_c + block_h

            spare_users = rng.sample([n_ for n_ in noise_names if n_ not in attacker_users], 5)
            for i in range(5):
                client = spare[i]
                user = spare_users[i]
                gw = rng.choice((EDGE_GW, CLIENT_GW))
                runs = rng.randint(0, k - 1)
                block = [(user, "FAIL", client, gw)] * runs + [(user, "OK", client, gw)]
                pos = rng.randint(0, len(events))
                events[pos:pos] = block

            correct = _alarms(events, by_client, k)
            if not correct or correct[0] != target:
                continue
            fails = Counter(e[0] for e in events if e[1] == "FAIL")
            top = max(fails.values())
            if fails[chatty] != top or sum(1 for n_ in fails.values() if n_ == top) != 1:
                continue
            decoys = [
                {"user": _first(_alarms(events, by_gateway, k))},
                {"user": _first(_alarms(events, by_client, k - 1))},
                {"user": _first(_alarms(events, by_client, k, consecutive=False))},
                {"user": _first(_alarms(events, by_user, k))},
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
        k = int(must_match(r"K = (\d+)", files["policy.txt"]).group(1))
        events = []
        for line in files["auth.log"].split("\n"):
            m = LINE.match(line.strip())
            if not m:
                continue
            _, user, result, client, gateway = m.groups()
            events.append((user, result, client, gateway))
        hits = _alarms(events, by_client, k)
        return {"user": hits[0]}


FAMILY = TwoHopAuth()
