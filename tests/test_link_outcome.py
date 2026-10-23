import pytest
from deltadom import LinkMembershipVerifier


async def test_link_identity_rejects_same_name_and_ignores_duplicate_links(live):
    page, _ = live
    state = {"saved": False}
    source = '<a href="/product/1">Cable</a><a href="/product/1"><img alt="Cable"></a>'
    wrong = '<a href="/product/2">Cable</a>'

    async def route(r):
        text = source if r.request.url.endswith("/source") or state["saved"] else wrong
        await r.fulfill(body=f'<main>{text}</main>', content_type="text/html")

    await page.route("http://witness.test/**", route)
    await page.goto("http://witness.test/source")
    verifier = LinkMembershipVerifier(
        [{"url": "http://witness.test/product/1", "label": "Cable"}], "http://witness.test/cart"
    )
    await verifier.prepare(page, page.goto)
    absent = await verifier.verify(page, page.goto)
    assert absent["status"] == "unconfirmed"
    assert absent["after"][0]["same_label_other_urls"] == 1
    state["saved"] = True
    assert (await verifier.verify(page, page.goto))["status"] == "new_link_membership_observed"
    verifier.invalidate()
    assert not verifier.matched


async def test_detail_page_grounding_and_concurrent_invalidation(live):
    page, _ = live
    saved = False

    async def route(r):
        if r.request.url.endswith("/product/1"):
            html = '<h1>Cable</h1><select><option>A</option><option>B</option></select>'
        else:
            html = '<a href="/product/1">Cable</a>' if saved else '<p>Empty cart</p>'
        await r.fulfill(body=f'<main>{html}</main>', content_type="text/html")

    await page.route("http://witness.test/**", route)
    await page.goto("http://witness.test/product/1")
    await page.locator("select").select_option(label="B")
    verifier = LinkMembershipVerifier(
        [{"url": page.url, "label": "Cable"}], "http://witness.test/cart"
    )
    await verifier.prepare(page, page.goto)
    saved = True

    async def concurrent_navigation(url):
        await page.goto(url)
        verifier.invalidate()

    assert (await verifier.verify(page, concurrent_navigation))["status"] == "unconfirmed"
    assert not verifier.matched
    assert (await verifier.verify(page, page.goto))["status"] == "new_link_membership_observed"
    await page.goto("http://witness.test/product/1")
    with pytest.raises(ValueError, match="already visible"):
        await verifier.prepare(page, page.goto)
    assert verifier.baseline is None
    assert not verifier.matched


async def test_wrong_origin_and_ungrounded_entity(live):
    page, _ = live
    await page.route("http://witness.test/**", lambda r: r.fulfill(
        body='<main><a href="/item">A</a></main>', content_type="text/html"))
    await page.goto("http://witness.test/source")
    verifier = LinkMembershipVerifier([{"url": "http://witness.test/item", "label": "A"}], "http://other.test/")
    with pytest.raises(ValueError, match="origin"):
        await verifier.prepare(page, page.goto)
    assert page.url == "http://witness.test/source"
    verifier = LinkMembershipVerifier([{"url": "http://witness.test/item", "label": "Wrong"}], "http://witness.test/cart")
    with pytest.raises(ValueError, match="not grounded"):
        await verifier.prepare(page, page.goto)


def test_duplicate_urls_are_not_distinct_entities():
    with pytest.raises(ValueError, match="distinct"):
        LinkMembershipVerifier([{"url": "http://a.test/p", "label": "A"}] * 2, "http://a.test/cart")
