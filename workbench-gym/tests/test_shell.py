# SPDX-License-Identifier: Apache-2.0

import os
import shlex
import signal
import sys
import time
import tracemalloc

import pytest
from workbench_gym.desk import shell


@pytest.fixture(autouse=True)
def use_supported_limits(monkeypatch):
    if sys.platform == "darwin":
        monkeypatch.setattr(shell, "_limits", lambda: None)


def test_shell_keeps_exit_status_and_combines_output(tmp_path):
    code, output = shell.run_shell("printf 'one\\n'; printf 'two\\n' >&2; exit 7", str(tmp_path))
    assert code == 7
    assert output == "one\ntwo\n"


def test_shell_does_not_forward_server_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_PRIVATE_MARKER", "server-only")
    code, output = shell.run_shell('printf "%s" "${ARENA_PRIVATE_MARKER-unset}"', str(tmp_path))
    assert code == 0
    assert output == "unset"


def test_shell_capture_memory_stays_bounded_for_large_output(tmp_path):
    tracemalloc.start()
    try:
        code, output = shell.run_shell("head -c 8388608 /dev/zero | tr '\\000' x", str(tmp_path))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert code == 0
    assert output.startswith("x" * 100)
    assert "output cut at 2000 characters" in output
    assert len(output) <= shell.MAX_OUTPUT_CHARS
    assert peak < 1024 * 1024


def test_shell_timeout_does_not_wait_for_detached_stdout_holder(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "WALL_TIMEOUT_S", 0.2)
    child = (
        "import os,time; os.setsid(); "
        "open('detached.pid','w').write(str(os.getpid())); time.sleep(3)"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(child)} & wait"
    started = time.monotonic()
    try:
        code, output = shell.run_shell(command, str(tmp_path))
        elapsed = time.monotonic() - started
        assert code == 124
        assert "command timed out" in output
        assert elapsed < 1.0
    finally:
        pid_file = tmp_path / "detached.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
