#!/usr/bin/env python3
# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Regression tests for the Codex generated-file PreToolUse hook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generated_file_guard.py"
ALLOW = 0
BLOCK = 2
BLOCK_PY = (
    "class Example:\n"
    "    # begin: auto-generated types\n"
    "    name: str\n"
    "    # end: auto-generated types\n\n"
    "    def value(self) -> int:\n"
    "        return 1\n"
)


def run_hook(command: str, cwd: Path, *, tool_name: str = "Bash", raw: str | None = None) -> int:
    """Invoke the hook and return its exit code."""
    payload = {"cwd": str(cwd), "tool_name": tool_name, "tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        env=dict(os.environ),
        check=False,
    )
    return result.returncode


class GeneratedFileGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.cwd = Path(self._temporary_directory.name)
        self.addCleanup(self._temporary_directory.cleanup)

    def write(self, name: str, content: str) -> None:
        path = self.cwd / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_allows_non_mutating_shell_read(self) -> None:
        self.write("generated.py", BLOCK_PY)
        self.assertEqual(run_hook("sed -n '1,4p' generated.py", self.cwd), ALLOW)

    def test_allows_app_owned_doctype_json_mutation(self) -> None:
        self.write("connect_diagnostics_core/doctype/example/example.json", "{}\n")
        command = "sed -i 's/{}/{} /' connect_diagnostics_core/doctype/example/example.json"
        self.assertEqual(run_hook(command, self.cwd), ALLOW)

    def test_allows_patch_outside_generated_types(self) -> None:
        self.write("generated.py", BLOCK_PY)
        patch = (
            "*** Begin Patch\n*** Update File: generated.py\n@@\n"
            "-        return 1\n+        return 2\n*** End Patch\n"
        )
        self.assertEqual(run_hook(patch, self.cwd, tool_name="apply_patch"), ALLOW)

    def test_denies_patch_inside_generated_types(self) -> None:
        self.write("generated.py", BLOCK_PY)
        patch = (
            "*** Begin Patch\n*** Update File: generated.py\n@@\n"
            "-    name: str\n+    name: int\n*** End Patch\n"
        )
        self.assertEqual(run_hook(patch, self.cwd, tool_name="apply_patch"), BLOCK)

    def test_denies_patch_to_module_initializer(self) -> None:
        self.write("package/__init__.py", "\n")
        patch = "*** Begin Patch\n*** Update File: package/__init__.py\n@@\n+value = 1\n*** End Patch\n"
        self.assertEqual(run_hook(patch, self.cwd, tool_name="apply_patch"), BLOCK)

    def test_denies_sed_in_place_on_generated_types(self) -> None:
        self.write("generated.py", BLOCK_PY)
        self.assertEqual(run_hook("sed -i 's/name: str/name: int/' generated.py", self.cwd), BLOCK)

    def test_denies_python_write_to_generated_types(self) -> None:
        self.write("generated.py", BLOCK_PY)
        command = "python3 -c \"from pathlib import Path; Path('generated.py').write_text('x')\""
        self.assertEqual(run_hook(command, self.cwd), BLOCK)

    def test_denies_shell_mutation_of_module_initializer(self) -> None:
        self.write("package/__init__.py", "\n")
        self.assertEqual(run_hook("rm package/__init__.py", self.cwd), BLOCK)

    def test_allows_malformed_payload(self) -> None:
        self.assertEqual(run_hook("", self.cwd, raw="not json"), ALLOW)


if __name__ == "__main__":
    unittest.main()
