#!/usr/bin/env python3
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Block direct Codex mutations of Frappe-managed generated Python files."""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import NoReturn, cast

BEGIN_MARKER = "# begin: auto-generated types"
END_MARKER = "# end: auto-generated types"
PATH_RE = re.compile(r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:json|py)\b")
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:(?:Update|Add|Delete) File|Move to): (.+?)\s*$")


def deny(reason: str) -> NoReturn:
    """Return the Codex denial shape and exit with the documented blocking status."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    print(reason, file=sys.stderr)
    raise SystemExit(2)


def payload_from_stdin() -> dict[str, object] | None:
    """Read a Codex hook payload, failing open when the payload is not JSON object data."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def tool_input(payload: dict[str, object]) -> dict[str, object]:
    """Return the tool input object when the hook payload contains one."""
    value = payload.get("tool_input")
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def command_from_payload(payload: dict[str, object]) -> str:
    """Extract the command string used by Bash and apply_patch hooks."""
    value = tool_input(payload).get("command")
    return value if isinstance(value, str) else ""


def working_directory(payload: dict[str, object]) -> Path:
    """Resolve the hook working directory without consulting user-controlled global state."""
    value = payload.get("cwd")
    return Path(value).resolve() if isinstance(value, str) and value else Path.cwd().resolve()


def relative_path(raw_path: str, cwd: Path) -> str:
    """Normalize a command path relative to the hook working directory."""
    path = Path(raw_path.strip().strip("'\""))
    candidate = path if path.is_absolute() else cwd / path
    try:
        return candidate.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return candidate.as_posix()


def current_content(path: str, cwd: Path) -> str | None:
    """Read an existing repository file for generated-block detection."""
    file_path = cwd / path
    try:
        return file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def type_block_span(content: str) -> tuple[int, int] | None:
    """Return the first generated type-block span when it is well-formed."""
    begin = content.find(BEGIN_MARKER)
    end = content.find(END_MARKER)
    if begin == -1 or end == -1 or end < begin:
        return None
    return begin, end + len(END_MARKER)


def is_module_init(path: str) -> bool:
    """Return whether a path is a generated package initializer."""
    return Path(path).name == "__init__.py"


def apply_patch_paths(command: str) -> list[str]:
    """Extract paths from the custom apply_patch file headers."""
    paths: list[str] = []
    for line in command.splitlines():
        match = PATCH_FILE_RE.match(line)
        if match:
            paths.append(match.group(1).strip())
    return paths


def shell_paths(command: str) -> list[str]:
    """Extract likely Python/JSON path operands from a shell command."""
    paths = PATH_RE.findall(command)
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        words = []
    paths.extend(word for word in words if word.endswith((".py", ".json")))
    return list(dict.fromkeys(paths))


def shell_mutates(command: str) -> bool:
    """Recognize common shell mutation forms without trying to execute the command."""
    patterns = (
        r"\b(?:sed|perl|ruby)\b[^\n;]*\s-i(?:\s|['\"]|$)",
        r"\bpython(?:3(?:\.\d+)?)?\b[^\n;]*(?:\s-c\s|\s-<<|write_text|open\([^)]*['\"]w)",
        r"\b(?:tee|touch|truncate|install|rm|mv|cp|chmod|chown|ln|dd|shred|unlink)\b",
        r"(?:^|\s)(?:>>|>)\s*\S+",
        r"\bfind\b[^\n;]*\s-delete\b",
        r"\bgit\s+(?:apply|checkout|restore|reset|clean|rm|mv)\b",
    )
    return any(re.search(pattern, command) for pattern in patterns)


def patch_touches_type_block(command: str, path: str, cwd: Path) -> bool:
    """Detect apply_patch hunks that remove or locate content inside a generated block."""
    content = current_content(path, cwd)
    if content is None:
        return False
    span = type_block_span(content)
    if span is None:
        return False
    if BEGIN_MARKER in command or END_MARKER in command:
        return True
    begin, end = span
    patch_lines = command.splitlines()
    for line in patch_lines:
        if line.startswith(("***", "@@")):
            continue
        candidate = line[1:] if line[:1] in {"+", "-", " "} else line
        if not candidate.strip():
            continue
        offset = content.find(candidate)
        if offset >= begin and offset + len(candidate) <= end:
            return True
    return False


def guard_path(path: str, *, command: str, cwd: Path, patch: bool) -> None:
    """Deny a mutation targeting a generated artifact."""
    normalized = relative_path(path, cwd)
    if is_module_init(normalized):
        deny(f"BLOCKED: {normalized} is a Frappe-managed module-level __init__.py file.")
    if not normalized.endswith(".py"):
        return
    if patch and patch_touches_type_block(command, normalized, cwd):
        deny(f"BLOCKED: this patch touches the auto-generated types block in {normalized}.")
    content = current_content(normalized, cwd)
    if not patch and content is not None and type_block_span(content) is not None:
        deny(f"BLOCKED: this shell mutation targets generated types in {normalized}.")


def main() -> None:
    """Guard Bash and apply_patch calls before Codex executes them."""
    payload = payload_from_stdin()
    if payload is None:
        return
    name = payload.get("tool_name")
    if name not in {"Bash", "apply_patch"}:
        return
    command = command_from_payload(payload)
    if not command:
        return
    cwd = working_directory(payload)
    is_patch = name == "apply_patch"
    if is_patch:
        for path in apply_patch_paths(command):
            guard_path(path, command=command, cwd=cwd, patch=True)
        return
    if not shell_mutates(command):
        return
    for path in shell_paths(command):
        guard_path(path, command=command, cwd=cwd, patch=False)


if __name__ == "__main__":
    main()
