# SPDX-License-Identifier: Apache-2.0

"""
Action and observation for Workbench Desk.

The action is one tool call, ``{"tool": "...", "args": {...}}``. Extra keys are
ignored, so a harmless extra key does not end an episode.
"""

from typing import Any

from openenv.core.env_server.types import Action, Observation
from pydantic import ConfigDict, Field


class DeskAction(Action):
    """One tool call: bash runs a shell command, write writes a file, submit grades and ends."""

    model_config = ConfigDict(extra="ignore")

    tool: str = Field(default="", description="One of: bash, write, submit.")
    args: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            'bash: {"command": "..."}. write: {"path": "...", "content": "..."}. submit: {}.'
        ),
    )


class DeskObservation(Observation):
    """The task text after reset, then the result of each tool call."""

    output: str = Field(default="", description="Task text, or the output of the last call")
    error: str = Field(default="", description="Why the last call failed, empty when it worked")
    calls_left: int = Field(default=0, description="Tool calls left, submit included")
