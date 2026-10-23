"""Ground entity membership in an observed result view, without CSS from the model."""

from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError


class PresenceVerifier:
    """Witness an absent -> present transition in a separately loaded UI view.

    This deliberately supports record membership only. The actor must choose the
    right result view; it does not certify arbitrary task semantics or server state.
    """

    def __init__(self, entities, readback_url):
        if not entities or len(entities) > 32:
            raise ValueError("require 1..32 entities")
        for texts in entities:
            if not isinstance(texts, list) or len(texts) < 2 or len(texts) > 8:
                raise ValueError("each entity needs 2..8 exact visible identity strings")
            if any(not isinstance(t, str) or not t.strip() for t in texts):
                raise ValueError("identity strings must be nonempty")
            if len(set(texts)) != len(texts):
                raise ValueError("identity strings must be distinct")
        self.entities = tuple(tuple(texts) for texts in entities)
        self.readback_url = readback_url
        self.receipt = None
        self.baseline = None
        self.revision = 0

    @property
    def matched(self):
        return bool(self.receipt and self.receipt["revision"] == self.revision
                    and self.receipt["status"] == "new_membership_observed")

    def invalidate(self):
        self.revision += 1
        self.receipt = None

    async def read(self, page):
        rows = []
        # Require a rendered content region. Blank/error/loading pages are not absence.
        main = page.get_by_role("main")
        if await main.count() != 1 or not await main.is_visible():
            raise ValueError("no unique visible main content region")
        for texts in self.entities:
            scope = main.locator("article, tr, [role=row], li, [role=listitem]")
            for text in texts:
                scope = scope.filter(has=page.get_by_text(text, exact=True))
            matches = 0
            for item in await scope.all():
                if await item.is_visible() and all([
                    await item.get_by_text(t, exact=True).count() == 1
                    and await item.get_by_text(t, exact=True).is_visible() for t in texts
                ]):
                    matches += 1
            rows.append({"identity": list(texts), "matches": matches})
        return rows

    async def _visit(self, page, navigator):
        current, target = urlsplit(page.url), urlsplit(self.readback_url)
        if target.scheme not in {"http", "https"} or (current.scheme, current.netloc) != (target.scheme, target.netloc):
            raise ValueError("readback must stay on the current HTTP(S) origin")
        await navigator(self.readback_url)
        await page.wait_for_load_state("networkidle", timeout=10000)
        if page.url != self.readback_url:
            raise ValueError("readback redirected to another view")

    async def prepare(self, page, navigator):
        self.invalidate()
        self.baseline = None
        revision = self.revision
        # The entity must already be identifiable in the current visible source view.
        source = await self.read(page)
        if any(r["matches"] != 1 for r in source):
            raise ValueError("entity is not uniquely grounded in the source view")
        origin = page.url
        try:
            await self._visit(page, navigator)
            baseline = await self.read(page)
            if any(r["matches"] != 0 for r in baseline):
                raise ValueError("result view already contains entity or is ambiguous; no new-membership contract")
        finally:
            await navigator(origin)
            await page.wait_for_load_state("networkidle", timeout=10000)
        if revision != self.revision:
            raise ValueError("action during preparation")
        self.baseline = baseline
        return {"status": "prepared", "source": source, "baseline": self.baseline,
                "readback_url": self.readback_url,
                "scope": "record membership only; no arbitrary field or task-completeness guarantee"}

    async def verify(self, page, navigator):
        self.receipt = None
        revision = self.revision
        if self.baseline is None:
            raise ValueError("prepare before actions")
        try:
            await self._visit(page, navigator)
            rows = await self.read(page)
            matched = all(r["matches"] == 1 for r in rows)
            if revision != self.revision or page.url != self.readback_url:
                raise ValueError("action or URL changed during readback")
            self.receipt = {"status": "new_membership_observed" if matched else "unconfirmed",
                            "revision": revision, "before": self.baseline, "after": rows, "url": self.readback_url}
        except (PlaywrightError, ValueError) as exc:
            self.receipt = {"status": "unconfirmed", "revision": revision,
                            "error": type(exc).__name__ + ": " + str(exc)}
        return self.receipt
