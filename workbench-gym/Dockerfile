# SPDX-License-Identifier: Apache-2.0

# Reuse the published v5 runtime and its pinned server/agent packages. The v6
# source changes only the task grader and environment implementation.
#   DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build -t ghcr.io/noeflandre/workbench-gym:v6 .

FROM ghcr.io/noeflandre/workbench-gym@sha256:e77cf160349154c5e16f1d55da307bfa1a9c73b1f08b7fbfb51bc6162be9eab5

WORKDIR /app/env

# Keep the grader inaccessible to the nobody user used for task shell commands.
COPY workbench_gym ./workbench_gym
COPY openenv.yaml ./openenv.yaml
RUN chmod -R go-rwx /app/env && chmod 755 /app && chmod 711 /root
