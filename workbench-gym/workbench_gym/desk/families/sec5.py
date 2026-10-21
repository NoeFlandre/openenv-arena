# SPDX-License-Identifier: Apache-2.0

"""
sec5: off-hours data egress from internal hosts (cybersecurity).

``flows.csv`` lists flows (flow_id, UTC timestamp, source and destination
address, port, bytes sent). ``assets.csv`` maps internal addresses to hosts and
``allowlist.txt`` lists approved external networks. Internal means RFC 1918;
external means anything else that is not allowlisted. Office time is UTC+2:
Monday to Friday, 08:00 up to 18:00 local time. Bytes sent to external
destinations outside office time are summed per host (MB = 10^6 bytes). Hosts
above 50 MB are reported with their largest off-hours destination.

Level 2 adds duplicate flow records (count each flow_id once) and a public
holiday in the notes (a whole local day counts as off-hours).

Decoys: counting office-hours flows, ignoring the allowlist, using UTC hours,
counting duplicates, and ignoring the holiday.
"""

import csv
import datetime as dt
import io
import ipaddress
import random
from collections import defaultdict
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import csv_text

OUT = "output/egress_report.csv"
HEADER = ["hostname", "external_mb", "top_destination"]
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
THRESHOLD_MB = 50.0
OFFSET = dt.timedelta(hours=2)
HOLIDAY = "2026-10-05"
FLOW_HEADER = ["flow_id", "timestamp", "src_ip", "dst_ip", "dst_port", "bytes_out"]
ASSET_HEADER = ["ip", "hostname", "owner"]


def _egress(
    flows: list[dict[str, str]],
    assets: dict[str, str],
    allow: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
    holidays: set[str],
    offset: dt.timedelta = OFFSET,
    use_allow: bool = True,
    dedupe: bool = True,
    count_office: bool = False,
) -> list[list]:
    totals: dict[str, int] = defaultdict(int)
    per_dst: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    seen: set[str] = set()
    for row in flows:
        if dedupe:
            if row["flow_id"] in seen:
                continue
            seen.add(row["flow_id"])
        src, dst = row["src_ip"].strip(), row["dst_ip"].strip()
        if src not in assets:
            continue
        dst_addr = ipaddress.ip_address(dst)
        if any(dst_addr in net for net in PRIVATE):
            continue
        if use_allow and any(dst_addr in net for net in allow):
            continue
        stamp = dt.datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).replace(
            tzinfo=None
        )
        local = stamp + offset
        in_office = (
            local.weekday() < 5
            and local.date().isoformat() not in holidays
            and 8 * 60 <= local.hour * 60 + local.minute < 18 * 60
        )
        if in_office and not count_office:
            continue
        size = int(row["bytes_out"])
        totals[assets[src]] += size
        per_dst[assets[src]][dst] += size
    rows = []
    for host, total in totals.items():
        if total / 1_000_000 <= THRESHOLD_MB:
            continue
        top = max(per_dst[host].items(), key=lambda kv: (kv[1], kv[0]))[0]
        rows.append([host, f"{total / 1_000_000:.2f}", top])
    rows.sort(key=lambda r: (-float(r[1]), r[0]))
    return rows


class Sec5(DeskFamily):
    id = "sec5"
    domain = "cybersecurity"
    title = "Off-hours data egress from internal hosts"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        hosts = [
            f"ws-{rng.choice(['ana', 'bo', 'chen', 'dara', 'eli', 'faro', 'gia', 'hana'])}-{i:02d}"
            for i in range(6)
        ]
        hosts = list(dict.fromkeys(hosts))
        assets = {f"10.20.{i}.{rng.randint(10, 200)}": h for i, h in enumerate(hosts)}
        allow_net = ipaddress.ip_network("203.0.113.0/27")
        allow = [allow_net]
        ext_pool = [
            f"{rng.choice([198, 185, 91, 151])}.{rng.randint(1, 250)}.{rng.randint(1, 250)}"
            f".{rng.randint(1, 250)}"
            for _ in range(12)
        ]
        ext_pool += [str(allow_net.network_address + rng.randint(1, 20)) for _ in range(3)]
        start = dt.datetime(2026, 10, 2, 0, 0)
        flows: list[dict[str, str]] = []
        for i in range(260):
            src = rng.choice(list(assets))
            when = start + dt.timedelta(minutes=rng.randint(0, 4 * 24 * 60))
            dst = (
                rng.choice(ext_pool)
                if rng.random() < 0.8
                else rng.choice(["10.20.0.5", "192.168.1.9"])
            )
            size = (
                rng.randint(10_000, 4_000_000)
                if rng.random() < 0.7
                else rng.randint(20_000_000, 90_000_000)
            )
            flows.append(
                {
                    "flow_id": f"F{i:05d}",
                    "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "src_ip": src,
                    "dst_ip": dst,
                    "dst_port": str(rng.choice([443, 80, 22, 8443])),
                    "bytes_out": str(size),
                }
            )
        heavy_src = rng.choice(list(assets))
        for k in range(4):
            when = dt.datetime(2026, 10, 3 + k % 2, 22, 0) + dt.timedelta(
                minutes=rng.randint(0, 30)
            )
            flows.append(
                {
                    "flow_id": f"F{260 + k:05d}",
                    "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "src_ip": heavy_src,
                    "dst_ip": rng.choice(ext_pool),
                    "dst_port": "443",
                    "bytes_out": str(rng.randint(30_000_000, 60_000_000)),
                }
            )
        holidays: set[str] = set()
        if level == 2:
            holiday_local = dt.date(2026, 10, 5)
            heavy = dt.datetime(2026, 10, 5, 9, 30) - OFFSET
            flows.append(
                {
                    "flow_id": f"F{300:05d}",
                    "timestamp": heavy.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "src_ip": rng.choice(list(assets)),
                    "dst_ip": rng.choice(ext_pool),
                    "dst_port": "443",
                    "bytes_out": str(rng.randint(60_000_000, 80_000_000)),
                }
            )
            holidays.add(holiday_local.isoformat())
            dupes = rng.sample(flows, k=12)
            flows.extend(dict(d) for d in dupes)
        rng.shuffle(flows)

        truth = _egress(flows, assets, allow, holidays)
        if len(truth) < 2:
            return None
        decoys = [
            _egress(flows, assets, allow, holidays, count_office=True),
            _egress(flows, assets, allow, holidays, use_allow=False),
            _egress(flows, assets, allow, holidays, offset=dt.timedelta(0)),
        ]
        if level == 2:
            decoys.append(_egress(flows, assets, allow, holidays, dedupe=False))
            decoys.append(_egress(flows, assets, allow, set()))
        if any(d == truth for d in decoys):
            return None

        files = {
            "flows.csv": csv_text(flows, FLOW_HEADER),
            "assets.csv": csv_text(
                [{"ip": ip, "hostname": h, "owner": "it"} for ip, h in assets.items()], ASSET_HEADER
            ),
            "allowlist.txt": "\n".join(str(n) for n in allow) + "\n",
        }
        extra = ""
        if level == 2:
            files["notes.md"] = (
                "# Notes\n"
                f"- {HOLIDAY} is a public holiday: the whole local day counts as outside office "
                "hours.\n"
                "- flows.csv can contain the same flow more than once; count each flow_id once.\n"
            )
            extra = " {root}/notes.md lists the holiday and a data-quality rule."
        instruction = (
            "The SOC wants the internal hosts that sent large amounts of data out of the office "
            "after hours. "
            "{root}/flows.csv lists the flows (flow_id, timestamp in UTC, src_ip, dst_ip, "
            "dst_port, bytes_out). "
            "{root}/assets.csv maps internal addresses to hosts. {root}/allowlist.txt lists "
            "approved external "
            "networks." + extra + "\n\n"
            "Rules:\n"
            "1. Internal sources are the addresses in assets.csv. A destination is external when "
            "it is not in "
            "10.0.0.0/8, 172.16.0.0/12 or 192.168.0.0/16 and not in an allowlisted network. Skip "
            "other flows.\n"
            "2. Office time is UTC+2 all year: Monday to Friday, 08:00 up to 18:00 local time. "
            "Convert each "
            "timestamp to local time first. Every other moment is outside office time.\n"
            "3. For each host, add the bytes_out of its external flows outside office time. MB = "
            "10^6 bytes.\n"
            "4. Report only hosts with more than 50.00 MB. top_destination is the external address "
            "that received "
            "the most of that host's bytes in these flows (on a tie, the higher address in text "
            "order).\n\n"
            "Output: a CSV at {root}/output/egress_report.csv with the exact header line "
            "hostname,external_mb,top_destination, one row per reported host, external_mb with 2 "
            "decimal places, "
            "sorted by external_mb from highest to lowest. Create the output folder if needed."
        )
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                CsvOut(
                    path=OUT,
                    header=tuple(HEADER),
                    columns=(Check("text"), Check("num", tol=0.011), Check("text")),
                    rows=tuple((r[0], float(r[1]), r[2]) for r in truth),
                )
            ],
            oracle={OUT: csv_text(truth, HEADER)},
            decoys=[{OUT: csv_text(d, HEADER)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"egress_report\.csv", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        flows = list(csv.DictReader(io.StringIO(text("flows.csv"))))
        assets = {
            r["ip"].strip(): r["hostname"].strip()
            for r in csv.DictReader(io.StringIO(text("assets.csv")))
        }
        allow = [
            ipaddress.ip_network(line.strip())
            for line in text("allowlist.txt").splitlines()
            if line.strip()
        ]
        holidays: set[str] = set()
        if "notes.md" in files:
            for line in text("notes.md").splitlines():
                if "public holiday" in line:
                    holidays.add(line.split()[1])
        return {OUT: csv_text(_egress(flows, assets, allow, holidays), HEADER)}


FAMILY = Sec5()
