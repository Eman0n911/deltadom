"""Capture a reproducible illustrative use case; never report it as benchmark evidence."""
import asyncio
import json
from pathlib import Path

from deltadom import ActionBinding, guarded_click
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets/ticket-queue'


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    html = (ROOT / 'examples/ticket_queue.html').read_text()
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        try:
            for mode in ['initial', 'ordinary', 'guarded', 'reorder']:
                page = await browser.new_page(viewport={'width': 1040, 'height': 650}, device_scale_factor=2)
                await page.route('http://ticket-story.test/**', lambda r: r.fulfill(content_type='text/html', body=html))
                await page.goto('http://ticket-story.test/queue')
                await page.evaluate('window.configure', mode)
                target = page.get_by_role('row').filter(
                    has=page.get_by_role('link', name='#1842', exact=True)
                ).get_by_role('button', name='标记完成', exact=True)
                binding, capture = await ActionBinding.capture(target)
                assert binding is not None, capture
                receipt = {'status': 'captured'}
                if mode == 'ordinary':
                    await target.click(timeout=1000)
                    receipt = {'status': 'clicked', 'method': 'semantic Locator.click'}
                elif mode in {'guarded', 'reorder'}:
                    if mode == 'reorder':
                        await page.evaluate('document.querySelector("tbody").append(document.querySelector("tbody tr"))')
                        await page.locator('#notice').evaluate('(e)=>e.textContent="#1842 从第一行移到第三行；身份没有改变。"')
                    receipt = await guarded_click(binding, page)
                effects = await page.evaluate('window.effects')
                expected = {'initial': [], 'ordinary': ['#2197'], 'guarded': [], 'reorder': ['#1842']}[mode]
                assert [effect['record'] for effect in effects] == expected, (mode, effects, receipt)
                assert all(effect['trusted'] for effect in effects)
                if mode == 'guarded':
                    assert receipt['status'] == 'blocked', receipt
                if mode == 'reorder':
                    assert receipt['status'] == 'clicked', receipt
                outcomes = {
                    'ordinary': {'kind': 'bad', 'title': '误操作：#2197 被标记完成', 'text': '本想处理 #1842，却触发了新工单的按钮。实际处理记录：#2197。'},
                    'guarded': {'kind': 'stop', 'title': '已拦截：没有工单被标记完成', 'text': '目标身份已改变，停止后续输入；#1842 尚未处理，需要重新检查页面。'},
                    'reorder': {'kind': 'good', 'title': '正确操作：#1842 被标记完成', 'text': '顺序改变不影响本例的身份匹配；其他工单保持待处理。'},
                }
                if mode in outcomes:
                    await page.evaluate('window.showOutcome', outcomes[mode])
                await page.screenshot(path=str(OUT / f'{mode}.png'), full_page=True)
                rows.append({'case': mode, 'binding': binding.data, 'receipt': receipt, 'effects': effects})
                await page.close()
        finally:
            await browser.close()
    (OUT / 'demonstration.json').write_text(json.dumps({
        'scope': 'Illustrative local ticket fixture. Not a customer deployment or independent benchmark.',
        'cases': rows,
    }, ensure_ascii=False, indent=2) + '\n')
    print('4 local story scenes verified; screenshots and raw receipts saved to', OUT)


if __name__ == '__main__':
    asyncio.run(main())
