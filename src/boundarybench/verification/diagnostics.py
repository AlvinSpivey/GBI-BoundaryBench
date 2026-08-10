"""Optional diagnostics kept outside the scoring path."""

from __future__ import annotations

from typing import Any


def sheaf_mapping_cone_diagnostic(*, enabled: bool) -> dict[str, Any]:
    """Return an explicit non-scoring diagnostic status.

    The sheaf/mapping-cone layer is not independently validated in this
    repository yet. It must remain diagnostic-only until validation artifacts
    exist.
    """

    if not enabled:
        return {
            "status": "NOT_RUN",
            "scoring_weight": 0,
            "validated": False,
            "reason": "diagnostic_not_requested",
        }
    return {
        "status": "DIAGNOSTIC_ONLY_NOT_VALIDATED",
        "scoring_weight": 0,
        "validated": False,
        "reason": "sheaf_mapping_cone_layer_lacks_independent_validation",
    }

