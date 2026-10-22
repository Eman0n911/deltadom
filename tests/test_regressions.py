"""Failures observed in the October observation/model pilot."""

import json

from deltadom import DeltaBrowser, DeltaSession
from test_core import node, process


async def test_pointer_listener_and_empty_icon_are_actionable(live):
    page, url = live
    await page.goto(url)
    await page.set_content("""<style>.icon-trash::before{content:"\\2716"}</style><div id="thread" style="cursor:pointer">Message</div>
      <span id="trash" class="icon-trash" style="cursor:pointer"></span>
      <span id="status">pending</span><span id="inline" onclick="this.textContent='done'"></span>
      <script>thread.addEventListener('click',()=>statusNode.textContent='opened');
      const statusNode=document.querySelector('#status');
      trash.addEventListener('click',()=>statusNode.textContent='deleted');</script>""")
    async with DeltaBrowser(page) as delta:
        for target, expected in [("thread", "opened"), ("trash", "deleted")]:
            obs = await delta.observe()
            nodes = obs.find(attr=("id", target))
            assert nodes and nodes[0]["interactive"], f"{target} missing from action surface"
            await delta.act(obs, nodes[0]["id"], "click")
            assert await page.locator("#status").inner_text() == expected
        obs = await delta.observe()
        target = obs.find(attr=("id", "inline"))
        assert target and target[0]["interactive"]




def test_attribute_only_change_does_not_resend_long_unchanged_text():
    session = DeltaSession(1.0, 20)
    nodes = [node(1, text="unchanged-description-" * 100, tag="button")]
    process(session, nodes)
    nodes[0]["attrs"]["aria-pressed"] = "true"
    delta = process(session, nodes)
    assert "unchanged-description" not in delta["text"]
    assert "aria-pressed" in delta["text"]
    assert json.loads(json.dumps(delta))["upsert"] == nodes


async def test_action_without_immediate_mutation_still_waits(live):
    page, url = live
    await page.goto(url)
    await page.set_content(
        """<button onclick="setTimeout(()=>document.querySelector('p').textContent='done',30)">Start</button><p>waiting</p>"""
    )
    async with DeltaBrowser(page, quiet_ms=70) as delta:
        obs = await delta.observe()
        await delta.act(obs, obs.find(tag="button")[0]["id"], "click")
        result = await delta.observe()
        assert result.find(text="done")
        assert result.settle["status"] == "quiet"


async def test_capture_on_non_secure_blank_page(live):
    page, _ = live
    await page.set_content("<button>Blank page</button>")
    async with DeltaBrowser(page, quiet_ms=0) as delta:
        assert (await delta.observe()).find(tag="button")
