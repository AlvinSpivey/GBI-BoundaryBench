"""Stage 10 freeze-manifest validation."""

from __future__ import annotations

import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from boundarybench.verification.references import sha256_file


FREEZE_SCHEMA_VERSION = "boundarybench.stage10_freeze_manifest.v1"
FREEZE_VALIDATION_FULL = "full"
FREEZE_VALIDATION_EXECUTION_ISOLATED = "execution_isolated"
FREEZE_VALIDATION_MODES = (FREEZE_VALIDATION_FULL, FREEZE_VALIDATION_EXECUTION_ISOLATED)
TRUSTED_ARTIFACT_ROOTS = (
    "data/empirical/v0_1/trusted_verifier_package",
    "data/empirical/v0_1/heldout_eval/trusted",
    "data/empirical/v0_1/public_dev/trusted",
)


def load_freeze_manifest(path: Path) -> dict[str, Any]:
    """Load a Stage 10 freeze manifest."""

    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_manifest_rel_path(repo_root: Path, rel_path: str) -> tuple[str | None, Path | None, str | None]:
    pure = PurePosixPath(rel_path)
    if pure.is_absolute():
        return None, None, f"absolute_frozen_path:{rel_path}"
    if any(part == ".." for part in pure.parts):
        return None, None, f"path_traversal_frozen_path:{rel_path}"
    if not pure.parts:
        return None, None, f"empty_frozen_path:{rel_path}"
    normalized = PurePosixPath(*pure.parts).as_posix()
    repo_real = repo_root.resolve()
    candidate = repo_root.joinpath(*pure.parts)
    resolved = candidate.resolve(strict=False)
    if resolved != repo_real and not resolved.is_relative_to(repo_real):
        return None, None, f"path_resolution_escape:{rel_path}"
    return normalized, candidate, None


def _is_under_trusted_artifact_root(normalized_rel_path: str) -> bool:
    pure = PurePosixPath(normalized_rel_path)
    for root in TRUSTED_ARTIFACT_ROOTS:
        root_pure = PurePosixPath(root)
        if pure == root_pure or pure.is_relative_to(root_pure):
            return True
    return False


def _trusted_artifact_root_errors(repo_root: Path) -> list[str]:
    errors: list[str] = []
    repo_real = repo_root.resolve()
    for root in TRUSTED_ARTIFACT_ROOTS:
        root_path = repo_root.joinpath(*PurePosixPath(root).parts)
        resolved_root = root_path.resolve(strict=False)
        if resolved_root != repo_real and not resolved_root.is_relative_to(repo_real):
            errors.append(f"execution_isolation_symlink_escape:{root}")
            continue
        if not root_path.exists():
            continue
        if root_path.is_file() or root_path.is_symlink():
            errors.append(f"execution_isolation_violation:{root}")
            continue
        for path in root_path.rglob("*"):
            if path.is_file() or path.is_symlink():
                try:
                    rel = path.resolve(strict=False).relative_to(repo_real).as_posix()
                except ValueError:
                    rel = path.as_posix()
                errors.append(f"execution_isolation_violation:{rel}")
    return errors


def validate_freeze_manifest(
    *,
    repo_root: Path,
    freeze_manifest_path: Path,
    validation_mode: str = FREEZE_VALIDATION_FULL,
    expected_freeze_manifest_sha256: str | None = None,
) -> list[str]:
    """Return deterministic integrity errors for a Stage 10 freeze manifest."""

    errors: list[str] = []
    if validation_mode not in FREEZE_VALIDATION_MODES:
        errors.append(f"invalid_freeze_validation_mode:{validation_mode}")
    if not freeze_manifest_path.is_file():
        return [f"missing_freeze_manifest:{freeze_manifest_path}"]
    freeze_manifest_sha256 = sha256_file(freeze_manifest_path)
    if validation_mode == FREEZE_VALIDATION_EXECUTION_ISOLATED:
        if not expected_freeze_manifest_sha256:
            errors.append("execution_isolated_validation_requires_expected_freeze_manifest_sha256")
        elif freeze_manifest_sha256 != expected_freeze_manifest_sha256:
            errors.append(
                "freeze_manifest_sha256_mismatch:"
                f"expected={expected_freeze_manifest_sha256}:actual={freeze_manifest_sha256}"
            )
        errors.extend(_trusted_artifact_root_errors(repo_root))
    try:
        manifest = load_freeze_manifest(freeze_manifest_path)
    except json.JSONDecodeError as exc:
        errors.append(f"freeze_manifest_json_parse_error:{exc.msg}")
        return errors

    if manifest.get("schema_version") != FREEZE_SCHEMA_VERSION:
        errors.append(f"invalid_schema_version:{manifest.get('schema_version')}")
    if manifest.get("external_model_runs_status") != "NOT_RUN":
        errors.append("external_model_runs_status_must_be_NOT_RUN_before_execution")
    if manifest.get("reference_hashes_frozen_before_model_runs") is not True:
        errors.append("reference_hashes_not_marked_frozen_before_model_runs")

    for section_name in ("reference_file_hashes", "heldout_model_input_hashes", "grader_file_hashes"):
        section = manifest.get(section_name)
        if not isinstance(section, dict) or not section:
            errors.append(f"missing_or_empty_hash_section:{section_name}")
            continue
        for rel_path, expected_hash in sorted(section.items()):
            if not isinstance(rel_path, str) or not isinstance(expected_hash, str):
                errors.append(f"invalid_hash_entry:{section_name}")
                continue
            normalized_rel_path, file_path, path_error = _normalize_manifest_rel_path(repo_root, rel_path)
            if path_error:
                errors.append(path_error)
                continue
            assert normalized_rel_path is not None
            assert file_path is not None
            is_trusted_artifact = _is_under_trusted_artifact_root(normalized_rel_path)
            if validation_mode == FREEZE_VALIDATION_EXECUTION_ISOLATED and is_trusted_artifact and file_path.exists():
                errors.append(f"execution_isolation_violation:{normalized_rel_path}")
                continue
            if not file_path.is_file():
                if validation_mode == FREEZE_VALIDATION_EXECUTION_ISOLATED and is_trusted_artifact:
                    continue
                errors.append(f"missing_frozen_file:{normalized_rel_path}")
                continue
            actual_hash = sha256_file(file_path)
            if actual_hash != expected_hash:
                errors.append(f"frozen_hash_mismatch:{normalized_rel_path}")
    return errors


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-manifest", type=Path, default=Path("data/empirical/v0_1/freeze_manifest.json"))
    args = parser.parse_args(argv)
    errors = validate_freeze_manifest(repo_root=Path.cwd(), freeze_manifest_path=args.freeze_manifest)
    if errors:
        print("freeze validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("freeze validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
