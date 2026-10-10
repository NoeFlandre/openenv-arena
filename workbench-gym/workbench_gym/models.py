# SPDX-License-Identifier: Apache-2.0

"""
Actions and observations for Workbench Gym.

The action is a tool call: ``{"tool": "...", "args": {...}}``. Extra keys are
ignored, so a harmless extra key does not end an episode.
"""

from typing import Any

from openenv.core.env_server.types import Action, Observation
from pydantic import ConfigDict, Field


class WorkbenchAction(Action):
    model_config = ConfigDict(extra="ignore")

    tool: str = Field(default="", description="One of ls, read, grep, py, submit.")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments of the tool.")


class WorkbenchObservation(Observation):
    task_id: str = Field(default="", description="Task being played")
    output: str = Field(default="", description="Reset text, or the result of the last call")
    ok: bool = Field(default=True, description="False when the call was invalid")
    calls_left: int = Field(default=0, description="Tool calls left, submit included")
