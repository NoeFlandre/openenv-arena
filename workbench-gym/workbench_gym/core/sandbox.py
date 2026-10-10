# SPDX-License-Identifier: Apache-2.0

"""
The ``py`` tool: run the agent's stdlib Python in a copy of the instance files.

The copy lives in a fresh temporary directory. The directory and its files are
owned by the server user and are read-only to the child, so the child cannot
change its inputs. When the server runs as root, the child drops to ``nobody``
first, so it cannot read the server's own files either. The grader and answer
keys never touch this directory.

Limits: CPU seconds, address space, file size, open files, wall time, and a
new session so the whole process group is killed on timeout. Network is not
blocked here. The container is the outer boundary.
"""

import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile

MAX_LINES = 20
MAX_SOURCE_CHARS = 600
MAX_OUTPUT_CHARS = 400
WALL_TIMEOUT_S = 10
CPU_SECONDS = 3
MEMORY_BYTES = 512 * 1024 * 1024
FILE_BYTES = 1024 * 1024
NOBODY_UID = 65534
NOBODY_GID = 65534


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_BYTES, FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if os.geteuid() == 0:
        os.setgid(NOBODY_GID)
        os.setuid(NOBODY_UID)


def run_python(lines: object, files: dict[str, str]) -> str:
    """Run ``lines`` joined by newlines. Returns the capped stdout and stderr."""
    if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
        return "py needs args.lines: a list of strings"
    if len(lines) > MAX_LINES or sum(len(x) for x in lines) > MAX_SOURCE_CHARS:
        return f"py source is capped at {MAX_LINES} lines and {MAX_SOURCE_CHARS} characters"
    root = tempfile.mkdtemp(prefix="wg-")
    try:
        os.chmod(root, 0o755)
        work = os.path.join(root, "work")
        os.mkdir(work)
        for name, content in files.items():
            target = os.path.join(work, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(target, 0o444)
        for dirpath, dirnames, _ in os.walk(work):
            for d in dirnames:
                os.chmod(os.path.join(dirpath, d), 0o755)
        script = os.path.join(root, "main.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.chmod(script, 0o444)
        env = {"PATH": "/usr/bin:/bin", "HOME": work, "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"}
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", script],
                cwd=work,
                env=env,
                capture_output=True,
                timeout=WALL_TIMEOUT_S,
                preexec_fn=_limits,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            return "py timed out after 10 s"
        text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
        if proc.returncode == -signal.SIGXCPU:
            text = f"py stopped at the {CPU_SECONDS} s CPU limit"
        elif proc.returncode != 0 and not text:
            text = f"py exited with status {proc.returncode}"
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[: MAX_OUTPUT_CHARS - 12] + " ...[cut]"
        return text or "(no output)"
    finally:
        shutil.rmtree(root, ignore_errors=True)
