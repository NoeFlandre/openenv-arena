# SPDX-License-Identifier: Apache-2.0

# Builds the Workbench Gym OpenEnv server (Terminal Workbench: the tbench2_env
# interface over the Workbench task families). The arena runs linux/amd64 only.
#   DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t ghcr.io/noeflandre/workbench-gym:v4 .

FROM python:3.12-slim

WORKDIR /app/env

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/env

# Small shell tools the tasks invite (python3, awk, grep and sed are already there).
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so this layer stays cached while the code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# OpenEnv at the arena's pinned revision (86a180e), vendored as a wheel.
COPY vendor ./vendor
RUN pip install --no-cache-dir --no-deps ./vendor/openenv-0.6.1.dev0-py3-none-any.whl

COPY workbench_gym ./workbench_gym
COPY openenv.yaml ./

# The server runs as root. Agent commands run as nobody, so they cannot read the
# family code, the reference solvers or the grader. Episode workspaces are
# created under /app, which stays traversable.
RUN chmod -R go-rwx /app/env && chmod 755 /app
ENV WG_WORK_ROOT=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "workbench_gym.terminal.app:app", "--host", "0.0.0.0", "--port", "8000"]
