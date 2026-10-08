# Contributing

Thank you for your help. This page explains how to change the code and the docs.

## Set up

```sh
uv sync
```

## Check your change

Run all checks before you open a pull request:

```sh
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv run mkdocs build --strict
```

Fix each failure. Do not skip a check.

## Change the environment

- Keep actions, observations and rewards in the `[0.0, 1.0]` range.
- Keep the answer computed from the log. Do not store it as a constant.
- Add a test for each new rule.
- Do not change the task seeds without a new version. A changed seed changes the training data.
- Update `docs/environment.md` when a rule changes.

## Write the docs

The docs use the ASD-STE100 Simplified Technical English rules. Follow these rules:

- Write one instruction in one sentence.
- Use the imperative for steps. Example: "Run the command."
- Keep each sentence to 20 words or fewer.
- Use active voice and present tense.
- Use one word for one meaning. Do not use synonyms for the same thing.
- Use simple verbs such as "use", "make", "check" and "send".
- Do not use idioms, slang or contractions.
- Use "must" for a requirement. Use "should" for advice. Use "do not" for a prohibition.
- Put each step in a numbered list.

## Commit and pull request

- Write the subject line in the imperative. Example: "Add grep limit test".
- Keep one topic in each pull request.
- Describe the change and the checks you ran.

## Licence

By you contributing, your change is released under the Apache License 2.0. See [LICENSE](LICENSE).
