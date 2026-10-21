# SPDX-License-Identifier: Apache-2.0

"""
Shell commands for the ``exec`` action.

Each command runs through /bin/sh in the episode's working directory, which
persists across commands so the agent can create files. When the server runs
as root, the command drops to ``nobody``, so it can read its own workspace but
not the server's code, the reference solvers or any answer key (those are only
in the server's memory). Limits: CPU, memory, file size, open files, process
count, a 20 s wall clock (as tbench2_env), and the whole process group is killed
when the command ends.
"""

import os
import resource
import signal
import subprocess

WALL_TIMEOUT_S = 20
CPU_SECONDS = 10
MEMORY_BYTES = 1024 * 1024 * 1024
FILE_BYTES = 16 * 1024 * 1024
MAX_PROCESSES = 64
MAX_OUTPUT_CHARS = 4000
NOBODY_UID = 65534
NOBODY_GID = 65534


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_BYTES, FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCESSES, MAX_PROCESSES))
    if os.geteuid() == 0:
        os.setgid(NOBODY_GID)
        os.setuid(NOBODY_UID)


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def give_to_sandbox_user(path: str) -> None:
    """Make ``path`` and everything under it belong to the command user."""
    if os.geteuid() != 0:
        return
    for dirpath, dirnames, filenames in os.walk(path):
        os.chown(dirpath, NOBODY_UID, NOBODY_GID)
        for name in dirnames + filenames:
            os.chown(os.path.join(dirpath, name), NOBODY_UID, NOBODY_GID, follow_symlinks=False)


def cap_output(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[: MAX_OUTPUT_CHARS - 40] + f"\n...[output cut at {MAX_OUTPUT_CHARS} characters]"


def run_shell(command: str, workdir: str) -> tuple[int, str]:
    """Run ``command`` in ``workdir``. Returns (exit status, capped stdout and stderr)."""
    env = {
        "PATH": "/opt/agent/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": workdir,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        # One BLAS thread: numpy would otherwise start one thread per host CPU, and
        # threads count against the process limit.
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    proc = subprocess.Popen(
        ["/bin/sh", "-c", command],
        cwd=workdir,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=_limits,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=WALL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        out, _ = proc.communicate()
        text = out.decode("utf-8", errors="replace")
        return 124, cap_output(text + f"\n[command timed out after {WALL_TIMEOUT_S} s]")
    finally:
        _kill_group(proc.pid)
    text = out.decode("utf-8", errors="replace")
    if proc.returncode == -signal.SIGXCPU:
        text += f"\n[command stopped at the {CPU_SECONDS} s CPU limit]"
    return proc.returncode, cap_output(text)
