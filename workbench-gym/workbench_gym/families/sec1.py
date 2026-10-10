# SPDX-License-Identifier: Apache-2.0

"""
sec1: authorization audit (cybersecurity).

``policy.txt`` lists coded rules. A rule fails for a request when its "if" part
holds and its "then" part does not; a "deny if" rule fails whenever its part
holds. ``requests.txt`` lists access requests as field=value pairs. The answer
has two set fields: ``allowed`` (users that fail no rule) and ``denied``
([user, code] for every failing rule, not just the first one). Decoys: only the
first failing rule per user, the last rule ignored, and deny rules ignored.
"""

import random
import re

from ..core.grading import Field, answer_size
from .base import Built, Family

RULE_COUNT = {1: 3, 2: 5, 3: 7}
USER_COUNT = 6
ANSWER_LIMIT = 260
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
FIELDS = {
    "role": ("admin", "dev", "viewer"),
    "team": ("eng", "fin", "ops", "contractor"),
    "env": ("prod", "stage"),
    "res": ("billing", "wiki", "deploy"),
    "act": ("read", "write", "delete"),
    "mfa": ("yes", "no"),
    "ip": ("corp", "vpn", "public"),
    "tkt": ("yes", "no"),
}

# (when, need): when is a tuple of (field, value); need is (field, allowed values) or None for deny.
POOL = (
    ((("act", "write"),), ("mfa", ("yes",))),
    ((("env", "prod"),), ("role", ("dev", "admin"))),
    ((("res", "billing"),), ("tkt", ("yes",))),
    ((("env", "prod"),), ("ip", ("corp",))),
    ((("act", "delete"),), ("role", ("admin",))),
    ((("team", "contractor"), ("res", "billing")), None),
    ((("ip", "public"),), None),
    ((("team", "contractor"),), ("ip", ("corp", "vpn"))),
)


def _rule_line(code, when, need):
    cond = " and ".join(f"{f}={v}" for f, v in when)
    if need is None:
        return f"{code} deny if {cond}"
    field, vals = need
    target = f"{field}={vals[0]}" if len(vals) == 1 else f"{field} in {','.join(vals)}"
    return f"{code} if {cond} then {target}"


def _fails(req, when, need):
    if not all(req.get(f) == v for f, v in when):
        return False
    if need is None:
        return True
    field, vals = need
    return req.get(field) not in vals


def _audit(reqs, rules, first_only=False):
    allowed, denied = [], []
    for user, req in reqs.items():
        bad = [code for code, when, need in rules if _fails(req, when, need)]
        if not bad:
            allowed.append(user)
        elif first_only:
            denied.append([user, bad[0]])
        else:
            denied.extend([user, code] for code in bad)
    return {"allowed": sorted(allowed), "denied": sorted(denied)}


def _key(answer):
    return (
        tuple(sorted(answer["allowed"])),
        tuple(sorted(tuple(p) for p in answer["denied"])),
    )


class AuthorizationAudit(Family):
    id = "sec1"
    domain = "cybersecurity"
    title = "Authorization audit"

    def build(self, level: int, rng: random.Random) -> Built:
        count = RULE_COUNT[level]
        while True:
            chosen = rng.sample(POOL, count)
            rules = [(f"R{i + 1}", when, need) for i, (when, need) in enumerate(chosen)]
            names = rng.sample(NAMES, USER_COUNT)
            reqs = {name: {f: rng.choice(vals) for f, vals in FIELDS.items()} for name in names}
            answer = _audit(reqs, rules)
            if not 1 <= len(answer["allowed"]) <= USER_COUNT - 1:
                continue
            if len(answer["denied"]) < 3:
                continue
            if answer_size(answer) > ANSWER_LIMIT:
                continue
            multi = sum(
                1 for u in reqs if sum(1 for _, w, n in rules if _fails(reqs[u], w, n)) >= 2
            )
            if multi < 1:
                continue
            decoys = [
                _audit(reqs, rules, first_only=True),
                _audit(reqs, rules[:-1]),
                _audit(reqs, [r for r in rules if r[2] is not None]),
            ]
            if any(_key(d) == _key(answer) for d in decoys):
                continue
            break

        policy = "\n".join(
            [
                "Access rules. A rule fails when its if-part holds and its then-part does not.",
                "A deny-if rule fails whenever its part holds.",
            ]
            + [_rule_line(code, when, need) for code, when, need in rules]
        )
        request_lines = [
            name + " " + " ".join(f"{f}={reqs[name][f]}" for f in FIELDS) for name in names
        ]
        requests = "\n".join(request_lines)
        return Built(
            question=(
                "policy.txt holds access rules and requests.txt holds access requests. Which "
                "users pass every rule (allowed), and which [user, rule] pairs fail, one per "
                "failing rule (denied)?"
            ),
            files={"policy.txt": policy + "\n", "requests.txt": requests + "\n"},
            fields={"allowed": Field("set"), "denied": Field("set")},
            answer=answer,
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        rules = []
        for line in files["policy.txt"].split("\n"):
            m = re.match(r"^(R\d+) (deny if|if) (.*)$", line.strip())
            if not m:
                continue
            code, kind, rest = m.groups()
            if kind == "deny if":
                when_text, need = rest, None
            else:
                when_text, target = rest.split(" then ")
                if " in " in target:
                    field, vals = target.split(" in ")
                    need = (field, tuple(vals.split(",")))
                else:
                    field, val = target.split("=")
                    need = (field, (val,))
            when = tuple(tuple(c.split("=")) for c in when_text.split(" and "))
            rules.append((code, when, need))

        allowed, denied = [], []
        for line in files["requests.txt"].split("\n"):
            parts = line.split()
            if len(parts) < 2 or "=" not in parts[1]:
                continue
            user = parts[0]
            req = dict(p.split("=", 1) for p in parts[1:])
            bad = [code for code, when, need in rules if _fails(req, when, need)]
            if not bad:
                allowed.append(user)
            else:
                denied.extend([user, code] for code in bad)
        return {"allowed": sorted(allowed), "denied": sorted(denied)}


FAMILY = AuthorizationAudit()
