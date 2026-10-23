"""Explicit, visible-page outcome checks. Never reads evaluator or backend state.

Contracts come from the caller/actor before execution; their semantic completeness
is not guaranteed. A match after reload is page evidence, not a server commit proof.
"""

from dataclasses import asdict, dataclass
from time import monotonic
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError

SAFE_ATTRIBUTES = {"aria-checked", "aria-pressed", "aria-selected", "aria-label", "title"}


@dataclass(frozen=True)
class OutcomeCheck:
    key: str
    scope: str
    identity: str
    target: str
    kind: str
    expected: str | bool
    attribute: str | None = None

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in
               (self.key, self.scope, self.identity, self.target)):
            raise ValueError("key, scope, identity and target must be nonempty strings")
        if self.kind not in {"text", "value", "checked", "attribute"}:
            raise ValueError("unsupported check kind")
        if self.kind == "checked":
            if type(self.expected) is not bool:
                raise ValueError("checked requires a boolean expectation")
        elif not isinstance(self.expected, str):
            raise ValueError("text/value/attribute requires a string expectation")
        if self.kind == "attribute" and self.attribute not in SAFE_ATTRIBUTES:
            raise ValueError("only visible semantic attributes are supported")


class OutcomeVerifier:
    """Freeze a caller-supplied contract and verify it on a fresh visible read.

    Does not retry writes or decide whether a task contract is complete. Call
    invalidate() after every action, including failed/ambiguous action attempts.
    """

    def __init__(self, checks, *, readback_url=None, timeout_ms=3000):
        self.checks = tuple(checks)
        if not self.checks or len(self.checks) > 100:
            raise ValueError("require 1..100 explicit checks")
        if len({c.key for c in self.checks}) != len(self.checks):
            raise ValueError("check keys must be unique")
        self.timeout_ms = timeout_ms
        self.readback_url = readback_url
        self.revision = 0
        self.receipt = None

    def invalidate(self):
        self.revision += 1
        self.receipt = None

    @property
    def matched(self):
        return bool(self.receipt and self.receipt["revision"] == self.revision
                    and self.receipt["status"] == "matched_after_reload")

    async def _read(self, page, check):
        # Identity and desired state are distinct: never locate by expected value.
        scope = page.locator(check.scope).filter(
            has=page.get_by_text(check.identity, exact=True)
        )
        count = await scope.count()
        if count != 1:
            return {"key": check.key, "status": "unknown", "reason": "identity_not_unique",
                    "matches": count}
        identity = scope.get_by_text(check.identity, exact=True)
        if await identity.count() != 1 or not await identity.is_visible():
            return {"key": check.key, "status": "unknown", "reason": "identity_not_unique_or_visible"}
        target = scope.locator(check.target)
        if await target.count() != 1 or not await target.is_visible():
            return {"key": check.key, "status": "unknown", "reason": "target_not_unique_or_visible"}
        if check.kind == "text":
            actual = await target.inner_text(timeout=self.timeout_ms)
        elif check.kind == "value":
            if await target.get_attribute("type") == "password":
                return {"key": check.key, "status": "unknown", "reason": "password_not_read"}
            actual = await target.input_value(timeout=self.timeout_ms)
        elif check.kind == "checked":
            actual = await target.is_checked(timeout=self.timeout_ms)
        else:
            actual = await target.get_attribute(check.attribute, timeout=self.timeout_ms)
        return {"key": check.key, "status": "match" if actual == check.expected else "mismatch",
                "identity": check.identity, "expected": check.expected, "actual": actual}

    async def verify(self, page):
        self.receipt = None
        revision = self.revision
        start = monotonic()
        url = self.readback_url or page.url
        rows = []
        refresh_error = None
        try:
            target, current = urlsplit(url), urlsplit(page.url)
            if target.scheme not in {"http", "https"} or (target.scheme, target.netloc) != (current.scheme, current.netloc):
                raise ValueError("readback URL must stay on the current HTTP(S) origin")
            if self.readback_url:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            else:
                await page.reload(wait_until="networkidle", timeout=self.timeout_ms)
            for check in self.checks:
                rows.append(await self._read(page, check))
        except (PlaywrightError, ValueError) as exc:
            refresh_error = type(exc).__name__ + ": " + str(exc)
        complete = len(rows) == len(self.checks)
        matched = complete and all(r["status"] == "match" for r in rows)
        if revision != self.revision or page.url != url:
            refresh_error = "action or URL changed during verification"
        self.receipt = {
            "status": "matched_after_reload" if matched and not refresh_error else "unconfirmed",
            "revision": revision, "url": url, "checks": rows, "error": refresh_error,
            "elapsed_ms": round((monotonic() - start) * 1000, 3),
            "scope": "caller-declared checks on visible page after reload; not task completeness or backend commit proof",
            "contract": [asdict(c) for c in self.checks],
        }
        return self.receipt
