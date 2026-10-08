# SPDX-License-Identifier: Apache-2.0

"""
Log Triage environment.

Each task is a service log generated from a fixed seed. The agent is asked
which service first returned an HTTP 5xx after a deploy. It searches the log
with ``grep`` and ends the episode with ``answer``. Reward is 1.0 for the
right service and 0.0 otherwise.
"""

import random
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from ..models import LogTriageAction, LogTriageObservation

QUESTION = (
    "A deploy ran at 12:20:00. Which service first returned an HTTP 5xx after the deploy? "
    'Reply {"grep": "<text>"} to search the log (up to 10 matching lines), '
    'or {"answer": "<service>"} to finish.'
)

SERVICES = [
    "api-gateway",
    "auth",
    "billing",
    "cart",
    "catalog",
    "checkout",
    "inventory",
    "notifier",
    "payments",
    "search",
]
PATHS = ["/v1/orders", "/v1/login", "/v1/search", "/v1/cart", "/v1/charge", "/health"]
OK_STATUSES = [200, 200, 200, 204, 301, 404, 429]
ERROR_STATUSES = [500, 502, 503, 504]

WINDOW_START = 12 * 3600  # 12:00:00
DEPLOY_TIME = 12 * 3600 + 20 * 60  # 12:20:00
WINDOW_END = 13 * 3600  # 13:00:00

MAX_STEPS = 10
MAX_MATCHES = 10

# Task id -> seed. Every task is in the train split.
TASKS = {f"log-{i:02d}": 1000 + i for i in range(12)}

# Shared by all instances. The HTTP server builds a new instance per request,
# so the episode must live outside the instance. The arena runs one episode
# per sandbox at a time.
_episode: dict | None = None


def _clock(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def make_log(seed: int) -> tuple[list[str], str]:
    """Build the log for ``seed``. Returns the lines and the correct answer."""
    rng = random.Random(seed)
    services = rng.sample(SERVICES, 6)
    deploy_service = rng.choice(services)
    release = f"v{rng.randint(1, 9)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"

    used = {DEPLOY_TIME}

    def pick_time(low: int, high: int) -> int:
        # Distinct seconds keep the answer unique.
        while True:
            t = rng.randrange(low, high)
            if t not in used:
                used.add(t)
                return t

    # (second, service, status)
    events: list[tuple[int, str, int]] = []
    for _ in range(rng.randint(1, 2)):
        events.append(
            (pick_time(WINDOW_START, DEPLOY_TIME), rng.choice(services), rng.choice(ERROR_STATUSES))
        )
    for _ in range(rng.randint(30, 40)):
        events.append(
            (pick_time(WINDOW_START, WINDOW_END), rng.choice(services), rng.choice(OK_STATUSES))
        )
    for service in rng.sample(services, rng.randint(2, 3)):
        events.append((pick_time(DEPLOY_TIME + 1, WINDOW_END), service, rng.choice(ERROR_STATUSES)))

    lines = []
    for second, service, status in events:
        path = rng.choice(PATHS)
        latency = rng.randint(20, 900)
        lines.append(
            (
                second,
                f"{_clock(second)} {service:<11} status={status} path={path} latency={latency}ms",
            )
        )
    lines.append(
        (
            DEPLOY_TIME,
            f"{_clock(DEPLOY_TIME)} deploy      release={release} service={deploy_service}",
        )
    )
    lines.sort()

    # The answer comes from the log itself: the earliest 5xx after the deploy.
    first_failure = min(
        (second, service)
        for second, service, status in events
        if second > DEPLOY_TIME and status >= 500
    )
    return [text for _, text in lines], first_failure[1]


class LogTriageEnvironment(Environment):
    """Find the service that first failed after a deploy, using grep on a log."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ) -> LogTriageObservation:
        global _episode
        task_id = task_id or next(iter(TASKS))
        if task_id not in TASKS:
            raise ValueError(f"unknown task_id {task_id!r}")

        lines, answer = make_log(TASKS[task_id])
        _episode = {
            "episode_id": episode_id or str(uuid4()),
            "task_id": task_id,
            "lines": lines,
            "answer": answer,
            "steps": 0,
            "done": False,
            "reward": 0.0,
        }
        return self._observation(output="", done=False, reward=0.0)

    def step(
        self,
        action: LogTriageAction,
        timeout_s: float | None = None,
        **kwargs,
    ) -> LogTriageObservation:  # type: ignore[override]
        ep = self._require_episode()
        if ep["done"]:
            return self._observation(output="the episode is over", done=True, reward=ep["reward"])

        ep["steps"] += 1
        if action.answer is not None and action.grep is None:
            correct = action.answer.strip().lower() == ep["answer"]
            return self._finish(1.0 if correct else 0.0, "correct" if correct else "wrong")
        if action.grep is not None and action.answer is None:
            needle = action.grep.lower()
            matches = [line for line in ep["lines"] if needle in line.lower()]
            output = "\n".join(matches[:MAX_MATCHES]) or "no matching lines"
            if len(matches) > MAX_MATCHES:
                output += f"\n({len(matches)} matches, first {MAX_MATCHES} shown)"
        else:
            output = "send exactly one of grep or answer"

        if ep["steps"] >= MAX_STEPS:
            return self._finish(0.0, output + "\nno steps left")
        return self._observation(output=output, done=False, reward=0.0)

    @property
    def state(self) -> State:
        ep = _episode or {}
        return State(episode_id=ep.get("episode_id"), step_count=ep.get("steps", 0))

    def _require_episode(self) -> dict:
        if _episode is None:
            raise RuntimeError("call reset() before step()")
        return _episode

    def _finish(self, reward: float, output: str) -> LogTriageObservation:
        ep = self._require_episode()
        ep["done"] = True
        ep["reward"] = reward
        return self._observation(output=output, done=True, reward=reward)

    def _observation(self, output: str, done: bool, reward: float) -> LogTriageObservation:
        ep = self._require_episode()
        return LogTriageObservation(
            task_id=ep["task_id"],
            question=QUESTION if ep["steps"] == 0 else "",
            output=output,
            steps_left=max(0, MAX_STEPS - ep["steps"]),
            done=done,
            reward=reward,
        )
