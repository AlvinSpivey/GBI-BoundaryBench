"""Signing and digest primitives for the DCSE protocol layer.

Real Ed25519 signatures via ``cryptography``, not a keyed MAC. The distinction
matters for the Section 9.4 non-equivocation claim: equivocation evidence is only
useful if a third party who holds no secret can verify that a given node signed
two conflicting statements. A shared-key MAC cannot support that; a signature can.

Everything here is deterministic given the seeds, so a run is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

CRYPTO_VERSION = "dcse-crypto-v3.0"


def canonical_bytes(payload: Any) -> bytes:
    """Deterministic serialization, so a digest is a function of content alone."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Identity:
    """A node's signing identity."""

    node_id: str
    _private: Ed25519PrivateKey

    @property
    def public_key_hex(self) -> str:
        return (
            self._private.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            .hex()
        )

    def sign(self, payload: Any) -> str:
        return self._private.sign(canonical_bytes(payload)).hex()

    def sign_raw(self, raw: bytes) -> str:
        return self._private.sign(raw).hex()


def derive_identity(node_id: str, seed: str = "dcse-v3") -> Identity:
    """Deterministically derive a node identity from a seed and node id."""

    material = hashlib.sha256(f"{seed}|{node_id}".encode("utf-8")).digest()
    return Identity(node_id=node_id, _private=Ed25519PrivateKey.from_private_bytes(material))


def verify(public_key_hex: str, payload: Any, signature_hex: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(signature_hex), canonical_bytes(payload))
    except (InvalidSignature, ValueError):
        return False
    return True


def verify_raw(public_key_hex: str, raw: bytes, signature_hex: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(signature_hex), raw)
    except (InvalidSignature, ValueError):
        return False
    return True
