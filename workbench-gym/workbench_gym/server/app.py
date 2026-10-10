# SPDX-License-Identifier: Apache-2.0

"""
HTTP and WebSocket server for Workbench Gym.

Episodes run over WebSocket (/ws), one environment per connection.

Run locally:
    uvicorn workbench_gym.server.app:app --host 0.0.0.0 --port 8000
"""

from openenv.core.env_server.http_server import create_app

from ..models import WorkbenchAction, WorkbenchObservation
from ..server.environment import WorkbenchEnvironment

app = create_app(
    WorkbenchEnvironment,
    WorkbenchAction,
    WorkbenchObservation,
    env_name="workbench_gym",
    max_concurrent_envs=16,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server with uvicorn."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
