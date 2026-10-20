# Workbench Gym

An [OpenEnv](https://github.com/meta-pytorch/OpenEnv) environment for the [OpenEnv Arena](https://openenvarena-arena.hf.space/).

Each episode gives one task from one of eight domains. The task is a small
workspace: text files that the agent reads with `ls`, `read`, `grep` and `py`
(stdlib Python on a copy of the files). The agent has 12 tool calls. It ends
with `submit`, which takes a JSON answer with named fields.

Reward is `1.0` when every field is correct. Partial credit (below `0.5`) is
given for some correct fields. It is `0.0` otherwise.

## Terminal Workbench (v4)

From v4 the image serves the same task families behind the interface of
OpenEnv's `tbench2_env` (same action and observation fields):

- `{"action_type": "exec", "command": "..."}` runs a shell command (as an
  unprivileged user, 20 s limit) in the episode's working directory.
- `{"action_type": "write_file", "file_path": "answer.json", "content": "..."}`
  writes a file inside that directory.
- `{"action_type": "evaluate"}` grades `answer.json` and ends the episode.

Reward is 1.0 when `answer.json` holds every answer field correctly and 0.0
otherwise. Every observation repeats the instruction. After 32 actions the
answer file is evaluated. Code: `workbench_gym/terminal/`, tests:
`tests/test_terminal.py`.

## Layout

| Path | Contents |
| --- | --- |
| `workbench_gym/core/` | Grading, file store, `py` sandbox, episode protocol |
| `workbench_gym/families/` | One module per task family (`sw1`, `med2`, ...) |
| `workbench_gym/server/` | OpenEnv environment and HTTP/WebSocket server |
| `tests/gates.py` | Quality gates every family must pass |
| `tests/` | Framework tests and family gate tests |

## Check

```sh
PYTHONPATH=. python -m pytest -q tests/test_core.py
PYTHONPATH=. python -m tests.gates            # all families, 200 seeds each
```

## Run

```sh
docker build --platform linux/amd64 -t workbench-gym:dev .
docker run --rm -p 8000:8000 workbench-gym:dev
openenv validate --url http://localhost:8000
```

## Source

Apache License 2.0.
