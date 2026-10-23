"""All original 14 BreakingWeb initial views: read-only binding portability audit.

Every native selector-map node is retained. No candidate-driven task selection,
no writes or evaluator. Reorder semantic siblings and compare actual DOM identity.
"""
import os
os.environ['ANONYMIZED_TELEMETRY']='false'
os.environ['BROWSER_USE_LOGGING_LEVEL']='error'

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
from outcome_agent import BASE, ROOT, http_json
from playwright.async_api import async_playwright


async def cell(browser,bs,task,condition,manifest):
    row={'task':task['task_id'],'condition':condition,'nodes':[]}
    context=await browser.new_context()
    try:
        params={'task_id':task['task_id'],'seed':manifest['seed']}
        if condition=='intervention':params['variant_filename']=task['variant']
        session=await asyncio.to_thread(http_json,f"/api/env/{task['env']}/session",params)
        page=await context.new_page()
        await page.goto(BASE+f"/env/{task['env']}"+session['start_path']+f"?session={session['session_id']}&agent_mode=1",wait_until='networkidle')
        cdp=await context.new_cdp_session(page)
        bs.agent_focus_target_id=(await cdp.send('Target.getTargetInfo'))['targetInfo']['targetId']
        snapshot=await bs.get_browser_state_summary(include_screenshot=False)
        held=[]
        for idx,node in snapshot.dom_state.selector_map.items():
            entry={'native_index':idx,'tag':node.node_name,'name':node.ax_node.name if node.ax_node else None}
            original=None;binding=None;historic=DOMInteractedElement.load_from_enhanced_dom_tree(node)
            try:
                locator=page.locator('xpath=/'+node.xpath.lstrip('/'))
                if await locator.count()!=1:
                    raise ValueError('native XPath does not identify one top-document element')
                original=await locator.element_handle()
                binding,capture=await ActionBinding.capture(locator)
                entry['capture']=capture
            except Exception as exc:  # noqa: BLE001 -- retain every native node
                entry['capture_error']=type(exc).__name__+': '+str(exc)
            held.append((entry,original,binding,historic,idx,node.backend_node_id))
        row['reordered_groups']=await page.evaluate('''()=>{
          const groups=new Map();
          for(const e of document.querySelectorAll('article,tr,li')){
            const p=e.parentElement;if(!groups.has(p))groups.set(p,[]);groups.get(p).push(e);
          }
          let changed=0;
          for(const [p,items] of groups)if(items.length>1){p.insertBefore(items.at(-1),items[0]);changed++;}
          return changed;
        }''')
        after=await bs.get_browser_state_summary(include_screenshot=False)
        action_type=Tools().registry.create_action_model()
        for entry,original,binding,historic,idx,backend_id in held:
            try:
                action=action_type.model_validate({'click':{'index':idx}})
                updated=await Agent._update_action_indices(SimpleNamespace(logger=logging.getLogger('native_match')),historic,action,after)
                matched=after.dom_state.selector_map.get(updated.get_index()) if updated else None
                entry['native_resolved']=matched is not None
                entry['native_same_node']=matched.backend_node_id==backend_id if matched else False
                entry['reference_node_still_visible']=bool(original and await original.is_visible())
                if binding:
                    selected,resolution=await binding.resolve(page)
                    entry['resolution']=resolution
                    entry['candidate_same_node']=bool(selected and await selected.evaluate('(e,original)=>e===original',original))
                    if selected:await selected.dispose()
            except Exception as exc:  # noqa: BLE001 -- every failure retained
                entry['resolution_error']=type(exc).__name__+': '+str(exc)
            finally:
                if original:await original.dispose()
            row['nodes'].append(entry)
        row['status']='completed'
    except Exception as exc:  # noqa: BLE001 -- all fourteen sites/conditions
        row.update(status='error',error=type(exc).__name__+': '+str(exc))
    finally:
        await context.close()
    return row


async def main(output):
    output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'artifacts/benchmarks/outcome-v1/manifest.json').read_text())
    files=[Path(__file__),ROOT/'python/deltadom/binding.py',ROOT/'python/deltadom/binding.js']
    for f in files:(output/f.name).write_bytes(f.read_bytes())
    rows=[]
    async with async_playwright() as p:
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        browser=await p.chromium.launch(channel='chrome',args=[f'--remote-debugging-port={port}'])
        bs=BrowserSession(cdp_url=f'http://127.0.0.1:{port}',keep_alive=True,enable_default_extensions=False)
        await bs.start()
        try:
            for task in manifest['confirmation']:
                for condition in manifest['conditions']:
                    row=await cell(browser,bs,task,condition,manifest)
                    rows.append(row)
                    with (output/'rows.jsonl').open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                    print(task['env'],condition,row['status'],len(row['nodes']),flush=True)
        finally:
            await bs.stop();await browser.close()
    nodes=[n for r in rows for n in r['nodes']]
    summary={'cells':len(rows),'completed':sum(r['status']=='completed' for r in rows),'native_nodes':len(nodes),
             'captured':sum(n.get('capture',{}).get('status')=='bound' for n in nodes),
             'candidate_same_node':sum(n.get('candidate_same_node',False) for n in nodes),
             'candidate_wrong_node':sum(n.get('resolution',{}).get('status')=='resolved' and not n.get('candidate_same_node',False) for n in nodes),
             'native_same_node':sum(n.get('native_same_node',False) for n in nodes),
             'native_wrong_node':sum(n.get('native_resolved',False) and not n.get('native_same_node',False) for n in nodes)}
    (output/'result.json').write_text(json.dumps({'scope':'read-only identity/coverage audit after controlled DOM reorder, not task/model scores',
        'upstream':manifest['upstream'],'seed':manifest['seed'],'sources':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        'summary':summary,'rows':rows},indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    asyncio.run(main(parser.parse_args().output))
