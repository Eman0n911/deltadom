"""Attach a fresh UI observation to a native action after observed HTTP writes.

Only transport lifecycle is observed; no response bodies, hidden state or task
answers are inspected. A completed request is NOT evidence of business success.
"""

import asyncio
from time import monotonic_ns

from .readback import Readback, same_origin


class ActionReadback:
    def __init__(self, page, *, timeout_ms=10000):
        self.page = page
        self.timeout_ms = timeout_ms

    async def run(self, action, *, force_read=False, read_allowed=lambda: True):
        initial_url = self.page.url
        pending = set()
        writes = []
        changed = asyncio.Event()

        def started(request):
            if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                pending.add(request)
                writes.append({"method": request.method.upper(), "state": "pending",
                               "started_monotonic_ns": monotonic_ns()})
                request_rows[request] = writes[-1]
                changed.set()

        def ended(request, state):
            if request in request_rows:
                pending.discard(request)
                request_rows[request].update(state=state, completed_monotonic_ns=monotonic_ns())
                changed.set()

        def finished(request):
            ended(request, "transport_finished")

        def failed(request):
            ended(request, "transport_failed")

        request_rows = {}
        self.page.on("request", started)
        self.page.on("requestfinished", finished)
        self.page.on("requestfailed", failed)
        try:
            result = await action()
            deadline = asyncio.get_running_loop().time() + self.timeout_ms / 1000
            while pending:
                changed.clear()
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return result, {"status": "unconfirmed", "reason": "write_transport_still_pending",
                                    "writes": writes, "read_performed": False}
                try:
                    await asyncio.wait_for(changed.wait(), remaining)
                except TimeoutError:
                    return result, {"status": "unconfirmed", "reason": "write_transport_still_pending",
                                    "writes": writes, "read_performed": False}
            if not writes and not force_read:
                return result, {"status": "not_triggered", "writes": [], "read_performed": False}
            if not read_allowed():
                return result, {"status": "unconfirmed", "reason": "read_budget_exhausted",
                                "writes": writes, "read_performed": False}
            if not same_origin(initial_url, self.page.url):
                return result, {"status": "unconfirmed", "reason": "origin_changed",
                                "writes": writes, "read_performed": False}
            count_before_read = len(writes)
            receipt = await Readback(self.page, timeout_ms=self.timeout_ms).read(self.page.url)
            if pending or len(writes) != count_before_read:
                receipt = {**receipt, "status": "unconfirmed", "reason": "concurrent_write_during_readback"}
            return result, {**receipt, "writes": writes, "read_performed": True,
                            "trigger": "observed_http_write" if writes else "control_nonlink_click",
                            "scope": "UI loaded after observed write requests ended; no business-success, "
                                     "exactly-once, pending-job, or safe-retry guarantee"}
        finally:
            self.page.remove_listener("request", started)
            self.page.remove_listener("requestfinished", finished)
            self.page.remove_listener("requestfailed", failed)
