"""Stage 10.5 empirical model-family CLI entrypoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from boundarybench.empirical.execution import (
    ALLOWED_EVIDENCE_MODES,
    EMPIRICAL_RESULT_SCHEMA_VERSION,
    GenerationConfig,
    empirical_result_record,
    missing_requirements,
    run_model_family,
    validate_explicit_commit_provenance,
    validate_smoke_task_limit_usage,
)


SUPPORTED_EVIDENCE_MODES = ALLOWED_EVIDENCE_MODES

FAMILY_SPECS: dict[str, dict[str, Any]] = {
    "open_weight_family_a": {
        "provider": "open_weight_family_a",
        "required_env": ("BOUNDARYBENCH_OPEN_WEIGHT_A_MODEL_ID", "BOUNDARYBENCH_OPEN_WEIGHT_A_MODEL_DIR"),
        "backend_env": "BOUNDARYBENCH_OPEN_WEIGHT_A_BACKEND",
        "supported_evidence_modes": ("output_only", "token_top_k", "full_category_evidence"),
        "adapter_modes": ("output_only", "token_top_k", "open_weight_full_category"),
    },
    "open_weight_family_b": {
        "provider": "open_weight_family_b",
        "required_env": ("BOUNDARYBENCH_OPEN_WEIGHT_B_MODEL_ID", "BOUNDARYBENCH_OPEN_WEIGHT_B_MODEL_DIR"),
        "backend_env": "BOUNDARYBENCH_OPEN_WEIGHT_B_BACKEND",
        "supported_evidence_modes": ("output_only", "token_top_k", "full_category_evidence"),
        "adapter_modes": ("output_only", "token_top_k", "open_weight_full_category"),
    },
    "closed_provider_a": {
        "provider": "openai_responses_api",
        "required_env": ("BOUNDARYBENCH_CLOSED_PROVIDER_A_MODEL_ID", "BOUNDARYBENCH_CLOSED_PROVIDER_A_API_KEY"),
        "supported_evidence_modes": ("output_only",),
        "adapter_modes": ("output_only",),
        "tool_policy": "no_web_search_no_file_search_no_tools_no_retrieval_no_browsing",
    },
    "closed_provider_b": {
        "provider": "anthropic_messages_api",
        "required_env": ("BOUNDARYBENCH_CLOSED_PROVIDER_B_MODEL_ID", "BOUNDARYBENCH_CLOSED_PROVIDER_B_API_KEY"),
        "supported_evidence_modes": ("output_only",),
        "adapter_modes": ("output_only",),
        "tool_policy": "no_tools_no_retrieval_no_browsing_no_external_context",
    },
}


def command_for_family(args: argparse.Namespace) -> str:
    command = (
        "PYTHONPATH=src "
        f"python3 scripts/run_empirical_model_family.py --family {args.family} "
        f"--evidence-mode {args.evidence_mode} --model-inputs {args.model_inputs} "
        f"--model-input-manifest {args.model_input_manifest} --freeze-manifest {args.freeze_manifest} "
        f"--out-dir {args.out_dir} --run-id {args.run_id}"
    )
    if args.allow_public_dev_smoke:
        command += " --allow-public-dev-smoke"
    if args.smoke_task_limit is not None:
        command += f" --smoke-task-limit {args.smoke_task_limit}"
    if args.execution_isolated_validation:
        command += " --execution-isolated-validation"
    if args.expected_freeze_manifest_sha256 is not None:
        command += f" --expected-freeze-manifest-sha256 {args.expected_freeze_manifest_sha256}"
    if args.runner_commit is not None:
        command += f" --runner-commit {args.runner_commit}"
    if args.benchmark_contract_commit is not None:
        command += f" --benchmark-contract-commit {args.benchmark_contract_commit}"
    return command


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True, choices=sorted(FAMILY_SPECS))
    parser.add_argument("--evidence-mode", required=True, choices=SUPPORTED_EVIDENCE_MODES)
    parser.add_argument("--model-inputs", type=Path, required=True)
    parser.add_argument("--model-input-manifest", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-id", default="run_001")
    parser.add_argument("--benchmark-contract-tag", default="benchmark-contract-v0.1")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--token-top-k", type=int, default=5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--mock-response-dir", type=Path, help="mock-only response directory for tests; never contacts providers")
    parser.add_argument(
        "--allow-public-dev-smoke",
        action="store_true",
        help=(
            "Permit only the canonical public_dev/model_inputs package for an explicit smoke run. "
            "Normal execution still requires heldout_eval/model_inputs."
        ),
    )
    parser.add_argument(
        "--smoke-task-limit",
        type=positive_int,
        help="Positive task limit for canonical public_dev smoke execution; requires --allow-public-dev-smoke.",
    )
    parser.add_argument(
        "--execution-isolated-validation",
        action="store_true",
        help=(
            "Validate the freeze manifest for an answer-key-free execution host: trusted artifacts must be absent, "
            "but non-trusted frozen files remain hash-checked."
        ),
    )
    parser.add_argument(
        "--expected-freeze-manifest-sha256",
        help="Required SHA256 of freeze_manifest.json when --execution-isolated-validation is set.",
    )
    parser.add_argument("--runner-commit", help="Explicit 40-hex runner commit for isolated execution provenance.")
    parser.add_argument(
        "--benchmark-contract-commit",
        help="Explicit 40-hex benchmark contract commit for isolated execution provenance.",
    )
    args = parser.parse_args(argv)

    try:
        if args.execution_isolated_validation and not args.expected_freeze_manifest_sha256:
            raise ValueError("execution_isolated_validation_requires_expected_freeze_manifest_sha256")
        args.runner_commit, args.benchmark_contract_commit = validate_explicit_commit_provenance(
            execution_isolated_validation=args.execution_isolated_validation,
            runner_commit=args.runner_commit,
            benchmark_contract_commit_value=args.benchmark_contract_commit,
        )
        validate_smoke_task_limit_usage(
            repo_root=Path.cwd(),
            model_inputs=args.model_inputs,
            model_input_manifest=args.model_input_manifest,
            allow_public_dev_smoke=args.allow_public_dev_smoke,
            smoke_task_limit=args.smoke_task_limit,
        )
    except ValueError as exc:
        print("external model run failed before completion")
        print(f"reason: {type(exc).__name__}:{exc}")
        return 1

    missing = missing_requirements(
        family=args.family,
        evidence_mode=args.evidence_mode,
        mock_response_dir=args.mock_response_dir,
    )
    if missing:
        print("external model run not executed")
        print("reason:")
        for item in missing:
            print(f"- {item}")
        print("command to execute when prerequisites are available:")
        print(command_for_family(args))
        return 2

    try:
        manifest = run_model_family(
            repo_root=Path.cwd(),
            family=args.family,
            evidence_mode=args.evidence_mode,
            model_inputs=args.model_inputs,
            model_input_manifest=args.model_input_manifest,
            freeze_manifest=args.freeze_manifest,
            out_dir=args.out_dir,
            run_id=args.run_id,
            generation_config=GenerationConfig(
                temperature=args.temperature,
                max_output_tokens=args.max_output_tokens,
                token_top_k=args.token_top_k,
                seed=args.seed,
                timeout_seconds=args.timeout_seconds,
            ),
            benchmark_contract_tag=args.benchmark_contract_tag,
            mock_response_dir=args.mock_response_dir,
            allow_public_dev_smoke=args.allow_public_dev_smoke,
            smoke_task_limit=args.smoke_task_limit,
            execution_isolated_validation=args.execution_isolated_validation,
            expected_freeze_manifest_sha256=args.expected_freeze_manifest_sha256,
            runner_commit=args.runner_commit,
            benchmark_contract_commit_value=args.benchmark_contract_commit,
            progress_stream=sys.stdout,
        )
    except Exception as exc:
        print("external model run failed before completion")
        print(f"reason: {type(exc).__name__}:{exc}")
        return 1
    print(json.dumps(manifest, sort_keys=True))
    return 0


__all__ = [
    "EMPIRICAL_RESULT_SCHEMA_VERSION",
    "FAMILY_SPECS",
    "SUPPORTED_EVIDENCE_MODES",
    "GenerationConfig",
    "empirical_result_record",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
