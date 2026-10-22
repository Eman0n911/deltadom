import os

import pytest_asyncio
from deltadom.demo import fixture_server
from playwright.async_api import async_playwright


@pytest_asyncio.fixture
async def live():
    with fixture_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel=os.environ.get("DELTADOM_CHANNEL"))
            page = await browser.new_page()
            yield page, url
            await browser.close()
