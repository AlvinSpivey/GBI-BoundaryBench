"""Provider-neutral model adapter API for GBI BoundaryBench."""

from boundarybench.adapters.base import BaseAdapter, ModelAdapter
from boundarybench.adapters.callable_adapters import (
    CallableOpenWeightFullCategoryAdapter,
    CallableOutputOnlyAdapter,
    CallableTokenTopKAdapter,
)
from boundarybench.adapters.offline import (
    OfflineOpenWeightFullCategoryAdapter,
    OfflineOutputOnlyAdapter,
    OfflineTokenTopKAdapter,
)
from boundarybench.adapters.prompting import request_from_task
from boundarybench.adapters.surrogate import LocalSurrogateProbeAdapter, SurrogateExample
from boundarybench.adapters.types import AdapterCapabilities, AdapterConfig, ModelRequest, ModelResponse, RetryPolicy

__all__ = [
    "AdapterCapabilities",
    "AdapterConfig",
    "BaseAdapter",
    "CallableOpenWeightFullCategoryAdapter",
    "CallableOutputOnlyAdapter",
    "CallableTokenTopKAdapter",
    "LocalSurrogateProbeAdapter",
    "ModelAdapter",
    "ModelRequest",
    "ModelResponse",
    "OfflineOpenWeightFullCategoryAdapter",
    "OfflineOutputOnlyAdapter",
    "OfflineTokenTopKAdapter",
    "RetryPolicy",
    "SurrogateExample",
    "request_from_task",
]
