# SPDX-License-Identifier: Apache-2.0

"""
Action, observation and state, copied field for field from OpenEnv's tbench2_env
(pinned revision 86a180e) so that GET /schema is identical to that environment's.
"""

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class Tbench2Action(Action):
    """Action for interacting with a TB2 task session."""

    action_type: str = Field(default="exec")
    command: str = Field(default="")
    session_id: str | None = Field(default=None)
    block: bool = Field(default=True)
    wait_seconds: float | None = Field(default=None)
    file_path: str = Field(default="")
    content: str = Field(default="")


class Tbench2Observation(Observation):
    """Observation returned from the TB2 environment."""

    instruction: str = Field(default="")
    output: str = Field(default="")
    success: bool = Field(default=True)
    error: str = Field(default="")
    task_id: str = Field(default="")
    task_path: str = Field(default="")
    session_id: str | None = Field(default=None)
    action_type: str = Field(default="")
    info: dict = Field(default_factory=dict)


class Tbench2State(State):
    """Server-side state for a TB2 task."""

    task_id: str = Field(default="")
    task_path: str = Field(default="")
    session_id: str = Field(default="")
    terminal_ready: bool = Field(default=False)
    last_action_type: str = Field(default="")
    last_command: str = Field(default="")
    last_output: str = Field(default="")
