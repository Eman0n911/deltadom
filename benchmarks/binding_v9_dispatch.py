"""Frozen trusted-input race matrix, including strong atomic simple control."""
import argparse
import asyncio
import hashlib
import json
import socket
from pathlib import Path

from deltadom.binding import ActionBinding
from deltadom.dispatch import guarded_click
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
CASES=['unchanged','remount','reorder','duplicate','removed','hover_recycle',
       'pointerdown_recycle','ancestor_click_recycle','window_click_recycle',
       'pointerdown_write','hidden_handler']
ARMS=['manual_locator','manual_precheck','atomic_dom','binding','dispatch_guard']
HTML='''<style>article{display:flex;gap:40px;margin:30px}button{width:130px;height:40px}</style>
<main><article><a href="/A">Record A</a><button>Approve</button></article>
<article><a href="/B">Record B</a><button>Approve</button></article></main>
<script>
window.effects=[];
const target=document.querySelector('button');
const change=()=>{const a=target.closest('article').querySelector('a');a.href='/Z';a.textContent='Record Z'};
const effect=e=>window.effects.push({record:window.hidden?'Z':e.target.closest('article').querySelector('a').getAttribute('href').slice(1),trusted:e.isTrusted,event:e.type});
const scenario=CASE;
if(scenario==='hover_recycle')target.addEventListener('pointermove',change,{once:true});
if(scenario==='pointerdown_recycle')target.addEventListener('pointerdown',change,{once:true});
if(scenario==='ancestor_click_recycle')document.addEventListener('click',change,true);
if(scenario==='window_click_recycle')window.addEventListener('click',change,true);
if(scenario==='pointerdown_write')target.addEventListener('pointerdown',e=>{change();effect(e)},{once:true});
document.addEventListener('click',e=>{if(e.target.tagName==='BUTTON' && (!TRUST || e.isTrusted))effect(e)});
</script>'''


def manual(page):
    link=page.get_by_role('link',name='Record A',exact=True).and_(page.locator('a[href="/A"]'))
    return page.get_by_role('article').filter(has=link).get_by_role('button',name='Approve',exact=True)


async def cell(browser,case,trust,arm,browser_url=None):
    context=await browser.new_context();page=await context.new_page()
    html=HTML.replace('CASE',json.dumps(case)).replace('TRUST',str(trust).lower())
    await page.route('http://dispatch.test/**',lambda r:r.fulfill(content_type='text/html',body=html))
    await page.goto('http://dispatch.test/list')
    row={'case':case,'trusted_required':trust,'arm':arm}
    bs=None
    try:
        binding,capture=await ActionBinding.capture(manual(page))
        row['capture']=capture
        if arm=='native_tools':
            from browser_use import BrowserSession, Tools
            bs=BrowserSession(cdp_url=browser_url,keep_alive=True,enable_default_extensions=False)
            await bs.start()
            cdp=await context.new_cdp_session(page)
            bs.agent_focus_target_id=(await cdp.send('Target.getTargetInfo'))['targetInfo']['targetId']
            snapshot=await bs.get_browser_state_summary(include_screenshot=False)
            idx=next(i for i,n in snapshot.dom_state.selector_map.items() if n.node_name.upper()=='BUTTON')
        if case=='remount':await page.locator('article').first.evaluate('e=>e.replaceWith(e.cloneNode(true))')
        if case=='reorder':await page.evaluate('document.querySelector("main").prepend(document.querySelectorAll("article")[1])')
        if case=='duplicate':await page.evaluate('document.querySelector("main").append(document.querySelector("article").cloneNode(true))')
        if case=='removed':await page.locator('article').first.evaluate('e=>e.remove()')
        if case=='hidden_handler':await page.evaluate('window.hidden=true')
        error=None
        try:
            if arm=='native_tools':
                tools=Tools();action=tools.registry.create_action_model().model_validate({'click':{'index':idx}})
                result=(await tools.act(action,browser_session=bs)).model_dump(exclude_none=True)
            elif arm in {'manual_locator','manual_precheck'}:
                locator=manual(page)
                if arm=='manual_precheck':
                    if await locator.count()!=1:raise ValueError('ambiguous or missing target')
                    assert await locator.evaluate('e=>e.closest("article").querySelector("a").textContent')=='Record A'
                await locator.click(timeout=750)
                result={'status':'clicked'}
            elif arm=='atomic_dom':
                result=await page.evaluate('''()=>{
                  const targets=[...document.querySelectorAll('article')].filter(r=>{
                    const a=r.querySelector('a');return a?.getAttribute('href')==='/A' && a.textContent==='Record A';
                  }).flatMap(r=>[...r.querySelectorAll('button')].filter(e=>e.innerText==='Approve'));
                  if(targets.length!==1)return {status:'unresolved'};
                  targets[0].click();return {status:'clicked'};
                }''')
            elif arm=='binding':result=await binding.click(page,timeout_ms=750)
            else:result=await guarded_click(binding,page,timeout_ms=750)
            row['result']=result
        except Exception as exc:  # noqa: BLE001 -- retain failed arms
            error=type(exc).__name__+': '+str(exc)
        effects=await page.evaluate('window.effects')
        correct=bool(effects) and len(effects)==1 and effects[0]['record']=='A'
        ordinary=case in {'unchanged','remount','reorder'}
        row.update(status='completed',error=error,effects=effects,correct_effect=correct,
                   wrong_effect=bool(effects) and not correct,false_refusal=ordinary and not effects,
                   refusal=not effects)
    finally:
        if bs:await bs.stop()
        await context.close()
    return row


async def main(output,arms=None):
    output.mkdir(parents=True,exist_ok=False)
    arms=arms or ARMS
    files=[Path(__file__),ROOT/'python/deltadom/binding.py',ROOT/'python/deltadom/binding.js',ROOT/'python/deltadom/dispatch.py']
    sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    for f in files:(output/f.name).write_bytes(f.read_bytes())
    rows=[]
    async with async_playwright() as p:
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        browser=await p.chromium.launch(channel='chrome',args=[f'--remote-debugging-port={port}'])
        try:
            for trust in [False,True]:
                for case in CASES:
                    for arm in arms:
                        try:row=await cell(browser,case,trust,arm,f'http://127.0.0.1:{port}')
                        except Exception as exc:row={'case':case,'trusted_required':trust,'arm':arm,'status':'harness_error','error':str(exc)}  # noqa: BLE001
                        rows.append(row)
                        with (output/'rows.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
                        print(trust,case,arm,row.get('correct_effect'),row.get('wrong_effect'),flush=True)
        finally:await browser.close()
    summary={str(trust):{arm:{k:sum(bool(r.get(k)) for r in rows if r['arm']==arm and r['trusted_required']==trust)
              for k in ['correct_effect','wrong_effect','false_refusal','refusal']} for arm in arms} for trust in [False,True]}
    (output/'result.json').write_text(json.dumps({'scope':'synthetic dispatch component, not autonomous task scores','sources':sources,'summary':summary,'rows':rows},indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--arms',nargs='+',choices=[*ARMS,'native_tools'])
    args=p.parse_args()
    asyncio.run(main(args.output,args.arms))
