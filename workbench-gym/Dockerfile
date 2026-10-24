# SPDX-License-Identifier: Apache-2.0

FROM ghcr.io/noeflandre/workbench-gym@sha256:e77cf160349154c5e16f1d55da307bfa1a9c73b1f08b7fbfb51bc6162be9eab5

WORKDIR /app/env

ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision=$SOURCE_REVISION
LABEL org.opencontainers.image.version="v7"

# Keep the grader inaccessible to the nobody user used for task shell commands.
COPY workbench_gym ./workbench_gym
COPY openenv.yaml ./openenv.yaml
RUN chmod -R go-rwx /app/env && chmod 755 /app && chmod 711 /root
