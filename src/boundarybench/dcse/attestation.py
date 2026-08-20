"""Attestation verification, Appendix B.1 Systems Validation item 1.

    "Deploy the system in a staging environment and inject invalid, expired, or
    modified remote attestation claims. Verify that invalid or stale attestation
    causes the governed write path to fail closed. Key revocation should be tested
    only in deployments whose key-management design actually uses
    attestation-bound database keys."

What is implemented: a quote format, a verifier with a declared check order, and
the six injection classes. What is *not* implemented, and must not be read as
implemented: a hardware root of trust. There is no SGX enclave here, no real
MRENCLAVE, and no IAS/DCAP round trip. The quote is signed by a software key
standing in for a platform attestation key.

That limit is why the Table 3 "Attestation Bootstrapping Time <= 2.5 s" figure is
reported as a proxy covering the *verification* path only. The dominant term in a
real deployment is quote generation plus the attestation-service round trip, and
neither is measured here. The manuscript's own conditional on key revocation is
honoured: revocation is tested as a verifier behaviour, and no claim is made about
attestation-bound database keys.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import time
from typing import Any, Sequence

from boundarybench.dcse.crypto import Identity, derive_identity, digest, verify

ATTESTATION_VERSION = "dcse-attestation-v3.0"

# Declared check order. Order is part of the contract: a verifier that checked
# freshness before signature would leak information about unsigned quotes.
CHECK_ORDER = (
    "signature_valid",
    "nonce_matches_challenge",
    "quote_not_expired",
    "measurement_in_allowlist",
    "signer_not_revoked",
    "tcb_version_at_or_above_minimum",
)

MAX_QUOTE_AGE_SECONDS = 300.0
MIN_TCB_VERSION = 5


@dataclass(frozen=True)
class AttestationQuote:
    enclave_measurement: str
    signer_measurement: str
    nonce: str
    issued_at: float
    tcb_version: int
    platform_key_id: str
    public_key_hex: str
    signature: str

    def signing_body(self) -> dict[str, Any]:
        return {
            "enclave_measurement": self.enclave_measurement,
            "signer_measurement": self.signer_measurement,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "tcb_version": self.tcb_version,
            "platform_key_id": self.platform_key_id,
        }


@dataclass(frozen=True)
class AttestationPolicy:
    measurement_allowlist: frozenset[str]
    revoked_key_ids: frozenset[str]
    max_age_seconds: float = MAX_QUOTE_AGE_SECONDS
    min_tcb_version: int = MIN_TCB_VERSION


def issue_quote(
    platform: Identity,
    *,
    enclave_measurement: str,
    nonce: str,
    now: float,
    tcb_version: int = MIN_TCB_VERSION,
    key_id: str = "platform-key-1",
) -> AttestationQuote:
    body = {
        "enclave_measurement": enclave_measurement,
        "signer_measurement": digest({"signer": "light-imaging-signing-authority"}),
        "nonce": nonce,
        "issued_at": now,
        "tcb_version": tcb_version,
        "platform_key_id": key_id,
    }
    quote = AttestationQuote(
        enclave_measurement=body["enclave_measurement"],
        signer_measurement=body["signer_measurement"],
        nonce=nonce,
        issued_at=now,
        tcb_version=tcb_version,
        platform_key_id=key_id,
        public_key_hex=platform.public_key_hex,
        signature="",
    )
    return replace(quote, signature=platform.sign(quote.signing_body()))


def verify_quote(
    quote: AttestationQuote,
    *,
    policy: AttestationPolicy,
    challenge_nonce: str,
    now: float,
) -> dict[str, Any]:
    """Evaluate the declared checks in order, stopping at the first failure."""

    failures: list[str] = []
    checks: dict[str, bool] = {}

    def run(name: str, ok: bool) -> bool:
        checks[name] = ok
        if not ok:
            failures.append(name)
        return ok

    if not run("signature_valid", verify(quote.public_key_hex, quote.signing_body(), quote.signature)):
        return _verdict(checks, failures)
    if not run("nonce_matches_challenge", quote.nonce == challenge_nonce):
        return _verdict(checks, failures)
    age = now - quote.issued_at
    if not run("quote_not_expired", 0.0 <= age <= policy.max_age_seconds):
        return _verdict(checks, failures)
    if not run("measurement_in_allowlist", quote.enclave_measurement in policy.measurement_allowlist):
        return _verdict(checks, failures)
    if not run("signer_not_revoked", quote.platform_key_id not in policy.revoked_key_ids):
        return _verdict(checks, failures)
    run("tcb_version_at_or_above_minimum", quote.tcb_version >= policy.min_tcb_version)
    return _verdict(checks, failures)


def _verdict(checks: dict[str, bool], failures: list[str]) -> dict[str, Any]:
    accepted = not failures
    return {
        "checks": dict(checks),
        "failed_checks": list(failures),
        "attestation_accepted": accepted,
        # Fail-closed: anything short of full acceptance denies the governed path.
        "governed_write_path": "permitted" if accepted else "denied_fail_closed",
    }


INJECTION_CLASSES = (
    "invalid_signature",
    "expired_quote",
    "modified_measurement",
    "replayed_nonce",
    "revoked_platform_key",
    "downgraded_tcb_version",
)


def run_attestation_suite(seed: str = "dcse-v3-attestation") -> dict[str, Any]:
    """A valid quote plus one injection per declared class."""

    platform = derive_identity("platform", seed=seed)
    attacker = derive_identity("attacker", seed=seed)
    good_measurement = digest({"enclave": "gbi-dcse-coprocessor", "build": "v3.0"})
    policy = AttestationPolicy(
        measurement_allowlist=frozenset({good_measurement}),
        revoked_key_ids=frozenset({"platform-key-compromised"}),
    )
    now = 1_800_000_000.0
    challenge = "challenge-abc"

    baseline = issue_quote(
        platform, enclave_measurement=good_measurement, nonce=challenge, now=now
    )
    accepted = verify_quote(baseline, policy=policy, challenge_nonce=challenge, now=now + 1.0)

    cases: dict[str, dict[str, Any]] = {}

    # 1. Signature by the wrong key.
    forged = replace(baseline, signature=attacker.sign(baseline.signing_body()))
    cases["invalid_signature"] = verify_quote(
        forged, policy=policy, challenge_nonce=challenge, now=now + 1.0
    )

    # 2. Stale quote.
    cases["expired_quote"] = verify_quote(
        baseline,
        policy=policy,
        challenge_nonce=challenge,
        now=now + policy.max_age_seconds + 60.0,
    )

    # 3. Measurement modified after signing. Signature must catch it first.
    tampered = replace(baseline, enclave_measurement=digest({"enclave": "tampered"}))
    cases["modified_measurement"] = verify_quote(
        tampered, policy=policy, challenge_nonce=challenge, now=now + 1.0
    )

    # 3b. Measurement not on the allowlist, correctly signed for that measurement.
    unlisted = issue_quote(
        platform,
        enclave_measurement=digest({"enclave": "unapproved-build"}),
        nonce=challenge,
        now=now,
    )
    cases["unlisted_measurement_correctly_signed"] = verify_quote(
        unlisted, policy=policy, challenge_nonce=challenge, now=now + 1.0
    )

    # 4. Replay of a valid quote against a fresh challenge.
    cases["replayed_nonce"] = verify_quote(
        baseline, policy=policy, challenge_nonce="challenge-xyz", now=now + 1.0
    )

    # 5. Revoked platform key.
    revoked = issue_quote(
        platform,
        enclave_measurement=good_measurement,
        nonce=challenge,
        now=now,
        key_id="platform-key-compromised",
    )
    cases["revoked_platform_key"] = verify_quote(
        revoked, policy=policy, challenge_nonce=challenge, now=now + 1.0
    )

    # 6. TCB downgrade.
    downgraded = issue_quote(
        platform,
        enclave_measurement=good_measurement,
        nonce=challenge,
        now=now,
        tcb_version=policy.min_tcb_version - 1,
    )
    cases["downgraded_tcb_version"] = verify_quote(
        downgraded, policy=policy, challenge_nonce=challenge, now=now + 1.0
    )

    # Verification-path latency, measured over repeated verifications.
    samples: list[float] = []
    for _ in range(2000):
        start = time.perf_counter()
        verify_quote(baseline, policy=policy, challenge_nonce=challenge, now=now + 1.0)
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]

    all_denied = all(case["attestation_accepted"] is False for case in cases.values())
    return {
        "schema_version": "boundarybench.dcse_attestation_suite.v1",
        "attestation_version": ATTESTATION_VERSION,
        "declared_check_order": list(CHECK_ORDER),
        "baseline_accepted": accepted["attestation_accepted"],
        "baseline_verdict": accepted,
        "injection_cases": cases,
        "injection_classes_declared": list(INJECTION_CLASSES),
        "injection_cases_run": len(cases),
        "all_injections_fail_closed": all_denied,
        "every_case_denied_the_write_path": all(
            case["governed_write_path"] == "denied_fail_closed" for case in cases.values()
        ),
        "verification_latency_ms": {
            "samples": len(samples),
            "median": samples[len(samples) // 2],
            "p95": p95,
            "max": samples[-1],
        },
        "table_3_attestation_target_seconds": 2.5,
        "latency_scope": (
            "Software verification path only. Excludes hardware quote generation and "
            "the attestation-service round trip, which dominate a real deployment. "
            "Reported as a proxy, not as the Table 3 TEE/IAS handshake measurement."
        ),
        "hardware_root_of_trust_present": False,
        "attestation_bound_database_keys_claimed": False,
    }
