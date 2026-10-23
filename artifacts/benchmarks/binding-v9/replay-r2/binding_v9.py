"""Fixed native history matcher + real action versus relational replay controls."""
import os
os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['BROWSER_USE_LOGGING_LEVEL'] = 'error'

import argparse
import asyncio
import hashlib
import json
import logging
import socket
from pathlib import Path
from types import SimpleNamespace

from browser_use import Agent, BrowserSession, Tools
from browser_use.dom.views import DOMInteractedElement
from deltadom.binding import ActionBinding
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = '''<main><p id="ticker">Update 0</p>
<article><a href="/records/A">Record A</a><button>Mark complete</button></article>
<article><a href="/records/B">Record B</a><button>Mark complete</button></article></main>
<script>window.actions=[];window.override=null;
document.addEventListener('click',e=>{if(e.target.tagName==='BUTTON'){
 const row=e.target.closest('article');const a=row?.querySelector('a');
 window.actions.push({url:window.override || a?.href || null,name:a?.innerText || null,button:e.target.innerText});
}});</script>'''
# expected target URL/name are task data, never hidden identifiers in the component.
CASES = {
 'unchanged': '()=>{}',
 'reorder': '()=>document.querySelector("main").prepend(document.querySelectorAll("article")[1])',
 'remount': '()=>{let e=document.querySelector("article");e.replaceWith(e.cloneNode(true))}',
 'wrapper_change': '()=>{let b=document.querySelector("button"),d=document.createElement("div");b.replaceWith(d);d.append(b)}',
 'insert_before': '()=>{let e=document.querySelectorAll("article")[1].cloneNode(true);e.querySelector("a").href="/records/C";e.querySelector("a").textContent="Record C";document.querySelector("main").prepend(e)}',
 'target_removed': '()=>document.querySelector("article").remove()',
 'duplicate_identity': '()=>document.querySelector("main").append(document.querySelector("article").cloneNode(true))',
 'name_changed': '()=>document.querySelector("article a").textContent="Record Z"',
 'unrelated_timer': '()=>document.querySelector("#ticker").textContent="Update 99"',
 'url_changed': '()=>document.querySelector("article a").href="/records/Z"',
 'global_unique': '()=>{}',
 'global_duplicate': '()=>document.querySelector("main").append(document.querySelector("button").cloneNode(true))',
 'no_link_reorder': '()=>document.querySelector("main").prepend(document.querySelectorAll("article")[1])',
 'invisible_handler': '()=>window.override="http://replay.test/records/Z"',
}
ARMS = ['native_history', 'manual_semantic', 'automatic_binding']


async def trial(browser, bs, case, arm):
    context = await browser.new_context()
    page = await context.new_page()
    html = HTML
    if case.startswith('global_'):
        html = '<main><button>Continue</button></main><script>window.actions=[];document.querySelector("button").onclick=()=>window.actions.push({button:"Continue"})</script>'
    elif case == 'no_link_reorder':
        html = HTML.replace('<a href="/records/A">Record A</a>', '<span>Record A</span>').replace('<a href="/records/B">Record B</a>', '<span>Record B</span>')
        html = html.replace('a?.href || null', 'row?.innerText.startsWith("Record A")?"http://replay.test/records/A":"http://replay.test/records/B"')
        html = html.replace('name:a?.innerText || null', 'name:row?.innerText.startsWith("Record A")?"Record A":"Record B"')
    await context.route('http://replay.test/**', lambda route: route.fulfill(content_type='text/html', body=html))
    await page.goto('http://replay.test/list')
    cdp = await context.new_cdp_session(page)
    bs.agent_focus_target_id = (await cdp.send('Target.getTargetInfo'))['targetInfo']['targetId']
    row = {'case': case, 'arm': arm}
    try:
        before = await bs.get_browser_state_summary(include_screenshot=False)
        buttons = [(i,n) for i,n in before.dom_state.selector_map.items() if n.node_name.lower()=='button']
        idx, node = buttons[0]
        historic = DOMInteractedElement.load_from_enhanced_dom_tree(node)
        binding, capture = await ActionBinding.capture(page.get_by_role('button').first)
        row.update(history_element=historic.to_dict(), binding_capture=capture)
        await page.evaluate(CASES[case])
        correct_available = case not in {'target_removed','duplicate_identity','name_changed','url_changed','global_duplicate','invisible_handler'}
        row['correct_target_available'] = correct_available
        error = None
        try:
            if arm == 'native_history':
                after = await bs.get_browser_state_summary(include_screenshot=False)
                tools = Tools()
                model = tools.registry.create_action_model()
                action = model.model_validate({'click': {'index':idx}})
                updated = await Agent._update_action_indices(SimpleNamespace(logger=logging.getLogger('native_match')),historic,action,after)
                if updated is None:
                    result = {'status':'unresolved'}
                else:
                    result = (await tools.act(updated,browser_session=bs)).model_dump(exclude_none=True)
                row['result'] = result
            elif arm == 'manual_semantic':
                if case.startswith('global_'):
                    locator = page.get_by_role('button',name='Continue',exact=True)
                elif case == 'no_link_reorder':
                    locator = page.get_by_role('article').filter(has=page.get_by_text('Record A',exact=True)).get_by_role('button',name='Mark complete',exact=True)
                else:
                    locator = page.get_by_role('article').filter(has=page.locator('a[href="/records/A"]').filter(has_text='Record A')).get_by_role('button',name='Mark complete',exact=True)
                await locator.click(timeout=500)
                row['result'] = {'status':'clicked'}
            elif binding is None:
                row['result'] = capture
            else:
                row['result'] = await ActionBinding.from_json(binding.to_json()).click(page,timeout_ms=500)
        except Exception as exc:  # noqa: BLE001 -- no dropped cells
            error = type(exc).__name__ + ': ' + str(exc)
        actions = await page.evaluate('window.actions')
        correct = bool(actions) and correct_available and (case.startswith('global_') or actions == [{'url':'http://replay.test/records/A','name':'Record A','button':'Mark complete'}])
        row.update(actions=actions,error=error,correct_action=correct,
                   wrong_action=bool(actions) and not correct,
                   false_refusal=not actions and correct_available,
                   justified_refusal=not actions and not correct_available,status='completed')
    finally:
        await context.close()
    return row


async def main(output):
    output.mkdir(parents=True,exist_ok=False)
    files = [Path(__file__), ROOT/'python/deltadom/binding.py',ROOT/'python/deltadom/binding.js']
    for f in files:
        (output/f.name).write_bytes(f.read_bytes())
    rows=[]
    async with async_playwright() as p:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        browser=await p.chromium.launch(channel='chrome',args=[f'--remote-debugging-port={port}'])
        bs=BrowserSession(cdp_url=f'http://127.0.0.1:{port}',keep_alive=True,enable_default_extensions=False)
        await bs.start()
        try:
            for case in CASES:
                for arm in ARMS:
                    try:
                        row=await trial(browser,bs,case,arm)
                    except Exception as exc:  # noqa: BLE001 -- retain failures
                        row={'case':case,'arm':arm,'status':'harness_error','error':str(exc)}
                    rows.append(row)
                    with (output/'rows.jsonl').open('a') as stream: stream.write(json.dumps(row)+'\n')
                    print(case,arm,row.get('correct_action'),row.get('wrong_action'),row.get('false_refusal'),flush=True)
        finally:
            await bs.stop(); await browser.close()
    summary={arm:{k:sum(bool(r.get(k)) for r in rows if r['arm']==arm) for k in ['correct_action','wrong_action','false_refusal','justified_refusal']} for arm in ARMS}
    (output/'result.json').write_text(json.dumps({'scope':'native replay matching + real UI actions, not full autonomous agent scores',
      'sources':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'summary':summary,'rows':rows},indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    asyncio.run(main(parser.parse_args().output))
