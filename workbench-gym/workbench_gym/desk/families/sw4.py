# SPDX-License-Identifier: Apache-2.0

"""
sw4: endpoint SLO table from a gateway access log (software-engineering).

``access.log`` has one JSON object per request. Level 2 adds a deploy time (lines
before it do not count), retries that share a request_id (keep the last attempt)
and malformed lines. The answer has one row per endpoint: request count, the
share of 5xx responses, and the nearest-rank p95 latency.

Decoys: counting health checks, counting every retry, ignoring the deploy time,
and a floor instead of the nearest-rank position.
"""

import json
import math
import random
import re
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import csv_text, half_up

OUT = "output/endpoints.csv"
DEPLOY = "2026-10-03T12:00:00Z"
HEADER = ["endpoint", "requests", "error_rate", "p95_latency_ms"]
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TEMPLATES = [
    "/users/{id}",
    "/users/{id}/orders",
    "/orders/{uuid}",
    "/orders",
    "/search",
    "/cart/{id}/items",
    "/health",
]


def _endpoint(method: str, path: str) -> str:
    parts = ["{id}" if seg.isdigit() or UUID_RE.match(seg) else seg for seg in path.split("/")]
    return f"{method} {'/'.join(parts)}"


def _rows(
    text: str,
    deploy: str | None,
    keep_last: bool = True,
    drop_health: bool = True,
    rank: str = "ceil",
) -> list[list]:
    kept: dict[str, dict] = {}
    for line in text.splitlines():
        try:
            rec = json.loads(line)
            ts, path, method = str(rec["ts"]), str(rec["path"]), str(rec["method"])
            status, latency = int(rec["status"]), float(rec["latency_ms"])
            rid, attempt = str(rec["request_id"]), int(rec["attempt"])
        except (ValueError, KeyError, TypeError):
            continue
        if deploy is not None and ts < deploy:
            continue
        if drop_health and path == "/health":
            continue
        rec = {"ep": _endpoint(method, path), "status": status, "lat": latency, "att": attempt}
        if keep_last:
            if rid not in kept or attempt > kept[rid]["att"]:
                kept[rid] = rec
        else:
            kept[f"{rid}#{len(kept)}"] = rec
    groups: dict[str, list[dict]] = {}
    for rec in kept.values():
        groups.setdefault(rec["ep"], []).append(rec)
    rows = []
    for ep, recs in groups.items():
        n = len(recs)
        errors = sum(1 for r in recs if r["status"] >= 500)
        lat = sorted(r["lat"] for r in recs)
        k = math.ceil(0.95 * n) if rank == "ceil" else max(1, math.floor(0.95 * n))
        rows.append([ep, n, half_up(errors / n, 4), half_up(lat[k - 1], 1)])
    rows.sort(key=lambda r: (-int(r[1]), str(r[0])))
    return rows


def _uuid(rng: random.Random) -> str:
    a, b, c, d, e = (
        rng.getrandbits(32),
        rng.getrandbits(16),
        rng.getrandbits(12),
        0x8000 | rng.getrandbits(14),
        rng.getrandbits(48),
    )
    return f"{a:08x}-{b:04x}-4{c:03x}-{d:04x}-{e:012x}"


class Sw4(DeskFamily):
    id = "sw4"
    domain = "software-engineering"
    title = "Endpoint SLO table from an access log"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        n = 260 if level == 1 else 420
        records = []
        for i in range(n):
            hour = rng.randint(6, 23) if level == 1 else rng.randint(6, 20)
            ts = f"2026-10-03T{hour:02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}Z"
            path = rng.choice(TEMPLATES).replace("{id}", str(rng.randint(1, 99999)))
            path = path.replace("{uuid}", _uuid(rng))
            records.append(
                {
                    "ts": ts,
                    "method": rng.choice(["GET", "POST"]),
                    "path": path,
                    "status": rng.choices([200, 201, 404, 500, 503], [70, 8, 8, 8, 6])[0],
                    "latency_ms": round(rng.lognormvariate(4.3, 0.55), 1),
                    "request_id": f"r-{i:06d}",
                    "attempt": 1,
                }
            )
        if level == 2:
            for rec in rng.sample(records, k=n // 5):
                failed = dict(rec, status=503, attempt=1)
                rec["attempt"] = 2
                records.append(failed)
        records.sort(key=lambda r: (r["ts"], r["request_id"], r["attempt"]))
        lines = [json.dumps(r) for r in records]
        if level == 2:
            for junk in ['{"ts": "2026-10-03T14:00:00Z", "method": "GET"', "GET /orders 200 ?"]:
                lines.insert(rng.randint(0, len(lines)), junk)
        text = "\n".join(lines) + "\n"

        deploy = DEPLOY if level == 2 else None
        truth = _rows(text, deploy)
        decoys = [
            _rows(text, deploy, drop_health=False),
            _rows(text, deploy, rank="floor"),
        ]
        if level == 2:
            decoys.append(_rows(text, deploy, keep_last=False))
            decoys.append(_rows(text, None))
        if truth == decoys[0] or len(truth) < 4:
            return self.build(level, rng)

        rule_deploy = (
            f" Only lines whose ts is at or after the deploy time {DEPLOY} count."
            if level == 2
            else ""
        )
        rule_retry = (
            " When a request_id appears on more than one line, keep only the line with the "
            "highest attempt number."
            if level == 2
            else ""
        )
        rule_junk = " Lines that are not valid JSON are skipped." if level == 2 else ""
        instruction = (
            "You are on call for the orders platform. {root}/access.log holds one JSON object "
            "per request from the gateway, with the fields ts (UTC), method, path, status, "
            "latency_ms, request_id and attempt. Build the endpoint SLO table and save it to "
            "{root}/output/endpoints.csv.\n\n"
            "Rules:\n"
            "1. Drop lines whose path is exactly /health."
            + rule_junk
            + rule_deploy
            + rule_retry
            + "\n"
            "2. An endpoint is the method, a space, then the path, where every path segment "
            "that is all digits or a UUID is written as {id}. Example: GET /users/{id}/orders.\n"
            "3. For each endpoint: requests = the number of kept lines; error_rate = the share "
            "of them with status 500 or higher, rounded to 4 decimal places; p95_latency_ms = "
            "the 95th percentile of latency_ms by the nearest-rank method (sort ascending and "
            "take the value at 1-based rank ceil(0.95 * requests)), rounded to 1 decimal place.\n\n"
            "Output: a CSV with the exact header line endpoint,requests,error_rate,p95_latency_ms "
            "and one row per endpoint, sorted by requests descending and then endpoint ascending. "
            "Write plain numbers without thousands separators. Create the output folder if needed."
        )
        checks = [Check("text"), Check("int"), Check("num", tol=0.00011), Check("num", tol=0.051)]
        return DeskTask(
            instruction=instruction,
            files={"access.log": text},
            outputs=[
                CsvOut(
                    path=OUT,
                    header=tuple(HEADER),
                    columns=tuple(checks),
                    rows=tuple(tuple(r) for r in truth),
                    key=0,
                )
            ],
            oracle={OUT: csv_text(truth, HEADER)},
            decoys=[{OUT: csv_text(d, HEADER)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"endpoints\.csv", instruction)
        text = files["access.log"]
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        deploy = DEPLOY if DEPLOY in instruction else None
        return {OUT: csv_text(_rows(text, deploy), HEADER)}


FAMILY = Sw4()
