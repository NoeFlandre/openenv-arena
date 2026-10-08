# SPDX-License-Identifier: Apache-2.0

"""
Actions and observations for the Log Triage environment.
"""

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class LogTriageAction(Action):
    """Search the log or answer. Send exactly one of the two fields."""

    grep: str | None = Field(
        default=None,
        max_length=200,
        description="Return up to 10 log lines containing this text (case-insensitive). "
        "An empty string returns the first 10 lines.",
    )
    answer: str | None = Field(
        default=None,
        max_length=64,
        description="The service that first returned HTTP 5xx after the deploy. Ends the episode.",
    )


class LogTriageObservation(Observation):
    """What the agent sees after each action."""

    task_id: str = Field(default="", description="Task being played")
    question: str = Field(default="", description="The question. Sent once, at reset.")
    output: str = Field(default="", description="Result of the last action")
    steps_left: int = Field(default=0, description="Actions left before the episode ends")
