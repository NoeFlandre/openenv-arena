"""Replay the public image through WebSocket tools, from inside its container."""

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import math
import re
import shlex
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from websockets.sync.client import ClientConnection, connect
from workbench_gym.desk.families import load_families

EXAMPLE_ACTIONS = [
    {"tool": "bash", "args": {"command": "ls -1"}},
    {"tool": "submit", "args": {}},
]
FINISH_ACTION = {"tool": "submit", "args": {}}
CONTROLS = ("oracle", "empty", "malformed", "wrong", "example", "finish")
OPENENV_COMMIT = "86a180ede21e044f7929b9a7783ad83aa67d83a3"
OPENENV_WHEEL_SHA256 = "6f7cd89e811f021a012ebcfd00193f44678188be414be6c7a0170fe9d91584c9"


def audit_runtime(wheel_path: Path) -> dict:
    wheel_hash = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    spec = importlib.util.find_spec("openenv")
    assert spec is not None and spec.origin is not None, "installed openenv package missing"
    installed = Path(spec.origin).parent
    with zipfile.ZipFile(wheel_path) as wheel:
        sources = [name for name in wheel.namelist() if name.startswith("openenv/")]
        sources = [name for name in sources if name.endswith(".py")]
        mismatches = [
            name
            for name in sources
            if not (installed.parent / name).is_file()
            or (installed.parent / name).read_bytes() != wheel.read(name)
        ]
    expected = {name.removeprefix("openenv/") for name in sources}
    extra = sorted(
        path.relative_to(installed).as_posix()
        for path in installed.rglob("*.py")
        if path.relative_to(installed).as_posix() not in expected
    )
    return {
        "passed": wheel_hash == OPENENV_WHEEL_SHA256
        and len(sources) == 162
        and not mismatches
        and not extra,
        "source_commit": OPENENV_COMMIT,
        "wheel_sha256": wheel_hash,
        "expected_wheel_sha256": OPENENV_WHEEL_SHA256,
        "python_files_checked": len(sources),
        "mismatched_files": mismatches,
        "unexpected_files": extra,
    }


def exchange(socket: ClientConnection, kind: str, data: dict) -> dict[str, Any]:
    socket.send(json.dumps({"type": kind, "data": data}))
    reply = json.loads(socket.recv(timeout=45))
    assert reply["type"] == "observation", reply
    result = reply["data"]
    assert not result["observation"].get("error"), result
    reward = result["reward"]
    assert isinstance(reward, (int, float)) and not isinstance(reward, bool), result
    assert math.isfinite(reward) and 0 <= reward <= 1, result
    return result


def step(socket: ClientConnection, tool: str, **args) -> dict[str, Any]:
    return exchange(socket, "step", {"tool": tool, "args": args})


def write_outputs(socket: ClientConnection, outputs: Mapping[str, str | bytes]) -> None:
    for name, content in outputs.items():
        if isinstance(content, str):
            result = step(socket, "write", path=name, content=content)
        else:
            encoded = base64.b64encode(content).decode("ascii")
            program = (
                "import base64,pathlib; "
                f"p=pathlib.Path({name!r}); p.parent.mkdir(parents=True,exist_ok=True); "
                f"p.write_bytes(base64.b64decode({encoded!r}))"
            )
            result = step(socket, "bash", command="python3 -c " + shlex.quote(program))
        assert result["done"] is False, result


def changed(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 104729
    if isinstance(value, str):
        return value + "__wrong__"
    if isinstance(value, list):
        return [changed(item) for item in value] or ["__wrong__"]
    if isinstance(value, dict):
        return {key: changed(item) for key, item in value.items()} or {"__wrong__": 1}
    return "__wrong__"


def wrong_output(name: str, content: str | bytes) -> str | bytes:
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        raw = content if isinstance(content, bytes) else content.encode()
        book = load_workbook(io.BytesIO(raw))
        for sheet in book:
            for row in sheet:
                for cell in row:
                    if cell.value is not None:
                        cell.value = changed(cell.value)
        target = io.BytesIO()
        book.save(target)
        book.close()
        return target.getvalue()
    text = content.decode() if isinstance(content, bytes) else content
    if name.endswith(".json"):
        return json.dumps(changed(json.loads(text)))
    if name.endswith(".csv"):
        rows = list(csv.reader(io.StringIO(text)))
        target = io.StringIO()
        writer = csv.writer(target)
        writer.writerow(rows[0])
        for row in rows[1:]:
            cells = []
            for cell in row:
                try:
                    cells.append(str(float(cell) + 104729))
                except ValueError:
                    cells.append(cell + "__wrong__")
            writer.writerow(cells)
        return target.getvalue()
    try:
        return str(float(text.strip()) + 104729)
    except ValueError:
        return text + "__wrong__"


def shell_probe(socket: ClientConnection) -> dict:
    program = (
        "import json,os,numpy,pandas,openpyxl; "
        "print(json.dumps({'uid':os.getuid(),"
        "'grader_readable':os.access('/app/env/workbench_gym/desk/spec.py',os.R_OK),"
        "'python_libraries':True}))"
    )
    result = step(socket, "bash", command="python3 -c " + shlex.quote(program))
    probe = json.loads(result["observation"]["output"])
    assert probe == {"uid": 65534, "grader_readable": False, "python_libraries": True}, probe
    return probe


def replay(task_id: str, family: Any, control: str) -> dict:
    with connect("ws://127.0.0.1:8000/ws", open_timeout=10, max_size=4 * 1024 * 1024) as socket:
        initial = exchange(socket, "reset", {"task_id": task_id})
        assert initial["done"] is False and initial["reward"] == 0, initial
        instruction = initial["observation"]["output"]
        match = re.search(r"/root/task-[0-9a-f]{8}", instruction)
        assert match is not None, instruction
        workspace = Path(match.group())
        probe = shell_probe(socket) if control == "oracle" else None
        if control in {"oracle", "wrong", "malformed"}:
            files = {}
            for path in workspace.rglob("*"):
                if path.is_file():
                    raw = path.read_bytes()
                    files[path.relative_to(workspace).as_posix()] = (
                        raw if path.suffix == ".xlsx" else raw.decode("utf-8")
                    )
            outputs = dict(family.solve(files, instruction))
            assert outputs, task_id
            if control == "wrong":
                outputs = {name: wrong_output(name, content) for name, content in outputs.items()}
            elif control == "malformed":
                outputs = {name: "{malformed" for name in outputs}
            write_outputs(socket, outputs)
        if control == "example":
            for action in EXAMPLE_ACTIONS:
                result = exchange(socket, "step", action)
        else:
            result = exchange(socket, "step", FINISH_ACTION)
        assert result["done"] is True, result
        reward = result["reward"]
        if control == "oracle":
            assert reward == 1, result
        elif control in {"empty", "finish"}:
            assert reward == 0, result
        elif control in {"wrong", "malformed"}:
            assert reward <= 0.2, result
        record = {"task_id": task_id, "control": control, "done": True, "reward": reward}
        if probe is not None:
            record["shell_probe"] = probe
        return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="/tmp/replay-report.json")
    parser.add_argument("--schema", default="/tmp/replay-schema.json")
    options = parser.parse_args()
    cases, failures = [], []
    report = {
        "passed": False,
        "task_count": 0,
        "case_count": 0,
        "example_actions": EXAMPLE_ACTIONS,
        "finish_action": FINISH_ACTION,
        "cases": cases,
        "failures": failures,
    }
    try:
        audit = audit_runtime(Path("/app/env/vendor/openenv-0.6.1.dev0-py3-none-any.whl"))
        report["runtime_audit"] = audit
        assert audit["passed"], audit
        print(
            f"PASS pinned OpenEnv runtime {audit['python_files_checked']} Python files", flush=True
        )
        with urlopen("http://127.0.0.1:8000/schema", timeout=10) as response:
            schema = json.load(response)
        Path(options.schema).write_text(
            json.dumps({key: schema[key] for key in ("action", "observation")}, indent=2) + "\n"
        )
        families = load_families()
        report["task_count"] = sum(len(family.levels) for family in families.values())
        for family_id, family in sorted(families.items()):
            for level in family.levels:
                task_id = f"{family_id}-L{level}"
                for control in CONTROLS:
                    try:
                        cases.append(replay(task_id, family, control))
                        print(f"PASS {task_id} {control} reward={cases[-1]['reward']}", flush=True)
                    except Exception as exc:
                        failure = {"task_id": task_id, "control": control, "error": str(exc)}
                        failures.append(failure)
                        print(f"FAIL {task_id} {control} {exc}", flush=True)
    except Exception as exc:
        failures.append({"stage": "setup", "error": str(exc)})
        print(f"FAIL setup {exc}", flush=True)
    finally:
        report["passed"] = not failures
        report["case_count"] = len(cases) + sum("task_id" in item for item in failures)
        Path(options.report).write_text(json.dumps(report, indent=2) + "\n")
    assert not failures, f"{len(failures)} replay failures"
    print(f"PASS {report['task_count']} tasks, {report['case_count']} episodes", flush=True)


if __name__ == "__main__":
    main()
