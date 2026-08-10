"""Run the verifier in a sterile subprocess."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


def run_verifier_isolated(
    *,
    repo_root: Path,
    tasks_path: Path,
    results_path: Path,
    grades_out: Path,
    summary_out: Path,
    enable_sheaf_diagnostic: bool = False,
    task_manifest_path: Path | None = None,
    trusted_checksums_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the PVE in a separate Python isolated-mode subprocess.

    The child process receives a minimal environment and no provider credential
    variables. The worker script inserts the repo-local ``src`` path itself,
    so it does not rely on inherited ``PYTHONPATH``.
    """

    worker = repo_root / "scripts" / "verification_worker.py"
    command = [
        sys.executable,
        "-I",
        str(worker),
        "--tasks",
        str(tasks_path),
        "--results",
        str(results_path),
        "--grades-out",
        str(grades_out),
        "--summary-out",
        str(summary_out),
    ]
    if enable_sheaf_diagnostic:
        command.append("--enable-sheaf-diagnostic")
    if task_manifest_path is not None:
        command.extend(["--task-manifest", str(task_manifest_path)])
    if trusted_checksums_path is not None:
        command.extend(["--trusted-checksums", str(trusted_checksums_path)])
    env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C",
        "LC_ALL": "C",
    }
    return subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
