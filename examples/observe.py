"""Read a local sample twice. No model, API key or external site required."""

import asyncio

from deltadom import DeltaBrowser, StateMirror
from deltadom.demo import fixture_server
from deltadom.runtime import launch_browser
from playwright.async_api import async_playwright


async def main():
    with fixture_server() as url:
        async with async_playwright() as p:
            browser, _ = await launch_browser(p)
            page = await browser.new_page()
            await page.goto(url)
            async with DeltaBrowser(page) as delta:
                mirror = StateMirror()
                first = await delta.observe()
                mirror.apply(first.frame)
                target = first.find(tag="input", attr=("name", "query"))[0]
                await delta.act(first, target["id"], "fill", "Rust")
                changed = await delta.observe()
                current_nodes = mirror.apply(changed.frame)
                assert current_nodes == list(changed.nodes)
                print(changed.text)
                print(f"Reconstructed {len(current_nodes)} semantic nodes.")
            await browser.close()


asyncio.run(main())
