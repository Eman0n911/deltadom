import asyncio

import pytest
import pytest_asyncio
from deltadom.action_readback import ActionReadback


@pytest_asyncio.fixture
async def action_page(live):
    original, _ = live
    context = await original.context.browser.new_context()
    page = await context.new_page()
    state = {"persist": True, "saved": False, "posts": 0, "delay": 0}

    async def route(request):
        if request.request.method == "POST":
            state["posts"] += 1
            await asyncio.sleep(state["delay"])
            state["saved"] = state["persist"]
            await request.fulfill(content_type="application/json", body='{"ok":true}')
        else:
            await request.fulfill(content_type="text/html", body=(
                '<main><button onclick="document.querySelector(\'p\').textContent=\'Saved\';'
                'fetch(\'/save\',{method:\'POST\'})">Save</button>'
                f'<p>{"Saved" if state["saved"] else "Not saved"}</p>'
                '<button onclick="this.textContent=\'Expanded\'">Expand</button></main>'
            ))
    await context.route("http://action.test/**", route)
    await page.goto("http://action.test/")
    yield page, state
    await context.close()


@pytest.mark.parametrize("persist", [False, True])
async def test_observes_real_write_and_waits_before_read(action_page, persist):
    page, state = action_page
    state.update(persist=persist, delay=0.15)
    _, receipt = await ActionReadback(page).run(page.get_by_role("button", name="Save").click)
    assert state["posts"] == 1  # Never tuned or automatically retried.
    assert receipt["read_performed"]
    assert receipt["writes"][0]["state"] == "transport_finished"
    assert receipt["acquisition"]["started_monotonic_ns"] > receipt["writes"][0]["completed_monotonic_ns"]
    assert ("Not saved" in receipt["evidence"]["text"]) == (not persist)
    assert await page.locator("p").inner_text() == "Saved"  # optimistic working DOM stays untouched
    assert len(page.context.pages) == 1


async def test_no_http_write_skips_read_but_control_does_not(action_page):
    page, _ = action_page
    _, receipt = await ActionReadback(page).run(page.get_by_role("button", name="Expand").click)
    assert receipt["status"] == "not_triggered"
    _, control = await ActionReadback(page).run(
        page.get_by_role("button", name="Expanded").click, force_read=True
    )
    assert control["read_performed"] and control["writes"] == []


async def test_pending_write_budget_and_exception_cleanup(action_page):
    page, state = action_page
    state["delay"] = 0.2
    _, receipt = await ActionReadback(page, timeout_ms=20).run(page.get_by_role("button", name="Save").click)
    assert receipt["status"] == "unconfirmed" and not receipt["read_performed"]
    assert receipt["reason"] == "write_transport_still_pending"
    await page.wait_for_load_state("networkidle")
    state["delay"] = 0
    _, receipt = await ActionReadback(page).run(page.get_by_role("button", name="Save").click,
                                              read_allowed=lambda: False)
    assert receipt["reason"] == "read_budget_exhausted"
    assert state["posts"] == 2

    async def broken():
        raise ValueError("action failed")

    with pytest.raises(ValueError, match="action failed"):
        await ActionReadback(page).run(broken)
    # A subsequent run has one listener cohort, never duplicated writes or stale observations.
    _, final = await ActionReadback(page).run(page.get_by_role("button", name="Save").click)
    assert len(final["writes"]) == 1
    assert state["posts"] == 3
