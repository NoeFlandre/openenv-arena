---
license: apache-2.0
task_categories:
  - reinforcement-learning
language:
  - en
tags:
  - openenv
  - procedural-generation
  - tool-use
configs:
  - config_name: workbench-desk-v7
    default: true
    data_files:
      - split: train
        path: tasks_v7.jsonl
---

# Workbench Desk v7

Workbench Desk trains file inspection, numerical analysis, and production of
verified output files through shell and file tools. It contains 34 task IDs,
with two difficulty levels for each of 17 procedural families across the
Arena's eight domains. Each reset creates fresh data from a server-selected
random seed. Training uses the public container image, which contains all
generators, assets, and grading code. It downloads nothing at startup.

The task manifest is `tasks_v7.jsonl`. The complete environment source and
reference solvers are under `releases/v7/source/`, with the pinned OpenEnv wheel.
Historical task manifests remain available in this dataset.

## Actions and rewards

The tools are `bash`, `write`, and `submit`. A task starts with a prose
instruction and files such as CSV, XLSX, JSON, and logs. The instruction names
the required output files. The agent has 20 calls, and `submit` ends the episode.
The finish action is `{"tool":"submit","args":{}}`.

An exact answer earns 1. Otherwise, reward equals 0.1 times the fraction of
checked values in a valid format, plus 0.1 times the fraction of correct
values, capped at 0.2. Missing output files earn 0. Invalid values never earn
full reward. The grader reads bounded regular files and rejects symbolic
links. Agent shell commands run as an unprivileged user with CPU, memory,
output, and wall-clock limits. The grader is inaccessible to that user.

Level 2 adds data interpretation issues such as revisions, status rows, units,
sentinel values, and corrections in notes. Task families include finance,
science, math, media, office analysis, industrial systems, software, and
security. The source includes independent solvers that derive results from
input files and instructions, plus plausible wrong-answer controls.

## Verification and limits

The release is checked through an anonymous pull of its public amd64 image,
the pinned OpenEnv validator, and 204 fresh WebSocket episodes. Each task has
exact-answer, empty, malformed, wrong-answer, example, and finish controls.
Reference solvers operate on generated input files. No LLM inference or model
calibration is used to select this release. These checks establish environment
behavior; they do not predict improvement on private Arena tasks.

The release manifest links the exact image digest, source commit, and public
verification run. A prior v6 release scored 3/40 on the Arena evaluation.
No v7 training or evaluation result exists before an approved submission.
