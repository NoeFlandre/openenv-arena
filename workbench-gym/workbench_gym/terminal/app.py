# SPDX-License-Identifier: Apache-2.0

"""
HTTP and WebSocket server for Terminal Workbench (tbench2_env interface).

Run locally:
    uvicorn workbench_gym.terminal.app:app --host 0.0.0.0 --port 8000
"""

from openenv.core.env_server.http_server import create_app

from .environment import TerminalWorkbenchEnvironment
from .models import Tbench2Action, Tbench2Observation

app = create_app(
    TerminalWorkbenchEnvironment,
    Tbench2Action,
    Tbench2Observation,
    env_name="workbench_gym_terminal",
    max_concurrent_envs=16,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server with uvicorn."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
