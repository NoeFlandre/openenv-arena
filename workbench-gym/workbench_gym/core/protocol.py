# SPDX-License-Identifier: Apache-2.0

"""Episode protocol: limits, task ids and the text the policy sees at reset."""

import re

MAX_CALLS = 12
RESET_CHARS = 1000
QUESTION_CHARS = 500
FILES_MAX_TOTAL_CHARS = 3000
FILES_MAX_COUNT = 12
TOOLS = ("ls", "read", "grep", "py", "submit")

TOOLS_TEXT = (
    "Tools, one JSON object per reply:\n"
    '{"tool":"ls","args":{"path":""}}\n'
    '{"tool":"read","args":{"path":"f.txt","start":0,"count":12}}\n'
    '{"tool":"grep","args":{"path":"","text":"word"}}\n'
    '{"tool":"py","args":{"lines":["print(1+1)"]}}  (stdlib, on a copy of the files; '
    "in py lines use single quotes only and no backslashes)\n"
    '{"tool":"submit","args":{"answer":{...}}}  ends the episode\n'
    f"You have {MAX_CALLS} calls, submit included."
)

_TASK_RE = re.compile(r"^([a-z]{2,4}[0-9])-L([1-3])$")


def parse_task_id(task_id: str) -> tuple[str, int]:
    """Split ``sw1-L2`` into ``("sw1", 2)``. Raises ValueError for anything else."""
    match = _TASK_RE.match(task_id or "")
    if not match:
        raise ValueError(f"unknown task_id: {task_id!r}")
    return match.group(1), int(match.group(2))


def describe_kind(field) -> str:
    kind = field.kind
    if kind == "int":
        return "integer"
    if kind == "number":
        return "number"
    if kind == "text":
        return "text"
    if kind == "set":
        return "list, order does not matter"
    if kind == "fraction":
        return 'string "p/q", reduced'
    return "object"


def reset_text(task_id: str, question: str, fields: dict) -> str:
    """The first observation. Families must keep it within RESET_CHARS (the gates check)."""
    field_list = "; ".join(f"{name} ({describe_kind(spec)})" for name, spec in fields.items())
    return (
        f"TASK {task_id}. {question}\n"
        f"Answer fields: {field_list}.\n"
        f"{TOOLS_TEXT}\n"
        "Reply with exactly one JSON object on one line."
    )
