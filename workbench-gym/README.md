# Workbench Desk

An [OpenEnv](https://github.com/meta-pytorch/OpenEnv) environment for the
[OpenEnv Arena](https://openenvarena-arena.hf.space/). Each episode is a small
desk job, modeled on the SkillsBench task shape: a prose instruction, input
files (CSV, XLSX, JSON, text) in a workspace, and output files that must hold
the right values in the asked format.

## Interface

The action and observation are `tbench2_env`-shaped in spirit but use three
tools, one JSON object per action:

- `{"tool": "bash", "args": {"command": "..."}}` runs a shell command in the
  workspace (as an unprivileged user, 20 s and 10 s CPU limit). Python 3 with
  pandas, numpy and openpyxl is on the path.
- `{"tool": "write", "args": {"path": "...", "content": "..."}}` writes a text
  file inside the workspace.
- `{"tool": "submit", "args": {}}` grades the output files the instruction
  names and ends the episode.

The first observation is the instruction with the workspace path filled in.
There are 20 calls per episode; after the last one the outputs are graded.

## Reward

An exact answer earns `1.0`. Otherwise, the mean of the valid-format fraction
and correct-value fraction gives partial credit, capped at `0.2`. Missing or
unparseable values do not count as valid format; an absent output file or wrong
CSV header scores `0.0`.

## Families

Each family (`workbench_gym/desk/families/<id>.py`) builds fresh instances from a
seeded random generator, has two levels (`<id>-L1`, `<id>-L2`), a reference
solver that works from the files alone, and decoys (plausible wrong answers).
Level 2 adds real-data traps: status rows, revisions, unit lines, sentinel
values and corrections in a notes file.

Domains: software engineering, industrial and physical systems, natural science,
office and white-collar work, finance and economics, math and formal reasoning,
cybersecurity, media and content production.

## Check

```sh
uv run ruff format --check . && uv run ruff check . && uv run ty check
uv run pytest
uv run python -m tests.desk_gates fin4 60   # gates for one family
```

## Layout

| Path | Contents |
| --- | --- |
| `workbench_gym/desk/environment.py` | Episode logic: workspace, tools, grading |
| `workbench_gym/desk/spec.py` | Output checks (JSON, CSV, text, XLSX) and the reward rule |
| `workbench_gym/desk/shell.py` | Sandboxed `bash` for the agent |
| `workbench_gym/desk/families/` | One module per task family |
| `tests/desk_gates.py` | Quality gates every family must pass |
| `tests/test_desk.py` | Tool, grading and workspace-safety tests, and the gates for every family |

## Build

```sh
export DOCKER_DEFAULT_PLATFORM=linux/amd64
docker build -t ghcr.io/noeflandre/workbench-gym:v6 .
```

The Dockerfile reuses the published v5 image by digest for its pinned server
and agent dependencies, then copies the v6 source and configuration.

The image serves the server on port 8000 (`/health`, `/schema`, `/ws`).
