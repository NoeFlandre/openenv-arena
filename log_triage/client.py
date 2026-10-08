# SPDX-License-Identifier: Apache-2.0

"""Log Triage Environment Client."""

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import LogTriageAction, LogTriageObservation


class LogTriageEnv(EnvClient[LogTriageAction, LogTriageObservation, State]):
    """
    Client for the Log Triage Environment.

    Example:
        >>> with LogTriageEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset(task_id="log-00")
        ...     print(result.observation.question)
        ...
        ...     result = client.step(LogTriageAction(grep="status=5"))
        ...     print(result.observation.output)
        ...
        ...     result = client.step(LogTriageAction(answer="billing"))
        ...     print(result.reward, result.done)
    """

    def _step_payload(self, action: LogTriageAction) -> dict:
        return action.model_dump(exclude_none=True)

    def _parse_result(self, payload: dict) -> StepResult[LogTriageObservation]:
        obs_data = payload.get("observation", {})
        observation = LogTriageObservation(
            task_id=obs_data.get("task_id", ""),
            question=obs_data.get("question", ""),
            output=obs_data.get("output", ""),
            steps_left=obs_data.get("steps_left", 0),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=payload.get("metadata", obs_data.get("metadata", {})),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
            metadata=payload.get("metadata"),
        )

    def _parse_state(self, payload: dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
