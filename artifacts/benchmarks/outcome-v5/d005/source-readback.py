"""Fresh UI readback without navigating or invalidating the actor's page.

This is a postcondition query, not a transaction, retry policy, or task judge.
No baseline-absence requirement: an already satisfied condition is valid evidence.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError


@dataclass(frozen=True)
class ObservedEntity:
    url: str
    label: str

    def __post_init__(self):
        if not isinstance(self.url, str) or not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("require an observed URL and nonempty visible label")


def same_origin(source, target):
    a, b = urlsplit(source), urlsplit(target)
    return (b.scheme in {"http", "https"} and not b.username and not b.password
            and (a.scheme, a.netloc) == (b.scheme, b.netloc))


async def visible_evidence(page):
    """One DOM evaluation: no joins between different document revisions."""
    return await page.evaluate("""() => {
      const visible = e => e.checkVisibility({checkVisibilityCSS:true, checkOpacity:true});
      const mains = [...document.querySelectorAll('main,[role="main"]')].filter(visible);
      if (mains.length > 1) throw Error('ambiguous main region');
      const main = mains[0] || document.body;
      if (!main || !visible(main)) throw Error('no visible content region');
      const label = e => e.getAttribute('aria-label') ||
        [...(e.labels || [])].map(l=>l.innerText.trim()).join(' ') ||
        e.getAttribute('placeholder') || e.innerText.trim();
      return {url:location.href, region:mains.length ? 'main' : 'body', text:main.innerText,
        controls:[...main.querySelectorAll('input,textarea,select,button,[role="checkbox"],[role="switch"]')]
          .filter(e=>visible(e) && e.type!=='password' && e.type!=='hidden')
          .map(e=>({tag:e.tagName.toLowerCase(),type:e.type || e.getAttribute('role') || '',
            label:label(e),value:e.value ?? null,checked:typeof e.checked==='boolean' ? e.checked : null,
            ariaChecked:e.getAttribute('aria-checked'),ariaPressed:e.getAttribute('aria-pressed')})),
        links:[...main.querySelectorAll('a[href]')].filter(visible)
          .map(e=>({url:e.href,label:e.innerText.trim()}))};
    }""")


def match_entities(evidence, entities):
    """Exact UI identity. Duplicated anchors are not a count of business objects."""
    rows = []
    for entity in entities:
        rows.append({"url": entity.url, "label": entity.label,
                     "matching_links": sum(e["url"] == entity.url and e["label"] == entity.label
                                           for e in evidence["links"]),
                     "same_label_other_urls": sum(e["url"] != entity.url and e["label"] == entity.label
                                                 for e in evidence["links"])})
    return {"status": "present" if rows and all(r["matching_links"] for r in rows)
            else "unconfirmed", "entities": rows,
            "scope": "visible link membership at read time only; not quantity, new insertion, "
                     "selection optimality, persistence guarantee or complete task success"}


class Readback:
    """Open one fresh same-origin UI view, inspect it, and close it.

    A temporary page shares cookies/localStorage, but not the actor's DOM or
    sessionStorage. Login redirects, ambiguous regions and timeouts are
    unconfirmed. No absence proof is returned and no action is automatically retried.
    """

    def __init__(self, actor_page, *, timeout_ms=10000):
        self.actor = actor_page
        self.timeout_ms = timeout_ms

    async def read(self, url):
        if not same_origin(self.actor.url, url):
            raise ValueError("readback must use an observed same-origin HTTP(S) UI URL")
        probe = None
        try:
            probe = await self.actor.context.new_page()
            response = await probe.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            if not response or not response.ok or probe.url != url:
                raise ValueError("readback failed or redirected")
            evidence = await visible_evidence(probe)
            if evidence["url"] != url:
                raise ValueError("readback view changed")
            return {"status": "read", "evidence": evidence}
        except (PlaywrightError, ValueError) as exc:
            return {"status": "unconfirmed", "error": type(exc).__name__ + ": " + str(exc)}
        finally:
            if probe is not None:
                await probe.close()

    async def check(self, url, entities):
        entities = tuple(entities)
        if not 1 <= len(entities) <= 32:
            raise ValueError("require 1..32 observed entities")
        if len({e.url for e in entities}) != len(entities):
            raise ValueError("entity URLs must be distinct")
        if any(not same_origin(self.actor.url, e.url) for e in entities):
            raise ValueError("entity URLs must be same-origin")
        result = await self.read(url)
        if result["status"] != "read":
            return result
        return {**match_entities(result["evidence"], entities), "readback_url": url}
