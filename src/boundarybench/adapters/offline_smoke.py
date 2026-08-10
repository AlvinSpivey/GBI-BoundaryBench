"""Offline adapter smoke runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boundarybench.adapters.offline import (
    OfflineOpenWeightFullCategoryAdapter,
    OfflineOutputOnlyAdapter,
    OfflineTokenTopKAdapter,
)
from boundarybench.adapters.prompting import request_from_task
from boundarybench.adapters.schemas import validate_model_response
from boundarybench.tasks.io import read_jsonl


def run_offline_smoke(tasks_path: Path) -> dict[str, Any]:
    tasks = read_jsonl(tasks_path)
    if not tasks:
        raise ValueError(f"no tasks found in {tasks_path}")
    request = request_from_task(tasks[0], seed=0)
    adapters = [
        OfflineOpenWeightFullCategoryAdapter(),
        OfflineTokenTopKAdapter(),
        OfflineOutputOnlyAdapter(),
    ]
    responses = []
    for adapter in adapters:
        response = adapter.generate(request)
        responses.append(
            {
                "adapter": adapter.__class__.__name__,
                "access_mode": adapter.config.access_mode,
                "is_mock": response.provenance["is_mock"],
                "execution_status": response.provenance["execution_status"],
                "validation_errors": validate_model_response(response.as_dict()),
                "observed_evidence": response.provenance["observed_evidence"],
            }
        )
    return {"schema_version": "boundarybench.adapter_smoke.v1", "responses": responses}


def main() -> None:
    root = Path.cwd()
    tasks_path = root / "data/tasks/public_dev/tasks.jsonl"
    print(json.dumps(run_offline_smoke(tasks_path), sort_keys=True))


if __name__ == "__main__":
    main()

