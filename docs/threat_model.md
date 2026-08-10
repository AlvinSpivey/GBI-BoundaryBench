# Threat model

## Security goals

GBI BoundaryBench should preserve:

- separation between model execution and deterministic grading;
- integrity of task references, answer keys, corruption manifests, and grader code;
- fail-closed behavior for malformed or unsupported outputs;
- credential and private endpoint secrecy;
- release exclusion of uncleared third-party/confidential files.

## In-scope adversaries

- A model that tries to pass by formatting tricks, answer-key injection, fabricated evidence IDs, or unsupported confident answers.
- A runner that accidentally supplies malformed, duplicate, mismatched, or incomplete result records.
- A contributor who accidentally commits credentials, local `.env` files, bulk upstream data, or not-for-release prompt/bootstrap material.
- A model adapter that lacks logprobs or full action scores but is mistakenly treated as full-evidence.

## Out-of-scope adversaries

- A malicious user with unrestricted write access to the repository before grading.
- Compromised operating system, Python interpreter, shell, or CI runner.
- Side channels from closed-provider services.
- Clinical safety threats from real patient care use; the benchmark is not for patient care.

## Controls implemented

- Typed task/result schemas and safe parse behavior.
- Exact, schema, graph, temporal, version, and evidence graders.
- Oracle, no-op, malformed-output, answer-key-injection, evidence-spoof, and task-ID-mismatch trials.
- Process-isolated verifier runner using `python -I` and a reduced environment.
- Provider-neutral adapter contracts that do not assume token logprobs exist.
- `.env` ignore rules and placeholder-only `.env.example`.
- Release validator checks for required docs, license boundaries, checksum/SBOM files, blocked paths, archive contents, and common secret patterns.
- Verifier task manifests record task/oracle hashes, and verifier runs check those hashes plus root `SHA256SUMS` when available.
- Result-file errors invalidate aggregate scored metrics instead of allowing a passing score with warnings.
- Baseline table generation verifies metadata/report/grades hashes before deriving tables.
- Stage 10 held-out model-input packages exclude references, oracle results, reference rationales, and hidden generation seeds.
- Stage 10 freezes reference, grader, policy, task-manifest, data-manifest, and held-out model-input hashes before external model execution.
- Stage 10 provides a verifier container recipe and read-only verifier-package boundary checks so model-authored files do not write into references or grader code.

## Residual risks

- Process-level isolation remains the baseline verifier guarantee. Container availability and exact read-only mount behavior must be verified in the operator runtime before external model execution.
- Root `SHA256SUMS` is a local integrity boundary, not a cryptographic signature.
- The public-dev answer key is public and should not be used for sealed leaderboard scoring. Stage 10 held-out answer keys must remain in the trusted verifier package only.
- Synthea synthetic data does not capture all real-world data quality or workflow risks.
- Secret scanning is best-effort and does not replace review.

## Future hardening

- Containerize the scored verifier and mount task references read-only.
- Split public-dev and hidden evaluation artifacts.
- Add signed release attestations.
- Add stronger SBOM generation from the build environment when external dependencies are introduced.
- Expand adversarial trials for prompt injection, path traversal, schema confusion, and answer-key exfiltration attempts.
