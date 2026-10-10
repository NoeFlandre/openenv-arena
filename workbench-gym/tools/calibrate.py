# SPDX-License-Identifier: Apache-2.0

"""
Calibrate task difficulty against the target model.

Plays fresh episodes of each task with Qwen/Qwen3.8-27B through the Hugging Face
inference router, thinking off. Replies are parsed strictly, the way the arena
does: a reply must be exactly one JSON object, or the episode ends with the
finish action (reward 0). One JSON line per episode goes to --out.

The token is read from HF_TOKEN and sent as a header. It is never printed or
written to a file.

Usage:
  PYTHONPATH=. python tools/calibrate.py --tasks sw1-L1,med2-L1 --episodes 8 --out runs/a.jsonl
"""

import argparse
import asyncio
import json
import os
import random
import secrets
import sys
import time

import httpx

from workbench_gym.core.protocol import MAX_CALLS
from workbench_gym.families import load_families
from workbench_gym.models import WorkbenchAction
from workbench_gym.server.environment import WorkbenchEnvironment

ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"
MODEL = "Qwen/Qwen3.8-27B:deepinfra"
MAX_REPLY_TOKENS = 1024
FINISH = {"tool": "submit", "args": {"answer": None}}

SYSTEM = (
    "You work in a small workspace of files. Each reply is exactly one JSON object and "
    "nothing else: a tool call such as {\"tool\":\"ls\",\"args\":{\"path\":\"\"}}, or "
    "{\"tool\":\"submit\",\"args\":{\"answer\":{...}}} to finish. No prose, no code fences."
)


def parse_reply(text: str) -> dict | None:
    """Strict: the whole reply must be one JSON object with a tool key."""
    try:
        value = json.loads(text.strip())
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or "tool" not in value:
        return None
    return value


async def chat(client: httpx.AsyncClient, token: str, messages: list[dict]) -> tuple[str, str, int]:
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_REPLY_TOKENS,
        "temperature": 0.7,
        "top_p": 0.8,
        "presence_penalty": 1.5,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    for attempt in range(6):
        resp = await client.post(
            ROUTER_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            await asyncio.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        return choice["message"].get("content") or "", choice.get("finish_reason") or "", tokens
    raise RuntimeError("router kept failing")


async def play(task_id: str, seed: int, client: httpx.AsyncClient, token: str) -> dict:
    env = WorkbenchEnvironment(families=FAMILIES)
    obs = env.reset(task_id=task_id, seed=seed)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps({"output": obs.output, "ok": True, "calls_left": MAX_CALLS})},
    ]
    record = {
        "task_id": task_id,
        "seed": seed,
        "reward": 0.0,
        "solved": False,
        "calls": 0,
        "invalid": 0,
        "truncated": 0,
        "completion_tokens": 0,
        "ended": "",
    }
    done = False
    while not done:
        reply, finish_reason, tokens = await chat(client, token, messages)
        record["completion_tokens"] += tokens
        if finish_reason == "length":
            record["truncated"] += 1
        action_dict = parse_reply(reply)
        if action_dict is None:
            record["invalid"] += 1
            record["ended"] = "invalid_reply"
            obs = env.step(WorkbenchAction.model_validate(FINISH))
            record["reward"] = obs.reward
            break
        record["calls"] += 1
        obs = env.step(WorkbenchAction.model_validate(action_dict))
        done = obs.done
        if done:
            record["reward"] = obs.reward
            record["ended"] = "submit" if action_dict.get("tool") == "submit" else "call_cap"
            break
        messages.append({"role": "assistant", "content": reply.strip()})
        messages.append({"role": "user", "content": json.dumps({"output": obs.output, "ok": obs.ok, "calls_left": obs.calls_left})})
    record["solved"] = record["reward"] == 1.0
    return record


async def run(tasks: list[str], episodes: int, out: str, concurrency: int, seed_base: int) -> None:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        sys.exit("HF_TOKEN is not set")
    rng = random.Random(seed_base or secrets.randbits(32))
    jobs = [(task, rng.getrandbits(62)) for task in tasks for _ in range(episodes)]
    semaphore = asyncio.Semaphore(concurrency)
    started = time.time()
    with open(out, "a", encoding="utf-8") as fh:
        async with httpx.AsyncClient() as client:

            async def one(task: str, seed: int) -> None:
                async with semaphore:
                    try:
                        record = await play(task, seed, client, token)
                    except Exception as exc:  # noqa: BLE001 - keep the run going, log the failure
                        record = {"task_id": task, "seed": seed, "error": type(exc).__name__}
                    record["model"] = MODEL
                    fh.write(json.dumps(record) + "\n")
                    fh.flush()

            await asyncio.gather(*(one(task, seed) for task, seed in jobs))
    print(f"{len(jobs)} episodes in {time.time() - started:.0f} s -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", required=True, help="comma list of task ids, or 'all'")
    parser.add_argument("--episodes", type=int, default=8)
    parser.add_argument("--out", required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed-base", type=int, default=0, help="0 means random")
    args = parser.parse_args()
    global FAMILIES
    FAMILIES = load_families()
    if args.tasks == "all":
        tasks = [f"{fid}-L{lv}" for fid in sorted(FAMILIES) for lv in FAMILIES[fid].levels]
    else:
        tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    asyncio.run(run(tasks, args.episodes, args.out, args.concurrency, args.seed_base))


if __name__ == "__main__":
    main()
