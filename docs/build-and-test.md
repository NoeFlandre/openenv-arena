# Build and test

This page shows how to set up the project. It shows how to run the checks, build the image and validate the server.

## Requirements

- [uv](https://docs.astral.sh/uv/).
- Python 3.10 or later. The project uses Python 3.13 by default.
- Docker. Use Docker with `linux/amd64` support.

## Install the dependencies

Run this command at the repository root:

```sh
uv sync
```

The command creates `.venv/`. It installs OpenEnv from `vendor/`. This wheel is built from the arena's pinned revision.

## Run the checks

Run each check in this order:

```sh
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

- `ruff` checks the style and common errors.
- `ty` checks the types.
- `pytest` runs the unit tests.

## Build the docs

```sh
uv run mkdocs build --strict
```

To read the docs in a browser, run:

```sh
uv run mkdocs serve
```

## Build the image

Build for `linux/amd64`. The arena runs only this platform.

```sh
docker build --platform linux/amd64 -t ghcr.io/noeflandre/log-triage:v1 .
```

## Run and validate the server

1. Start the container:

   ```sh
   docker run --rm -d --name log-triage -p 8000:8000 ghcr.io/noeflandre/log-triage:v1
   ```

2. Check the health endpoint:

   ```sh
   curl -s http://localhost:8000/health
   ```

3. Validate the server:

   ```sh
   uv run openenv validate --url http://localhost:8000
   ```

4. Read the schema. Copy the `action` and `observation` parts into the submission:

   ```sh
   curl -s http://localhost:8000/schema
   ```

5. Play one episode. Every episode must end with `done` set to `true`:

   ```sh
   curl -s -X POST http://localhost:8000/reset -H 'Content-Type: application/json' -d '{"task_id": "log-00"}'
   curl -s -X POST http://localhost:8000/step -H 'Content-Type: application/json' -d '{"action": {"grep": "status=5"}}'
   curl -s -X POST http://localhost:8000/step -H 'Content-Type: application/json' -d '{"action": {"answer": "unknown"}}'
   ```

6. Stop the container:

   ```sh
   docker stop log-triage
   ```

The server keeps one episode at a time. Each `/reset` starts a new episode.
