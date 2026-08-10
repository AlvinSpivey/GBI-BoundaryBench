"""Canonical hashing helpers for prompts and adapter configuration."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data deterministically."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def prompt_sha256(prompt: str) -> str:
    return sha256_text(prompt)


def config_sha256(config: dict[str, Any]) -> str:
    return sha256_text(canonical_json(config))

