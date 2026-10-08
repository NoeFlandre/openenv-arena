# Log Triage

Log Triage is an [OpenEnv](https://github.com/meta-pytorch/OpenEnv) environment. It trains an agent to find the cause of a failure in a service log.

Each episode gives the agent one question. The agent searches the log with `grep`. Then the agent gives one answer. The reward is `1.0` for a correct answer and `0.0` for a wrong answer.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.10 or later, and Docker.

1. Install the dependencies:

   ```sh
   uv sync
   ```

2. Run the checks:

   ```sh
   uv run ruff format --check .
   uv run ruff check .
   uv run ty check
   uv run pytest
   ```

3. Build the image for the arena (`linux/amd64`):

   ```sh
   docker build --platform linux/amd64 -t ghcr.io/noeflandre/log-triage:v1 .
   ```

4. Run the image and validate it:

   ```sh
   docker run --rm -d --name log-triage -p 8000:8000 ghcr.io/noeflandre/log-triage:v1
   uv run openenv validate --url http://localhost:8000
   docker stop log-triage
   ```

## Documentation

The documentation is in [`docs/`](docs/). It uses the ASD-STE100 writing rules. Read it locally:

```sh
uv run mkdocs serve
```

## Repository layout

| Path | Contents |
| --- | --- |
| `log_triage/` | Environment code: models, client and server |
| `tests/` | Unit tests |
| `docs/` | Documentation (MkDocs) |
| `dataset/` | Task list and dataset card for Hugging Face |
| `submission/` | Draft submission request |
| `vendor/` | OpenEnv wheel at the arena's pinned revision |
| `Dockerfile` | Image build for the arena |

## License

Apache License 2.0. See [LICENSE](LICENSE).
