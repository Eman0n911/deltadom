"""Browser discovery shared by the demo and installation check."""

import platform

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from . import DeltaSession


class BrowserUnavailable(RuntimeError):
    pass


async def launch_browser(playwright, channel="auto", *, headless=True):
    choices = (
        [None, "chrome"]
        if channel in {None, "auto"}
        else [None if channel == "chromium" else channel]
    )
    errors = []
    for choice in choices:
        try:
            browser = await playwright.chromium.launch(channel=choice, headless=headless)
            return browser, choice or "chromium"
        except PlaywrightError as exc:
            errors.append(f"{choice or 'chromium'}: {exc}")
    raise BrowserUnavailable(
        "无法启动演示浏览器。请安装 Google Chrome，或在安装环境中运行：\n"
        "python -m playwright install chromium\n"
        "然后运行 deltadom doctor 检查。浏览器诊断：\n" + "\n".join(errors)
    )


async def inspect_browser():
    DeltaSession().process_frame('{"document":"doctor","url":"local","nodes":[]}')
    async with async_playwright() as p:
        browser, channel = await launch_browser(p)
        report = {
            "status": "ready",
            "python": platform.python_version(),
            "browser": browser.version,
            "channel": channel,
            "native_core": "ok",
        }
        await browser.close()
        return report
