"""Async Playwright adapter. Network observation is opt-in and never replays requests."""

import asyncio
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass
from importlib.resources import files
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError

from ._core import DeltaSession

SNAPSHOT_JS = files("deltadom").joinpath("snapshot.js").read_text()


class StaleObservationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Observation:
    frame: dict
    nodes: tuple[dict, ...]
    api: tuple[dict, ...]
    settle: dict
    warnings: tuple[str, ...]
    timings_ms: dict

    @property
    def text(self):
        extras = {"settle": self.settle, "warnings": self.warnings, "api": self.api}
        return self.frame["text"] + json.dumps(extras, ensure_ascii=False, separators=(",", ":"))

    def find(self, *, tag=None, text=None, attr=None):
        """Find exact semantic nodes. Text nodes have tag '#text'; controls use attrs."""
        return [
            n
            for n in self.nodes
            if (tag is None or n["tag"] == tag)
            and (text is None or n["text"] == text)
            and (attr is None or n["attrs"].get(attr[0]) == attr[1])
        ]


def endpoint(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class DeltaBrowser:
    def __init__(
        self,
        page,
        *,
        api_fields=None,
        quiet_ms=60,
        timeout_ms=1500,
        threshold=0.45,
        keyframe_interval=20,
    ):
        if quiet_ms < 0 or timeout_ms <= 0 or quiet_ms > timeout_ms:
            raise ValueError("require 0 <= quiet_ms <= timeout_ms and positive timeout")
        self.page = page
        self.session = DeltaSession(threshold, keyframe_interval)
        self.api_fields = {endpoint(k): list(v) for k, v in (api_fields or {}).items()}
        for fields in self.api_fields.values():
            if not fields or len(fields) > 32 or any(not isinstance(f, str) for f in fields):
                raise ValueError("each API endpoint needs 1..32 explicit scalar field names")
        self.quiet_ms, self.timeout_ms = quiet_ms, timeout_ms
        self._key = "__deltadom_" + uuid.uuid4().hex
        self._lock = asyncio.Lock()
        self._inflight, self._tasks = set(), set()
        self._api = deque(maxlen=8)
        self._diagnostics = deque(maxlen=20)
        self._last_network = time.monotonic()
        self._generation = 0
        self._latest = None
        self._closed = False
        self._listeners = {
            "request": self._request,
            "requestfinished": self._done,
            "requestfailed": self._done,
            "response": self._response,
            "framenavigated": self._navigated,
        }
        for event, handler in self._listeners.items():
            page.on(event, handler)

    def _request(self, req):
        if req.resource_type in {"document", "xhr", "fetch"}:
            self._inflight.add(req)
            self._last_network = time.monotonic()

    def _done(self, req):
        if req in self._inflight:
            self._inflight.discard(req)
            self._last_network = time.monotonic()

    def _navigated(self, frame):
        if frame == self.page.main_frame:
            self._generation += 1
            self._api.clear()
            self._latest = None
            self._inflight.clear()
            self._last_network = time.monotonic()

    def _response(self, response):
        target = endpoint(response.url)
        if (
            target not in self.api_fields
            or response.request.resource_type not in {"xhr", "fetch"}
            or not 200 <= response.status < 300
        ):
            return
        if len(self._tasks) >= 8:
            self._diagnostics.append("API task limit reached; response omitted")
            return
        task = asyncio.create_task(self._capture_response(response, target, self._generation))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _capture_response(self, response, target, generation):
        try:
            headers = await response.all_headers()
            content_type = headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type != "application/json" and not content_type.endswith("+json"):
                return
            length = headers.get("content-length")
            # No streaming body API: reject unknown / compressed sizes BEFORE reading.
            if (
                length is None
                or not length.isdecimal()
                or int(length) > 1_048_576
                or headers.get("content-encoding", "identity") != "identity"
            ):
                self._diagnostics.append("API body omitted: unknown, encoded or oversized length")
                return
            body = await asyncio.wait_for(response.body(), timeout=self.timeout_ms / 1000)
            if len(body) > 1_048_576:
                self._diagnostics.append("API body omitted: actual size exceeds 1 MiB")
                return
            data = json.loads(
                self.session.filter_api_json(body.decode("utf-8"), self.api_fields[target])
            )
            if data["tables"] and generation == self._generation and not self._closed:
                if len(self._api) == self._api.maxlen:
                    self._diagnostics.append("API queue full; oldest observation evicted")
                self._api.append(
                    {
                        "source": target,
                        "status": response.status,
                        "kind": "untrusted_network_data",
                        **data,
                    }
                )
        except (PlaywrightError, TimeoutError, UnicodeError, ValueError) as exc:
            self._diagnostics.append("API capture failed: " + type(exc).__name__)

    async def _capture(self, mode="capture", **kwargs):
        if self._closed:
            raise RuntimeError("DeltaBrowser is closed")
        return await self.page.evaluate(SNAPSHOT_JS, {"key": self._key, "mode": mode, **kwargs})

    async def wait_settle(self):
        start = time.monotonic()
        deadline = start + self.timeout_ms / 1000
        while True:
            idle = await self._capture("idle")
            network_idle = (time.monotonic() - self._last_network) * 1000
            settled = (
                (time.monotonic() - start) * 1000 >= self.quiet_ms
                and not self._inflight
                and not self._tasks
                and idle["idle"] >= self.quiet_ms
                and network_idle >= self.quiet_ms
            )
            if settled or time.monotonic() >= deadline:
                return {
                    "status": "quiet" if settled else "timeout",
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
                    "pending_requests": len(self._inflight),
                    "pending_api": len(self._tasks),
                }
            await asyncio.sleep(min(0.015, max(0, deadline - time.monotonic())))

    async def observe(self, *, force_full=False):
        async with self._lock:
            start = time.perf_counter()
            settle = await self.wait_settle()
            t = time.perf_counter()
            raw = await self._capture()
            capture_ms = (time.perf_counter() - t) * 1000
            frame_input = {k: raw[k] for k in ("document", "url", "nodes")}
            t = time.perf_counter()
            frame = json.loads(self.session.process_frame(json.dumps(frame_input), force_full))
            core_ms = (time.perf_counter() - t) * 1000
            warnings = tuple(raw["warnings"]) + tuple(self._diagnostics)
            obs = Observation(
                frame,
                tuple(raw["nodes"]),
                tuple(self._api),
                settle,
                warnings,
                {
                    "capture": capture_ms,
                    "core_boundary": core_ms,
                    "total": (time.perf_counter() - start) * 1000,
                },
            )
            self._api.clear()
            self._diagnostics.clear()
            self._latest = obs
            return obs

    async def act(self, observation, node_id, action, value=None):
        """Resolve the exact observed DOM object. Reject old frames, replaced or changed nodes.

        Supports click/fill/select/check/uncheck. No model calls or request replay.
        """
        async with self._lock:
            if observation is not self._latest:
                raise StaleObservationError("observe again: this is not the latest observation")
            if action not in {"click", "fill", "select", "check", "uncheck"}:
                raise ValueError("unsupported action")
            if action in {"fill", "select"} and not isinstance(value, str):
                raise ValueError("fill/select requires a string value")
            expected = next((n for n in observation.nodes if n["id"] == node_id), None)
            if not expected or not expected["interactive"]:
                raise StaleObservationError("node is not an observed interactive target")
            current = await self._capture()
            actual = next((n for n in current["nodes"] if n["id"] == node_id), None)

            def subtree(nodes, root):
                included = {root}
                result = []
                for node in nodes:
                    if node["id"] == root or node["parent"] in included:
                        included.add(node["id"])
                        result.append(node)
                return result

            if (
                current["document"] != observation.frame["document"]
                or current["url"] != observation.frame["url"]
                or actual != expected
                or subtree(current["nodes"], node_id) != subtree(observation.nodes, node_id)
            ):
                raise StaleObservationError("document or target changed; observe again")
            handle = await self.page.evaluate_handle(
                SNAPSHOT_JS,
                {
                    "key": self._key,
                    "mode": "resolve",
                    "documentId": current["document"],
                    "nodeId": node_id,
                },
            )
            try:
                element = handle.as_element()
                if element is None:
                    raise StaleObservationError("target detached")
                self._latest = None  # one action per observation, including failed attempts
                if action == "fill":
                    await element.fill(value, timeout=self.timeout_ms)
                elif action == "select":
                    await element.select_option(value, timeout=self.timeout_ms)
                else:
                    await getattr(element, action)(timeout=self.timeout_ms)
            finally:
                await handle.dispose()

    async def close(self):
        if self._closed:
            return
        for event, handler in self._listeners.items():
            self.page.remove_listener(event, handler)
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if not self.page.is_closed():
            await self._capture("close")
        self._closed = True
        self._latest = None
        self._api.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
