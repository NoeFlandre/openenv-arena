# SPDX-License-Identifier: Apache-2.0

"""
math5: shortest delivery route on a road graph (mathematics-or-formal-reasoning).

``roads.csv`` lists road segments (from, to, km, oneway) and ``closures.txt``
the closed segments. The van starts at depot D0 and must reach the customer
named in the instruction. Distances are whole tenths of a km, so the total is
exact. The generator keeps only instances whose shortest route is unique.

Decoys: ignoring the closures, ignoring one-way roads, and counting each one-way
road in both directions.
"""

import csv
import heapq
import io
import json
import random
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match
from ._common import csv_text

OUT = "output/route.json"
DEPOT = "D0"


def _graph(
    roads: list[tuple[str, str, int, bool]],
    closed: set[tuple[str, str]],
    use_closures: bool = True,
    use_oneway: bool = True,
) -> dict[str, list[tuple[str, int]]]:
    """Driving arcs. A closed pair (u, v) blocks the drive from u to v only."""
    graph: dict[str, list[tuple[str, int]]] = {}
    for a, b, tenths, oneway in roads:
        arcs = [(a, b)] if (oneway and use_oneway) else [(a, b), (b, a)]
        for u, v in arcs:
            if use_closures and (u, v) in closed:
                continue
            graph.setdefault(u, []).append((v, tenths))
    return graph


def _rounded_total(graph: dict[str, list[tuple[str, int]]], route: list[str]) -> int:
    """The same route with each road rounded to whole km (a wrong answer from early rounding)."""
    total = 0
    for u, v in zip(route, route[1:], strict=False):
        w = min(x for y, x in graph[u] if y == v)
        total += (w + 5) // 10 * 10
    return total


def _hop_route(graph: dict[str, list[tuple[str, int]]], target: str) -> tuple[int, list[str]]:
    """The route with the fewest junctions, and its length (a hurried driver's wrong answer)."""
    prev: dict[str, str] = {DEPOT: DEPOT}
    queue = [DEPOT]
    for u in queue:
        for v, _ in graph.get(u, []):
            if v not in prev:
                prev[v] = u
                queue.append(v)
    if target not in prev:
        return -1, []
    route = [target]
    while route[-1] != DEPOT:
        route.append(prev[route[-1]])
    route.reverse()
    total = 0
    for u, v in zip(route, route[1:], strict=False):
        total += min(w for x, w in graph[u] if x == v)
    return total, route


def _shortest(graph: dict[str, list[tuple[str, int]]], target: str) -> tuple[int, list[str], bool]:
    """Shortest distance (tenths of km), one route, and whether that route is unique."""
    dist = {DEPOT: 0}
    count = {DEPOT: 1}
    prev: dict[str, str] = {}
    heap = [(0, DEPOT)]
    done: set[str] = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        for v, w in graph.get(u, []):
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                count[v] = count[u]
                prev[v] = u
                heapq.heappush(heap, (nd, v))
            elif nd == dist[v] and v not in done:
                count[v] += count[u]
    if target not in dist:
        return -1, [], False
    route = [target]
    while route[-1] != DEPOT:
        route.append(prev[route[-1]])
    route.reverse()
    return dist[target], route, count[target] == 1


def _answer(dist: int, route: list[str]) -> dict:
    return {"distance_km": round(dist / 10, 1), "route": route}


class Math5(DeskFamily):
    id = "math5"
    domain = "mathematics-or-formal-reasoning"
    title = "Shortest delivery route with closures"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        n = rng.randint(24, 40)
        names = [DEPOT] + [f"J{i:02d}" for i in range(1, n)]
        roads: list[tuple[str, str, int, bool]] = []
        seen: set[frozenset[str]] = set()
        for i in range(1, n):
            j = rng.randrange(0, i)
            roads.append((names[i], names[j], rng.randint(12, 150), False))
            seen.add(frozenset((names[i], names[j])))
        for _ in range(n * 2):
            a, b = rng.sample(names, 2)
            if frozenset((a, b)) in seen:
                continue
            seen.add(frozenset((a, b)))
            oneway = level == 2 and rng.random() < 0.25
            roads.append((a, b, rng.randint(12, 150), oneway))
        closed: set[tuple[str, str]] = set()
        if level == 2:
            for a, b, _, oneway in rng.sample(roads, 3):
                closed.add((a, b))
                if not oneway:
                    closed.add((b, a))
        target = names[rng.randint(n // 2, n - 1)]

        graph = _graph(roads, closed)
        dist, route, unique = _shortest(graph, target)
        if dist < 0 or not unique or len(route) < 4:
            return None
        truth = _answer(dist, route)
        decoys = [_answer(*_hop_route(graph, target)), _answer(_rounded_total(graph, route), route)]
        if level == 2:
            decoys.append(
                _answer(*_shortest(_graph(roads, closed, use_closures=False), target)[:2])
            )
            decoys.append(_answer(*_shortest(_graph(roads, closed, use_oneway=False), target)[:2]))
        if any(d == truth for d in decoys) or any(d["distance_km"] < 0 for d in decoys):
            return None

        road_rows = [
            {"from": a, "to": b, "km": f"{t // 10}.{t % 10}", "oneway": int(o)}
            for a, b, t, o in roads
        ]
        files = {"roads.csv": csv_text(road_rows, ["from", "to", "km", "oneway"])}
        if level == 2:
            files["closures.txt"] = "\n".join(f"{a}-{b}" for a, b in sorted(closed)) + "\n"
        closure_text = (
            " {root}/closures.txt lists closed drives, one per line as from-to: the drive from the "
            "first junction "
            "to the second is closed. Both directions of a two-way road are listed when it is "
            "closed."
            if level == 2
            else ""
        )
        oneway_text = (
            " A road with oneway 1 can be driven only from its from junction to its to junction."
            if level == 2
            else " Every road can be driven in both directions."
        )
        instruction = (
            "Dispatch needs the shortest drive for the van from the depot D0 to customer "
            f"{target}. {{root}}/roads.csv lists the road segments: from, to, km (text in km with "
            "one "
            "decimal place) and oneway (1 or 0)."
            + oneway_text
            + closure_text
            + "\n\nFind the route with the smallest total length. Use only the roads described "
            "above. "
            "Output: a JSON object at {root}/output/route.json with the keys distance_km (the "
            "total length, "
            "rounded to 1 decimal place) and route (the list of junction ids in driving order, "
            "starting at "
            "D0 and ending at "
            f"{target}). Create the output folder if needed."
        )
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                JsonOut(
                    path=OUT,
                    checks={"distance_km": Check("num", tol=0.051), "route": Check("list")},
                    want=truth,
                )
            ],
            oracle={OUT: json.dumps(truth)},
            decoys=[{OUT: json.dumps(d)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"route\.json", instruction)
        target = must_match(r"to customer (J\d+)\.", instruction).group(1)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        roads = [
            (r["from"], r["to"], int(r["km"].replace(".", "")), r["oneway"] == "1")
            for r in csv.DictReader(io.StringIO(text("roads.csv")))
        ]
        closed: set[tuple[str, str]] = set()
        if "closures.txt" in files:
            for line in text("closures.txt").split():
                a, b = line.split("-")
                closed.add((a, b))
        dist, route, _ = _shortest(_graph(roads, closed), target)
        return {OUT: json.dumps(_answer(dist, route))}


FAMILY = Math5()
