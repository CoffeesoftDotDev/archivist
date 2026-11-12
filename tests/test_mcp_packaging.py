"""Offline packaging contracts; clean installation evidence lives in mcp_smoke.py."""
from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_entry_points_and_optional_sdk_metadata():
    distribution = importlib.metadata.distribution("archivist")
    scripts = {
        entry.name: entry.value
        for entry in distribution.entry_points if entry.group == "console_scripts"
    }
    assert scripts["archivist"] == "archivist.cli:main"
    assert scripts["archivist-mcp"] == "archivist.mcp:main"
    requirements = distribution.requires or []
    sdk = [requirement for requirement in requirements if requirement.lower().startswith("mcp")]
    assert len(sdk) == 1
    normalized = sdk[0].replace(" ", "").replace("'", '"')
    assert ">=1.28" in normalized and "<2" in normalized
    assert 'extra=="mcp"' in normalized


def test_ordinary_cli_never_imports_optional_sdk(tmp_path):
    # A fresh interpreter blocks even discovery of mcp, including transitive imports.
    code = """
import importlib.abc
import runpy
import sys

class NoMcp(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mcp" or fullname.startswith("mcp."):
            raise AssertionError("ordinary CLI imported the optional MCP SDK")

sys.meta_path.insert(0, NoMcp())
sys.argv = ["archivist", "--help"]
runpy.run_module("archivist", run_name="__main__")
"""
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("ARCHIVIST_")
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=environment,
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()
    assert list(tmp_path.iterdir()) == []


def test_missing_sdk_startup_reports_extra_before_loading_optional_dependencies(tmp_path):
    code = """
import importlib.abc
import runpy
import sys

class NoOptionalDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mcp":
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        if fullname in {"anyio", "jsonschema"}:
            raise AssertionError("adapter imported an SDK dependency before checking for MCP")

sys.meta_path.insert(0, NoOptionalDependencies())
sys.argv = ["archivist-mcp", "--version"]
runpy.run_module("archivist.mcp", run_name="__main__")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "install this source with [mcp]" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("stdio", [False, True])
def test_mcp_help_exposes_operator_only_policy_without_writes(tmp_path, stdio):
    pytest.importorskip("mcp")
    from dataclasses import fields

    from archivist.services.image_access import ReadLimits

    completed = subprocess.run(
        [sys.executable, "-m", "archivist.mcp", *(["--stdio"] if stdio else []), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=20, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert "--source-root" in completed.stderr
    assert "--destination-root" in completed.stderr
    assert "--stdio" in completed.stderr
    for field in fields(ReadLimits):
        assert "--" + field.name.replace("_", "-") in completed.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("flag", ["--source-root", "--destination-root"])
@pytest.mark.parametrize("value", ["", " ", "\t"])
def test_empty_startup_roots_fail_closed_instead_of_authorizing_cwd(tmp_path, flag, value):
    pytest.importorskip("mcp")
    completed = subprocess.run(
        [
            sys.executable, "-m", "archivist.mcp",
            "--source-root", str(tmp_path), "--destination-root", str(tmp_path),
            flag, value,
        ],
        cwd=tmp_path, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=20, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode != 0, "Empty root silently authorized the working directory"
    assert completed.stdout == ""
    assert completed.stderr
    assert list(tmp_path.iterdir()) == []


def test_smoke_rejects_mutable_git_references_without_installing():
    script = Path(__file__).resolve().parents[1] / "scripts" / "mcp_smoke.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--commit", "main"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert completed.returncode != 0
    assert "40-character" in completed.stderr


def test_smoke_import_does_not_require_sdk():
    script = Path(__file__).resolve().parents[1] / "scripts" / "mcp_smoke.py"
    code = (
        "import runpy,sys,json; "
        f"runpy.run_path({str(script)!r}, run_name='smoke_import_test'); "
        "print(json.dumps('mcp' in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10, check=True,
    )
    assert json.loads(completed.stdout) is False
