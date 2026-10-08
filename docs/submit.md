# Submit

This page describes the submission to the arena. Read all of it before you submit.

## Rules

- One account can have one accepted submission every 24 hours.
- An accepted submission starts training. You cannot stop it from this page.
- The submission must name a public image and a public dataset.
- The arena pins the image digest when you submit. A new image needs a new `submission_id`.

## Before you submit

Check each item:

- [ ] `uv run pytest` passes.
- [ ] `uv run openenv validate --url` passes against the public image.
- [ ] The image is public. You can pull it without a login.
- [ ] The dataset `noeflandre/log-triage` is public. Access requests are off.
- [ ] The schema in `submission/submission.json` matches `GET /schema`.
- [ ] Every example episode ends with `done` set to `true`.

## The submission file

The draft is in `submission/submission.json`. It has these main fields:

| Field | Meaning |
| --- | --- |
| `submission_id` | A unique id. Change it for every new image. |
| `image` | The public image reference with its tag. |
| `schema` | The `action` and `observation` from `GET /schema`. |
| `tasks` | The 12 task ids. Each task has its time limits. |
| `example_actions` | Actions that end an episode with a reward from 0 to 1. |
| `finish_action` | The action the arena sends when an episode does not end. |
| `dataset` | The public Hugging Face dataset. |
| `source` | The public source repository. |

## Send the request

Do not send the request before the owner approves it.

Set the token in the `HF_TOKEN` environment variable. Do not write the token in a file or in a command.

```sh
BASE=https://openenvarena-arena.hf.space/api/openenv
printf 'Authorization: Bearer %s\n' "$HF_TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' --data @submission/submission.json "$BASE/submissions"
```

The answer is `202` with `state` set to `validating`. If the answer is an error, read its `code`. An error that the arena refuses at once does not use your daily slot.

## Check the status

```sh
printf 'Authorization: Bearer %s\n' "$HF_TOKEN" | curl -sS -H @- "$BASE/submissions/log-triage-v1"
```

Wait until `state` is `validated` or `rejected`. If it is `rejected`, read `report.errors`.

## After admission

The arena starts the run when a GPU is free. Read the run status here:

```sh
printf 'Authorization: Bearer %s\n' "$HF_TOKEN" | curl -sS -H @- "$BASE/runs/RUN_ID"
```

Replace `RUN_ID` with the `run.run_id` from the submission status.
