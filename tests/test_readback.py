import pytest
import pytest_asyncio
from deltadom.readback import ObservedEntity, Readback, match_entities


@pytest_asyncio.fixture
async def readback_page(live):
    original, _ = live
    context = await original.context.browser.new_context()
    page = await context.new_page()
    yield page
    await context.close()


async def serve(page):
    state = {"label": "Cable", "href": "/item/1", "status": 200, "redirect": False}

    async def route(request):
        if state["redirect"] and request.request.url.endswith("/cart"):
            await request.fulfill(status=302, headers={"Location": "/login"})
        else:
            await request.fulfill(status=state["status"], content_type="text/html", body=(
                f'<main><input aria-label="Draft"><a href="{state["href"]}">{state["label"]}</a>'
                '<a href="/item/2">Cable</a><a hidden href="/hidden">Hidden</a></main>'
            ))
    await page.context.route("http://readback.test/**", route)
    await page.goto("http://readback.test/source")
    return state


async def test_fresh_readback_preserves_draft_and_document(readback_page):
    page = readback_page
    state = await serve(page)
    await page.get_by_role("textbox", name="Draft").fill("unsaved work")
    old = await page.query_selector("input")
    state["label"] = "Changed on server"
    result = await Readback(page).check("http://readback.test/cart", [
        ObservedEntity("http://readback.test/item/1", "Changed on server")
    ])
    assert result["status"] == "present"
    assert page.url == "http://readback.test/source"
    assert await old.input_value() == "unsaved work"
    assert len(page.context.pages) == 1


async def test_identity_not_label_and_no_new_insertion_claim(readback_page):
    page = readback_page
    await serve(page)
    reader = Readback(page)
    entity = ObservedEntity("http://readback.test/item/1", "Cable")
    for _ in range(2):
        result = await reader.check("http://readback.test/cart", [entity])
        assert result["status"] == "present"  # Already present remains a valid postcondition.
        assert result["entities"][0]["same_label_other_urls"] == 1
    wrong = await reader.check("http://readback.test/cart", [
        ObservedEntity("http://readback.test/item/missing", "Cable")
    ])
    assert wrong["status"] == "unconfirmed"
    hidden = await reader.check("http://readback.test/cart", [
        ObservedEntity("http://readback.test/hidden", "Hidden")
    ])
    assert hidden["status"] == "unconfirmed"


async def test_read_failure_never_becomes_absence(readback_page):
    page = readback_page
    state = await serve(page)
    reader = Readback(page)
    state["status"] = 503
    assert (await reader.read("http://readback.test/cart"))["status"] == "unconfirmed"
    state.update(status=200, redirect=True)
    assert (await reader.read("http://readback.test/cart"))["status"] == "unconfirmed"
    assert len(page.context.pages) == 1
    with pytest.raises(ValueError):
        await reader.read("https://elsewhere.test/cart")
    assert len(page.context.pages) == 1


def test_no_vacuous_success_or_quantity_from_duplicate_anchors():
    entity = ObservedEntity("http://readback.test/item/1", "Cable")
    evidence = {"links": [entity.__dict__, entity.__dict__]}
    assert match_entities(evidence, [entity])["entities"][0]["matching_links"] == 2
    assert "not quantity" in match_entities(evidence, [entity])["scope"]
    assert match_entities(evidence, [])["status"] == "unconfirmed"
