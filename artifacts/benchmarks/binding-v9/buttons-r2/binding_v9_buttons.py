"""Exhaustive actual button-input audit over all frozen BreakingWeb views."""
import os

os.environ['ANONYMIZED_TELEMETRY']='false'
os.environ['BROWSER_USE_LOGGING_LEVEL']='error'

import argparse
import asyncio
import hashlib
import json
import logging
import socket
import time
from pathlib import Path
from types import SimpleNamespace

from binding_context_baseline import ContextCheck
from browser_use import Agent, BrowserSession, Tools
from browser_use.dom.views import DOMInteractedElement
from deltadom.binding import ActionBinding
from deltadom.dispatch import guarded_click
from outcome_agent import BASE, ROOT, http_json
from playwright.async_api import async_playwright

ARMS=['native_history','full_row_check','dispatch_guard']
REORDER='''()=>{
 const groups=new Map();for(const e of document.querySelectorAll('article,tr,li')){
 const p=e.parentElement;if(!groups.has(p))groups.set(p,[]);groups.get(p).push(e)}
 let changed=0;for(const [p,items] of groups)if(items.length>1){p.insertBefore(items.at(-1),items[0]);changed++}return changed;
}'''


async def open_page(browser,task,condition,seed):
    params={'task_id':task['task_id'],'seed':seed}
    if condition=='intervention':params['variant_filename']=task['variant']
    session=await asyncio.to_thread(http_json,f"/api/env/{task['env']}/session",params)
    context=await browser.new_context();page=await context.new_page()
    await page.goto(BASE+f"/env/{task['env']}"+session['start_path']+f"?session={session['session_id']}&agent_mode=1",wait_until='networkidle')
    return context,page


async def native(browser_url,page):
    bs=BrowserSession(cdp_url=browser_url,keep_alive=True,enable_default_extensions=False)
    await bs.start()
    cdp=await page.context.new_cdp_session(page)
    bs.agent_focus_target_id=(await cdp.send('Target.getTargetInfo'))['targetInfo']['targetId']
    return bs


async def inventory(browser,browser_url,manifest,output):
    cells=[]
    for task in manifest['confirmation']:
        for condition in manifest['conditions']:
            entry={'task':task,'condition':condition,'buttons':[]}
            context=None;bs=None
            try:
                context,page=await open_page(browser,task,condition,manifest['seed'])
                bs=await native(browser_url,page)
                snapshot=await bs.get_browser_state_summary(include_screenshot=False)
                entry['buttons']=[{'xpath':n.xpath,'name':n.ax_node.name if n.ax_node else None,'native_index':i}
                  for i,n in snapshot.dom_state.selector_map.items() if n.node_name.upper()=='BUTTON']
                entry['status']='completed'
            except Exception as exc:entry.update(status='error',error=str(exc))  # noqa: BLE001
            finally:
                if bs:await bs.stop()
                if context:await context.close()
            cells.append(entry)
    frozen={'upstream':manifest['upstream'],'seed':manifest['seed'],'cells':cells}
    (output/'inventory.json').write_text(json.dumps(frozen,indent=2,ensure_ascii=False)+'\n')
    return frozen


async def trial(browser,browser_url,cell,button,arm,seed):
    row={'task':cell['task']['task_id'],'condition':cell['condition'],'button':button,'arm':arm}
    context=None;bs=None;events=[];start=time.perf_counter()
    try:
        context,page=await open_page(browser,cell['task'],cell['condition'],seed)
        target=page.locator('xpath=/'+button['xpath'].lstrip('/'))
        if await target.count()!=1:raise ValueError('frozen XPath unavailable')
        row['fresh_name']=await target.evaluate('e=>e.getAttribute("aria-label")||e.innerText')
        binding,capture=await ActionBinding.capture(target)
        row['capture']=capture
        full_row=await target.evaluate("e=>e.closest('article,tr,li,[role=row]')?.innerText ?? null")
        role=await target.get_attribute('role') or 'button'
        context_check=await ContextCheck.capture(page,target,button['name'] or '') if arm=='context_check' else None
        if context_check:row['baseline_capture']={'role':context_check.role,'name':context_check.name,'fingerprint':context_check.fingerprint}
        if arm=='native_history':
            bs=await native(browser_url,page)
            before=await bs.get_browser_state_summary(include_screenshot=False)
            nodes=[(i,n) for i,n in before.dom_state.selector_map.items() if n.xpath==button['xpath'] and n.node_name.upper()=='BUTTON']
            if len(nodes)!=1:raise ValueError('frozen target missing from native snapshot')
            idx,node=nodes[0];historic=DOMInteractedElement.load_from_enhanced_dom_tree(node)
        await page.expose_binding('__ddInputAudit',lambda source,event:events.append(event))
        await target.evaluate('''expected=>window.addEventListener('click',event=>{
          const button=event.target.closest?.('button');if(button)window.__ddInputAudit({same:button===expected,trusted:event.isTrusted});
        },true)''')
        row['reordered_groups']=await page.evaluate(REORDER)
        action_start=time.perf_counter()
        if arm=='native_history':
            after=await bs.get_browser_state_summary(include_screenshot=False)
            tools=Tools();action=tools.registry.create_action_model().model_validate({'click':{'index':idx}})
            updated=await Agent._update_action_indices(SimpleNamespace(logger=logging.getLogger('native_match')),historic,action,after)
            row['receipt']=(await tools.act(updated,browser_session=bs)).model_dump(exclude_none=True) if updated else {'status':'unresolved'}
        elif arm=='full_row_check':
            name=button['name'] or ''
            locator=page.get_by_role(role,name=name,exact=True)
            if full_row is not None:
                candidates=page.locator('article,tr,li,[role=row]')
                matches=[candidates.nth(i) for i in range(await candidates.count()) if await candidates.nth(i).inner_text()==full_row]
                if len(matches)!=1:raise ValueError('full row absent or ambiguous')
                locator=matches[0].get_by_role(role,name=name,exact=True)
            await locator.click(timeout=1000)
            row['receipt']={'status':'clicked'}
        elif arm=='context_check':
            row['receipt']=await context_check.click(page) if context_check else {'status':'unsupported'}
        elif binding:
            row['receipt']=await guarded_click(binding,page,timeout_ms=1000)
        else:row['receipt']=capture
        row['dispatch_seconds']=time.perf_counter()-action_start
        await page.wait_for_timeout(50)
        row['status']='completed'
    except Exception as exc:row.update(status='error',error=type(exc).__name__+': '+str(exc))  # noqa: BLE001
    finally:
        if bs:await bs.stop()
        if context:await context.close()
    blocked=row.get('receipt',{}).get('status') in {'blocked','unresolved','unsupported'}
    row.update(events=events,elapsed_seconds=time.perf_counter()-start,
      correct_input=bool(events) and all(e['same'] for e in events) and not blocked,
      wrong_input=any(not e['same'] for e in events) and not blocked,
      refusal=not events or blocked)
    return row


async def main(output,inventory_path=None,arms=None):
    output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'artifacts/benchmarks/outcome-v1/manifest.json').read_text())
    arms=arms or ARMS
    files=[Path(__file__),ROOT/'python/deltadom/binding.py',ROOT/'python/deltadom/binding.js',ROOT/'python/deltadom/dispatch.py',ROOT/'benchmarks/binding_context_baseline.py']
    sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    for f in files:(output/f.name).write_bytes(f.read_bytes())
    rows=[]
    async with async_playwright() as p:
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        browser=await p.chromium.launch(channel='chrome',args=[f'--remote-debugging-port={port}'])
        browser_url=f'http://127.0.0.1:{port}'
        try:
            if inventory_path:
                frozen=json.loads(inventory_path.read_text())
                (output/'inventory.json').write_bytes(inventory_path.read_bytes())
            else:frozen=await inventory(browser,browser_url,manifest,output)
            total=sum(len(c['buttons']) for c in frozen['cells'])*len(arms)
            print('FROZEN',total,'cells',flush=True)
            for cell in frozen['cells']:
                for button in cell['buttons']:
                    for arm in arms:
                        row=await trial(browser,browser_url,cell,button,arm,manifest['seed'])
                        rows.append(row)
                        with (output/'rows.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                        print(len(rows),total,cell['task']['env'],cell['condition'],button['native_index'],arm,row['correct_input'],row['wrong_input'],flush=True)
        finally:await browser.close()
    summary={arm:{k:sum(bool(r[k]) for r in rows if r['arm']==arm) for k in ['correct_input','wrong_input','refusal']} for arm in arms}
    (output/'result.json').write_text(json.dumps({'scope':'exhaustive input-identity audit, not task completion or server outcome',
      'sources':sources,'inventory_sha256':hashlib.sha256((output/'inventory.json').read_bytes()).hexdigest(),'summary':summary,'cells':len(rows)},indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inventory',type=Path);p.add_argument('--arms',nargs='+',choices=[*ARMS,'context_check'])
    args=p.parse_args()
    asyncio.run(main(args.output,args.inventory,args.arms))
