"""FastAPI router for USDA FAS Export Sales Reporting.

One route per task in ``tasks.__all__``, at ``/usda-esr/<task>``. A task whose
parameters are all scalars is a ``GET`` with query parameters; a task with any non-scalar
parameter is a ``POST`` whose JSON body is keyed by parameter name (ADR-0007). No logic
lives here (ADR-0001). The consumer mounts it; it is never served standalone.
"""

from xippios.core.http import router_from_tasks

from xippios.usda.esr import tasks
from xippios.usda.esr._client import SOURCE

router = router_from_tasks(SOURCE, [getattr(tasks, name) for name in tasks.__all__])

__all__ = ["router"]
