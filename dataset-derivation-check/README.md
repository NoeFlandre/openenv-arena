---
license: apache-2.0
language:
  - en
pretty_name: Derivation Check tasks
tags:
  - openenv
  - math
  - media
  - reinforcement-learning
size_categories:
  - n<1K
---

# Derivation Check tasks

This dataset lists the tasks of the Derivation Check OpenEnv environment. The environment code is in the [GitHub repository](https://github.com/NoeFlandre/openenv-arena).

## What the environment teaches

The agent gets one log and a question. The log has one line per step. The agent searches it with `grep`, checks the lines, and gives one answer. Two families:

| Family | Domain | Question | Answer |
| --- | --- | --- | --- |
| `math` | Math and formal reasoning | Which step is the first wrong equation? | The step number, for example `07`. |
| `caption` | Media and content production | Which caption is the first one over the 90-character limit? | The caption number, for example `07`. |

Each task has a level from 0 to 7. Levels 0 to 2 are easy, 3 to 5 medium and 6 to 7 hard. Harder levels have longer logs, more wrong equations, or captions close to the limit.

## Files

| File | Contents |
| --- | --- |
| `tasks.jsonl` | One task for each line: `task_id`, `split`, `family`, `level` and the `seed`. |

The dataset does not contain the logs. The server builds each log from its seed, so the same seed always gives the same log and answer.

## Reward

- `1.0`: the answer is correct.
- `0.0`: the answer is wrong, or the agent uses all 10 steps.

## Splits

All 16 tasks are in the `train` split.

## Limits

- The logs are synthetic.
- A grep returns at most 10 matching lines.
- Each episode has 10 steps.

## License

Apache License 2.0.
