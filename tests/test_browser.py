import asyncio

import pytest
from deltadom import DeltaBrowser, StaleObservationError, StateMirror
from test_core import decode_full_text


async def test_real_actions_deltas_shadow_and_reload(live):
    page, url = live
    async with DeltaBrowser(page) as delta:
        await page.goto(url)
        first = await delta.observe()
        assert "PASSWORD-SENTINEL" not in first.text
        assert "HIDDEN-SENTINEL" not in first.text
        assert "data-bid" not in await page.content()
        assert decode_full_text(first.frame["text"]) == list(first.nodes)
        mirror = StateMirror()
        assert mirror.apply(first.frame) == list(first.nodes)
        empty = await delta.observe()
        assert empty.frame["upsert"] == [] and empty.frame["removed"] == []
        mirror.apply(empty.frame)
        with pytest.raises(StaleObservationError):
            await delta.act(first, first.find(tag="button")[0]["id"], "click")
        await delta.act(
            empty, empty.find(tag="input", attr=("name", "shadow"))[0]["id"], "fill", "hello"
        )
        obs = await delta.observe()
        assert mirror.apply(obs.frame) == list(obs.nodes)
        assert obs.find(tag="input", attr=("name", "shadow"))[0]["attrs"]["value"] == "hello"
        await delta.act(obs, obs.find(tag="select")[0]["id"], "select", "sale")
        obs = await delta.observe()
        assert mirror.apply(obs.frame) == list(obs.nodes)
        assert obs.find(tag="select")[0]["attrs"]["value"] == "sale"
        await delta.act(obs, obs.find(tag="input", attr=("name", "stock"))[0]["id"], "check")
        obs = await delta.observe()
        assert mirror.apply(obs.frame) == list(obs.nodes)
        assert obs.find(tag="input", attr=("name", "stock"))[0]["attrs"]["checked"] == "true"
        old_doc = obs.frame["document"]
        await page.reload()
        with pytest.raises(StaleObservationError):
            await delta.act(obs, obs.find(tag="select")[0]["id"], "select", "all")
        reloaded = await delta.observe()
        assert reloaded.frame["document"] != old_doc
        assert reloaded.frame["reason"] == "document_changed"


async def test_replaced_or_semantically_changed_target_rejected(live):
    page, url = live
    async with DeltaBrowser(page) as delta:
        await page.goto(url)
        obs = await delta.observe()
        target = obs.find(tag="button", attr=("id", "sort"))[0]
        await page.locator("#sort").evaluate(
            "el => el.textContent = 'Dangerous replacement meaning'"
        )
        with pytest.raises(StaleObservationError, match="changed"):
            await delta.act(obs, target["id"], "click")
        obs = await delta.observe()
        target = obs.find(tag="button", attr=("id", "sort"))[0]
        await page.locator("#sort").evaluate("el => el.replaceWith(el.cloneNode(true))")
        with pytest.raises(StaleObservationError, match="changed"):
            await delta.act(obs, target["id"], "click")


async def test_api_opt_in_and_body_task_awaited(live):
    page, url = live
    async with DeltaBrowser(page, api_fields={url + "/api/products": ["name", "price"]}) as delta:
        await page.goto(url)
        obs = await delta.observe()
        await delta.act(obs, obs.find(tag="button", attr=("id", "load"))[0]["id"], "click")
        await page.get_by_text("Loaded 2 API records", exact=True).wait_for()
        obs = await delta.observe()
        assert obs.api[0]["tables"][0]["rows"][0] == {"name": "Rust toolkit", "price": 19}
        assert "API-SECRET-SENTINEL" not in obs.text
        assert not (await delta.observe()).api  # consumed exactly once
    async with DeltaBrowser(page) as disabled:
        await page.locator("#load").click()
        assert not (await disabled.observe()).api


async def test_timeout_is_explicit_and_cleanup(live):
    page, url = live
    await page.goto(url)
    delta = DeltaBrowser(page, quiet_ms=40, timeout_ms=100)
    await delta.observe()
    await page.evaluate(
        "window.churn=setInterval(()=>document.querySelector('#status').textContent=String(performance.now()),5)"
    )
    obs = await delta.observe()
    assert obs.settle["status"] == "timeout"
    await page.evaluate("clearInterval(window.churn)")
    await delta.close()
    assert not delta._tasks
    assert await page.evaluate("key => window[key] === undefined", delta._key)
    with pytest.raises(RuntimeError, match="closed"):
        await delta.observe()


async def test_network_response_after_navigation_not_delivered(live):
    page, url = live
    async with DeltaBrowser(page, api_fields={url + "/api/products": ["name"]}) as delta:
        await page.goto(url)
        # Generation test exercises a late body completion using the real page's navigation.
        generation = delta._generation
        ready, release = asyncio.Event(), asyncio.Event()

        class LateResponse:
            status = 200

            async def all_headers(self):
                return {"content-type": "application/json", "content-length": "30"}

            async def body(self):
                ready.set()
                await release.wait()
                return b'{"items":[{"name":"stale"}]}'

        task = asyncio.create_task(
            delta._capture_response(LateResponse(), url + "/api/products", generation)
        )
        await ready.wait()
        await page.reload()
        release.set()
        await task
        assert not (await delta.observe()).api
