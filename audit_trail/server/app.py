# SPDX-License-Identifier: Apache-2.0

"""
HTTP and WebSocket server for the Audit Trail environment.

Endpoints (from OpenEnv):
    - POST /reset: start an episode. Body: {"task_id": "auth-00"}
    - POST /step: send an action. Body: {"action": {"grep": "..."}} or {"action": {"answer": "..."}}
    - GET /state: current episode state
    - GET /schema: action and observation schemas
    - GET /health: readiness check
    - WS /ws: one persistent session

Run locally:
    uvicorn audit_trail.server.app:app --host 0.0.0.0 --port 8000
"""

from openenv.core.env_server.http_server import create_app

from ..models import AuditTrailAction, AuditTrailObservation
from .audit_trail_environment import AuditTrailEnvironment

app = create_app(
    AuditTrailEnvironment,
    AuditTrailAction,
    AuditTrailObservation,
    env_name="audit_trail",
    max_concurrent_envs=1,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server with uvicorn. Used by the `server` command."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
