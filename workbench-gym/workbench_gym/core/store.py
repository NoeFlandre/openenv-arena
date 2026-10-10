# SPDX-License-Identifier: Apache-2.0

"""
Read-only view of an instance's files, served from memory.

Paths are keys of the instance dict. Absolute paths, ``..`` and unknown names
return "no such file", so the policy cannot reach anything outside the dict.
Every output is capped so one call cannot fill the context.
"""

MAX_READ_LINES = 12
MAX_READ_CHARS = 400
MAX_GREP_HITS = 5
MAX_GREP_CHARS = 80
MAX_LS_CHARS = 400


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 12] + " ...[cut]"


class Store:
    def __init__(self, files: dict[str, str]):
        self._files = dict(files)

    @staticmethod
    def _clean(path: object) -> str | None:
        if not isinstance(path, str):
            return None
        if path.startswith("/") or "\\" in path:
            return None
        if any(part in ("..", ".") for part in path.split("/") if part != ""):
            return None
        return path.strip("/")

    def _is_dir(self, path: str) -> bool:
        prefix = path + "/" if path else ""
        return path == "" or any(name.startswith(prefix) for name in self._files)

    def ls(self, path: object) -> tuple[bool, str]:
        clean = self._clean(path if path is not None else "")
        if clean is None or not self._is_dir(clean):
            return False, "no such directory"
        prefix = clean + "/" if clean else ""
        entries: set[str] = set()
        for name in self._files:
            if not name.startswith(prefix):
                continue
            head = name[len(prefix):].split("/", 1)[0]
            if "/" in name[len(prefix):]:
                entries.add(head + "/")
            else:
                entries.add(f"{head} ({len(self._files[name])} chars)")
        return True, _cut("\n".join(sorted(entries)) or "(empty)", MAX_LS_CHARS)

    def read(self, path: object, start: object, count: object) -> tuple[bool, str]:
        clean = self._clean(path)
        if clean is None or clean not in self._files:
            return False, "no such file"
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            return False, "start must be a non-negative integer"
        n = 1 if not isinstance(count, int) or isinstance(count, bool) else count
        n = min(max(n, 1), MAX_READ_LINES)
        lines = self._files[clean].split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        if start >= len(lines):
            return True, f"end of file ({len(lines)} lines)"
        chunk = lines[start : start + n]
        body = "\n".join(f"{start + i + 1}: {line}" for i, line in enumerate(chunk))
        if start + n < len(lines):
            body += f"\n(next start {start + n} of {len(lines)} lines)"
        return True, _cut(body, MAX_READ_CHARS)

    def grep(self, path: object, text: object) -> tuple[bool, str]:
        clean = self._clean(path if path is not None else "")
        if clean is None or not (clean in self._files or self._is_dir(clean)):
            return False, "no such file or directory"
        if not isinstance(text, str) or text == "":
            return False, "text must be a non-empty string"
        prefix = clean + "/" if clean else ""
        hits: list[str] = []
        total = 0
        for name in sorted(self._files):
            if name != clean and not name.startswith(prefix):
                continue
            for i, line in enumerate(self._files[name].split("\n"), start=1):
                if text in line:
                    total += 1
                    if len(hits) < MAX_GREP_HITS:
                        hits.append(f"{name}:{i}: {line[:MAX_GREP_CHARS]}")
        if not hits:
            return True, "no match"
        out = "\n".join(hits)
        if total > MAX_GREP_HITS:
            out += f"\n({total} matches, first {MAX_GREP_HITS} shown)"
        return True, _cut(out, MAX_READ_CHARS + MAX_GREP_CHARS)
