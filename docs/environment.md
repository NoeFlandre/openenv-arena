# Environment

This page describes the environment. It covers the tasks, the actions, the observations and the reward.

## Tasks

The environment has 12 tasks. Their ids are `log-00` to `log-11`. All tasks are in the `train` split.

Each task id sets a seed. The seed makes one log. The same task id always gives the same log.

## The log

Each log has about 40 lines. Each line has a time, a service, a status and a latency. One line is a deploy. It runs at `12:20:00`.

The log has three kinds of lines:

- Normal lines with statuses such as `200`, `204`, `301`, `404` and `429`.
- Decoy lines with a 5xx status before the deploy.
- Failure lines with a 5xx status after the deploy.

## The question

The agent gets this question at reset:

> A deploy ran at 12:20:00. Which service first returned an HTTP 5xx after the deploy?

## Actions

Send one JSON object for each action. Send exactly one field.

| Action | Example | Effect |
| --- | --- | --- |
| Search | `{"grep": "status=5"}` | Returns up to 10 lines that contain the text. Case does not matter. |
| Answer | `{"answer": "billing"}` | Ends the episode. The answer does not need capital letters. |

An empty search, `{"grep": ""}`, returns the first 10 lines.

If an action has both fields, or no field, the environment does not end the episode. It counts as one step.

## Observations

Each observation has these fields:

| Field | Meaning |
| --- | --- |
| `task_id` | The task you are playing. |
| `question` | The question. The environment sends it once, at reset. |
| `output` | The result of the last action. |
| `steps_left` | The number of actions left. |
| `done` | `true` when the episode ends. |
| `reward` | The reward. It is `0.0` until the episode ends. |

## Reward

| Case | Reward | Episode ends |
| --- | --- | --- |
| Correct answer | `1.0` | Yes |
| Wrong answer | `0.0` | Yes |
| Ten steps used without an answer | `0.0` | Yes |
| Search or invalid action | `0.0` | No |

The correct answer is the service of the earliest 5xx line after `12:20:00`. The environment computes this answer from the log. It does not store the answer in the task list.

## Limits

| Limit | Value |
| --- | --- |
| Steps per episode | 10 |
| Lines per search result | 10 |
| Search text length | 200 characters |
| Answer length | 64 characters |
