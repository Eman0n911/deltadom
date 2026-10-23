import pytest
from deltadom.presence import PresenceVerifier


async def test_membership_requires_new_unique_visible_record(live):
    page, _ = live
    state = {"saved": False, "duplicate": False}
    record = '<article><strong>Alice</strong><span>Invoice A</span></article>'

    async def route(request):
        if request.request.method == "POST":
            state["saved"] = True
            return await request.fulfill(body="{}", content_type="application/json")
        source = request.request.url.endswith("/source")
        body = record if source or state["saved"] else "<p>Empty</p>"
        if state["duplicate"]:
            body += record
        await request.fulfill(body='<main>' + body + '</main><button onclick="fetch(\'/save\',{method:\'POST\'})">Save</button>', content_type="text/html")

    await page.route("http://presence.test/**", route)
    await page.goto("http://presence.test/source")
    verifier = PresenceVerifier([["Alice", "Invoice A"]], "http://presence.test/result")
    await verifier.prepare(page, page.goto)
    assert not verifier.matched
    assert (await verifier.verify(page, page.goto))["status"] == "unconfirmed"
    await page.get_by_role("button", name="Save").click()
    await page.wait_for_load_state("networkidle")
    assert (await verifier.verify(page, page.goto))["status"] == "new_membership_observed"
    verifier.invalidate()
    assert not verifier.matched
    state["duplicate"] = True
    assert (await verifier.verify(page, page.goto))["status"] == "unconfirmed"
    state["duplicate"] = False

    async def concurrent_navigation(url):
        await page.goto(url)
        verifier.invalidate()

    assert (await verifier.verify(page, concurrent_navigation))["status"] == "unconfirmed"
    assert not verifier.matched
    assert (await verifier.verify(page, page.goto))["status"] == "new_membership_observed"
    with pytest.raises(ValueError, match="already contains"):
        await verifier.prepare(page, page.goto)
    assert verifier.baseline is None
    assert not verifier.matched


async def test_already_present_result_is_not_a_change_proof(live):
    page, _ = live
    await page.route("http://presence.test/**", lambda r: r.fulfill(
        body='<main><article><b>Alice</b><span>Invoice A</span></article></main>',
        content_type="text/html"))
    await page.goto("http://presence.test/source")
    verifier = PresenceVerifier([["Alice", "Invoice A"]], "http://presence.test/result")
    with pytest.raises(ValueError, match="already contains"):
        await verifier.prepare(page, page.goto)
    assert page.url == "http://presence.test/source"
    assert verifier.baseline is None
