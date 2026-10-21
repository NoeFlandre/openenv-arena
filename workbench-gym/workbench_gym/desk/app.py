# SPDX-License-Identifier: Apache-2.0

"""
HTTP and WebSocket server for Workbench Desk.

Run locally:
    uvicorn workbench_gym.desk.app:app --host 0.0.0.0 --port 8000
"""

from openenv.core.env_server.http_server import create_app

from .environment import DeskEnvironment
from .models import DeskAction, DeskObservation

app = create_app(
    DeskEnvironment,
    DeskAction,
    DeskObservation,
    env_name="workbench_desk",
    max_concurrent_envs=16,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server with uvicorn."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
