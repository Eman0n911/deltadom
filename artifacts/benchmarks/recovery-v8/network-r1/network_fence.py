"""Opt-in exact HTTP replay fence for one dedicated, owned browser context.

This is not HTTP/business idempotency. Redirects, GET writes, WebSockets,
service workers, request aliases and a server duplicating one request are outside
coverage. Identical intentional repetitions are blocked too. Never install this
on a user's general browsing session. Use service_workers='block', no other route
handlers, and retain the fence until the dedicated context is closed.
"""

import hashlib
import json
from urllib.parse import urlsplit

from .readback import same_origin


def request_signature(method, url, body):
    """Exact bytes deliberately avoid inventing endpoint-specific equivalences."""
    prefix = json.dumps([method.upper(), url], separators=(",", ":")).encode()
    return hashlib.sha256(len(prefix).to_bytes(8, "big") + prefix + (body or b"")).hexdigest()


class NetworkFence:
    def __init__(self, context, ledger, intent, *, origin):
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HTTP(S) origin required")
        self.context, self.ledger, self.intent = context, ledger, intent
        self.origin = origin
        self.decisions = []
        self._installed = False

    async def install(self):
        if self._installed:
            raise ValueError("fence already installed")
        if self.context.service_workers:
            raise ValueError("use a dedicated context with service workers blocked")
        await self.context.route("**/*", self._route)
        self._installed = True
        return self

    async def _route(self, route):
        request = route.request
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"} or not same_origin(
            self.origin, request.url
        ):
            await route.continue_()
            return
        signature = request_signature(request.method, request.url, request.post_data_buffer)
        try:
            admitted = self.ledger.admit_forward(self.intent, signature)
        except Exception as exc:  # noqa: BLE001 -- storage failure must not forward a write
            self.decisions.append({"admitted": False, "error": type(exc).__name__})
            await route.abort("blockedbyclient")
            return
        self.decisions.append({"admitted": admitted, "signature": signature,
                               "method": request.method})
        if admitted:
            # Never refund this permit if forwarding or response delivery fails.
            await route.continue_()
        else:
            await route.abort("blockedbyclient")
