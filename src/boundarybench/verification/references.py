"""Reference-manifest and checksum validation for verifier inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path, root: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def read_trusted_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ValueError(f"malformed checksum line {line_number}: {path}")
        digest, rel_path = parts
        checksums[rel_path] = digest
    return checksums


def _verify_manifest_file_hash(
    *,
    rel_path: str,
    actual_path: Path,
    expected_hash: str | None,
    errors: list[str],
) -> None:
    if expected_hash is None:
        errors.append(f"manifest missing hash for {rel_path}")
        return
    if not actual_path.is_file():
        errors.append(f"manifest referenced missing file:{rel_path}")
        return
    actual_hash = sha256_file(actual_path)
    if actual_hash != expected_hash:
        errors.append(f"manifest hash mismatch:{rel_path}")


def validate_reference_manifest(
    *,
    root: Path,
    tasks_path: Path,
    manifest_path: Path,
    trusted_checksums_path: Path | None = None,
) -> list[str]:
    """Return integrity errors for a task split manifest.

    The manifest is intentionally deterministic and unsigned. The optional
    trusted checksum file ties it back to a committed/released source snapshot.
    """

    errors: list[str] = []
    if not manifest_path.is_file():
        return [f"missing task manifest:{manifest_path}"]
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"task manifest json_parse_error:{exc.msg}"]

    if manifest.get("schema_version") != "boundarybench.task_split_manifest.v1":
        errors.append("invalid task manifest schema_version")

    expected_tasks_path = manifest.get("tasks_path")
    actual_tasks_rel = repo_relative(tasks_path, root)
    if expected_tasks_path != actual_tasks_rel:
        errors.append(f"manifest tasks_path mismatch:{expected_tasks_path}!={actual_tasks_rel}")
    _verify_manifest_file_hash(
        rel_path=actual_tasks_rel,
        actual_path=tasks_path,
        expected_hash=manifest.get("tasks_sha256"),
        errors=errors,
    )

    oracle_rel = manifest.get("oracle_results_path")
    oracle_hash = manifest.get("oracle_results_sha256")
    if isinstance(oracle_rel, str):
        oracle_path = root / oracle_rel
        if oracle_path.exists():
            _verify_manifest_file_hash(
                rel_path=oracle_rel,
                actual_path=oracle_path,
                expected_hash=oracle_hash,
                errors=errors,
            )
        elif oracle_hash is not None:
            errors.append(f"manifest referenced missing oracle_results_path:{oracle_rel}")

    if trusted_checksums_path is not None and trusted_checksums_path.is_file():
        trusted = read_trusted_checksums(trusted_checksums_path)
        for rel_path, actual_path in (
            (repo_relative(manifest_path, root), manifest_path),
            (actual_tasks_rel, tasks_path),
        ):
            expected = trusted.get(rel_path)
            if expected is None:
                errors.append(f"trusted checksum missing:{rel_path}")
            elif sha256_file(actual_path) != expected:
                errors.append(f"trusted checksum mismatch:{rel_path}")
    return errors
