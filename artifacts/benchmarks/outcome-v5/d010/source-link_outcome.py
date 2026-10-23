"""Readback witness for observed entity links; no model-authored selectors."""

from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError


class LinkMembershipVerifier:
    """Witness new visible links with the same URL and visible name as the source.

    A URL is an observed UI identity, not a database key or a completeness proof.
    Repeated links to the same entity do not prove a quantity. No automatic writes.
    """

    def __init__(self, entities, readback_url):
        if not entities or len(entities) > 32:
            raise ValueError("require 1..32 observed entity links")
        self.entities = tuple((e["url"], e["label"]) for e in entities)
        if any(not isinstance(v, str) or not v.strip() for e in self.entities for v in e):
            raise ValueError("entity URL and visible label must be nonempty")
        if len({url for url, _ in self.entities}) != len(self.entities):
            raise ValueError("entity URLs must be distinct")
        self.readback_url = readback_url
        self.baseline = None
        self.receipt = None
        self.revision = 0

    def invalidate(self):
        self.revision += 1
        self.receipt = None

    @property
    def matched(self):
        return bool(self.receipt and self.receipt["revision"] == self.revision
                    and self.receipt["status"] == "new_link_membership_observed")

    async def read(self, page):
        main = page.get_by_role("main")
        if await main.count() != 1 or not await main.is_visible():
            raise ValueError("no unique visible main content region")
        links = await main.locator("a[href]:visible").evaluate_all(
            "els => els.map(e => ({url:e.href,label:e.innerText.trim()}))"
        )
        rows = []
        for url, label in self.entities:
            matches = [e for e in links if e["url"] == url and e["label"] == label]
            conflicts = [e for e in links if e["label"] == label and e["url"] != url]
            rows.append({"url": url, "label": label, "matching_links": len(matches),
                         "same_label_other_urls": len(conflicts)})
        return rows

    async def _visit(self, page, navigator):
        current = urlsplit(page.url)
        for url in [self.readback_url, *(u for u, _ in self.entities)]:
            target = urlsplit(url)
            if target.scheme not in {"http", "https"} or (target.scheme, target.netloc) != (current.scheme, current.netloc):
                raise ValueError("entity and readback links must stay on the current HTTP(S) origin")
        await navigator(self.readback_url)
        await page.wait_for_load_state("networkidle", timeout=10000)
        if page.url != self.readback_url:
            raise ValueError("readback redirected")

    async def prepare(self, page, navigator):
        self.invalidate()
        self.baseline = None
        revision = self.revision
        source = await self.read(page)
        # A current detail page can ground its own URL using one visible main h1.
        headings = page.get_by_role("main").locator("h1:visible")
        current_label = (await headings.inner_text()).strip() if await headings.count() == 1 else None
        for row in source:
            detail = row["url"] == page.url and row["label"] == current_label
            if not row["matching_links"] and not detail:
                raise ValueError("entity link/name is not grounded in the visible source")
        origin = page.url
        try:
            await self._visit(page, navigator)
            baseline = await self.read(page)
            if any(r["matching_links"] for r in baseline):
                raise ValueError("entity already visible in result view; cannot witness new membership")
        finally:
            await navigator(origin)
            await page.wait_for_load_state("networkidle", timeout=10000)
        if revision != self.revision:
            raise ValueError("action during preparation")
        self.baseline = baseline
        return {"status": "prepared", "entities": source, "baseline": baseline,
                "scope": "new observed link membership; not item quantity, selection optimality or task completeness"}

    async def verify(self, page, navigator):
        self.receipt = None
        revision = self.revision
        if self.baseline is None:
            raise ValueError("prepare before the relevant change")
        try:
            await self._visit(page, navigator)
            rows = await self.read(page)
            matched = all(r["matching_links"] > 0 for r in rows)
            if revision != self.revision or page.url != self.readback_url:
                raise ValueError("action or URL changed during readback")
            self.receipt = {"status": "new_link_membership_observed" if matched else "unconfirmed",
                            "revision": revision, "before": self.baseline, "after": rows}
        except (PlaywrightError, ValueError) as exc:
            self.receipt = {"status": "unconfirmed", "revision": revision,
                            "error": type(exc).__name__ + ": " + str(exc)}
        return self.receipt
