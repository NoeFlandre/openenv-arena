# SPDX-License-Identifier: Apache-2.0

"""
Write the submission request and the public dataset folder from the final task list.

Inputs:
  --tasks   JSONL from tools/select.py or the stability step (task_id, family, domain, level, ...)
  --schema  the live GET /schema JSON from the running image (action and observation are copied)
  --outdir  folder to write into

Outputs:
  OUTDIR/submission.json   the request for the arena (not sent by this script)
  OUTDIR/dataset/tasks.jsonl  one public task per line (ids and calibration counts, no answers)
  OUTDIR/dataset/README.md    dataset card

The dataset carries no answer keys. The reference solvers live in the public
source tree, as in every other arena entry.
"""

import argparse
import json
import os

IMAGE = "ghcr.io/noeflandre/workbench-gym:v1"
SUBMISSION_ID = "workbench-gym-v1"
DATASET = "NoeFlandre/workbench-gym"
SOURCE = "https://github.com/NoeFlandre/openenv-arena/tree/workbench-gym-v1/workbench-gym"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    with open(args.tasks, encoding="utf-8") as fh:
        tasks = [json.loads(line) for line in fh if line.strip()]
    with open(args.schema, encoding="utf-8") as fh:
        schema = json.load(fh)

    submission = {
        "submission_id": SUBMISSION_ID,
        "name": "Workbench Gym",
        "image": IMAGE,
        "schema": {"action": schema["action"], "observation": schema["observation"]},
        "tasks": [
            {
                "task_id": t["task_id"],
                "split": "train",
                "reset_wall_s": 180,
                "rollout_wall_s": 1800,
                "verifier_wall_s": 120,
                "tool_wall_s": 30,
                "tool_calls_total": 12,
            }
            for t in tasks
        ],
        "example_actions": [
            {"tool": "ls", "args": {}},
            {"tool": "submit", "args": {"answer": {"x": 0}}},
        ],
        "finish_action": {"tool": "submit", "args": {"answer": None}},
        "dataset": DATASET,
        "source": SOURCE,
    }

    dataset_dir = os.path.join(args.outdir, "dataset")
    os.makedirs(dataset_dir, exist_ok=True)
    with open(os.path.join(args.outdir, "submission.json"), "w", encoding="utf-8") as fh:
        json.dump(submission, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(dataset_dir, "tasks.jsonl"), "w", encoding="utf-8") as fh:
        for t in tasks:
            public = {k: t[k] for k in ("task_id", "family", "domain", "level") if k in t}
            for key in ("stage_a", "stage_b", "stability"):
                if key in t:
                    public[key] = t[key]
            fh.write(json.dumps(public) + "\n")

    domains = sorted({t["domain"] for t in tasks})
    card = [
        "---",
        "license: apache-2.0",
        "task_categories:",
        "- reinforcement-learning",
        "tags:",
        "- openenv",
        "- workbench",
        "---",
        "",
        "# Workbench Gym tasks",
        "",
        f"{len(tasks)} train tasks for the Workbench Gym OpenEnv environment. "
        f"Each task id is a family and a level, for example `sw2-L3`. "
        "Each reset draws a fresh instance.",
        "",
        "Each episode gives a small workspace of text files. "
        "The agent reads them with `ls`, `read`, "
        "`grep` and `py` (stdlib Python on a copy of the files), then submits a JSON answer. "
        "Reward is 1.0 when every answer field is correct, and below 0.5 for some correct fields.",
        "",
        "## Domains",
        "",
        *[f"- {d}" for d in domains],
        "",
        "## Calibration",
        "",
        "Each task was played with Qwen/Qwen3.8-27B (thinking off) "
        "through the Hugging Face router. "
        "`stage_a` and `stage_b` count solves out of episodes. "
        "Tasks were kept in the mixed-outcome band.",
        "",
        "## Files",
        "",
        "- `tasks.jsonl`: task ids and calibration counts. No answers are included.",
        "",
        f"Source and reference solvers: {SOURCE}",
        "",
    ]
    with open(os.path.join(dataset_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(card))
    print(f"wrote {args.outdir}/submission.json with {len(tasks)} tasks")


if __name__ == "__main__":
    main()
