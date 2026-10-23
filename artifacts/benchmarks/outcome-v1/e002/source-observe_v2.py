"""Frozen, zero-model observation pilot. See PROTOCOL-v2.md for comparison limits."""
import argparse
import asyncio
import functools
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version

os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['BROWSER_USE_CLOUD_SYNC'] = 'false'
os.environ['BROWSER_USE_LOGGING_LEVEL'] = 'error'

from browser_use import BrowserSession
from browser_use.dom.service import DomService
from deltadom import DeltaBrowser, StateMirror, TextMirror
from deltadom.demo import fixture_server
from playwright.async_api import async_playwright
import tiktoken

ROOT = Path(__file__).resolve().parents[1]
ARMS = ['deltadom-delta', 'deltadom-full', 'browser-use', 'agent-browser-full', 'agent-browser-delta', 'playwright-aria']
CASES = ['enter-text', 'login-user', 'click-checkboxes', 'email-inbox', 'local-shop']
SEEDS = [11, 22, 33]


@contextmanager
def serve_miniwob():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    handler = functools.partial(Quiet, directory=ROOT / '.bench/miniwob/miniwob/html')
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def init_mini(page, seed):
    await page.evaluate('''seed => {
      Math.seedrandom(String(seed)); core.startEpisodeReal();
      clearTimeout(core.EP_TIMER); core.EP_TIMER = null; core.clearTimer();
    }''', seed)


async def fingerprint(page):
    state = await page.evaluate('''() => ({html:document.body.innerHTML,
      values:[...document.querySelectorAll('input,select,textarea')].map(e=>[e.id,e.value,e.checked])})''')
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def steps(case):
    if case == 'local-shop':
        return [('initial', None), ('unchanged', None), ('fill', ('fill', '[name=query]', 'Rust')),
                ('api', ('click', '#load')), ('reorder', ('click', '#sort')),
                ('choose', ('click', 'button[data-product="7"]')), ('add', ('click', '#add')),
                ('reload', ('reload',))]
    actions = {
        'enter-password': [('fill', '#password', 'sample123'), ('fill', '#verify', 'sample123')],
        'click-tab': [('click', 'a[href="#tabs-2"]'), ('click', 'a[href="#tabs-1"]')],
        'click-option': [('check', '#ch0'), ('check', '#ch1')],
        'enter-text': [('fill', '#tt', 'Alice'), ('fill', '#tt', 'Bob')],
        'login-user': [('fill', '#username', 'alice'), ('fill', '#password', 'sample123')],
        'click-checkboxes': [('check', '#ch0'), ('uncheck', '#ch0')],
        'email-inbox': [('click', '#main .email-thread >> nth=0'), ('click', '#close-email')],
    }[case]
    return [('initial', None), ('unchanged', None), ('mutation1', actions[0]),
            ('mutation2', actions[1]), ('unchanged_after', None), ('reload', ('reload',))]


async def cli(session, port, *args):
    proc = await asyncio.create_subprocess_exec(
        str(ROOT / '.bench/node/node_modules/.bin/agent-browser'),
        '--session', session, '--cdp', str(port), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, 'AGENT_BROWSER_NAMESPACE': 'deltadom-pilot',
             'AGENT_BROWSER_CONFIG': str(ROOT / 'benchmarks/agent-browser.json')},
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 30)
    except BaseException:
        proc.kill()
        await proc.communicate()
        raise
    if proc.returncode:
        raise RuntimeError(f'agent-browser exit {proc.returncode}: {err.decode()} {out.decode()}')
    return out.decode(), err.decode()


async def run_case(browser, port, url, case, seed, outdir, encoder, rows):
    page = await browser.new_page(viewport={'width': 1280, 'height': 900})
    await page.goto(url, wait_until='load')
    if case != 'local-shop':
        await init_mini(page, seed)
    bs = BrowserSession(cdp_url=f'http://127.0.0.1:{port}', keep_alive=True,
                        enable_default_extensions=False)
    await bs.start()
    cdp = await page.context.new_cdp_session(page)
    bs.agent_focus_target_id = (await cdp.send('Target.getTargetInfo'))['targetInfo']['targetId']
    dom = DomService(bs)
    previous = None
    deltas = {arm: DeltaBrowser(page) for arm in ARMS[:2]}
    mirrors = {arm: StateMirror() for arm in deltas}
    text_mirrors = {arm: TextMirror() for arm in deltas}
    sessions = {arm: f'dd-{seed}-{case}-{arm.rsplit("-",1)[-1]}' for arm in ARMS[3:5]}
    for session in sessions.values():
        # Connection/daemon startup outside measured capture, no snapshot warming.
        await cli(session, port, 'get', 'url')
    case_steps = steps(case)
    try:
        for step_idx, (label, action) in enumerate(case_steps):
            if action:
                kind, *args = action
                if kind == 'reload':
                    await page.reload(wait_until='load')
                    if case != 'local-shop':
                        await init_mini(page, seed)
                else:
                    await getattr(page.locator(args[0]), kind)(*args[1:])
                    if label == 'api':
                        await page.get_by_text('Loaded 2 API records', exact=True).wait_for()
            before = await fingerprint(page)
            instruction = await page.locator('#query').inner_text() if case != 'local-shop' else ''
            order = ARMS.copy()
            random.Random(seed * 100 + step_idx).shuffle(order)
            for arm in order:
                record = {'seed': seed, 'case': case, 'step': label, 'arm': arm,
                          'order': order.index(arm), 'status': 'ok', 'page_before': before}
                start = time.perf_counter()
                try:
                    if arm in deltas:
                        obs = await deltas[arm].observe(force_full=arm.endswith('full'))
                        text = obs.frame['text']
                        elapsed = (time.perf_counter()-start)*1000
                        assert mirrors[arm].apply(obs.frame) == list(obs.nodes)
                        assert text_mirrors[arm].apply(obs.frame['text']) == list(obs.nodes)
                        record['text_reconstruction_equal']=True
                        record.update(frame_kind=obs.frame['kind'], reconstruction_equal=True,
                                      node_count=len(obs.nodes), timings_ms=obs.timings_ms,
                                      settle=obs.settle, warnings=obs.warnings,
                                      complete_observation_tokens=len(encoder.encode(obs.text, disallowed_special=())))
                        if step_idx+1 < len(case_steps):
                            next_action=case_steps[step_idx+1][1]
                            if next_action and next_action[0] != 'reload':
                                target_id=await page.locator(next_action[1]).evaluate('(el,key)=>window[key].ids.get(el)', deltas[arm]._key)
                                target=next((n for n in obs.nodes if n['id']==target_id), None)
                                record['next_script_target']={'selector':next_action[1], 'captured':target is not None,
                                                             'interactive': bool(target and target['interactive'])}
                        (outdir/f'{seed}-{case}-{step_idx}-{arm}.json').write_text(json.dumps(obs.frame, ensure_ascii=False),encoding='utf-8')
                    elif arm == 'browser-use':
                        previous, _, timing = await dom.get_serialized_dom_tree(previous)
                        text = previous.llm_representation()
                        elapsed = (time.perf_counter()-start)*1000
                        record.update(timings_ms=timing, target_count=len(previous.selector_map))
                    elif arm.startswith('agent-browser'):
                        text, stderr = await cli(sessions[arm], port, 'snapshot', *(['--delta'] if arm.endswith('delta') else []))
                        elapsed = (time.perf_counter()-start)*1000
                        record['stderr'] = stderr
                        record['frame_kind'] = 'unchanged' if text.startswith('unchanged') else 'native'
                    else:
                        text = await page.locator('body').aria_snapshot()
                        elapsed = (time.perf_counter()-start)*1000
                    record.update(wall_ms=elapsed, bytes=len(text.encode('utf-8')),
                                  tokens=len(encoder.encode(text, disallowed_special=())), instruction=instruction)
                    name=f'{seed}-{case}-{step_idx}-{arm}.txt'
                    (outdir/name).write_text(text, encoding='utf-8')
                    record['raw'] = name
                except Exception as exc:
                    record.update(status='error', error=f'{type(exc).__name__}: {exc}', wall_ms=(time.perf_counter()-start)*1000)
                record['page_after']=await fingerprint(page)
                record['page_unchanged']=record['page_after']==before
                rows.append(record)
                with (outdir/'rows.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(record,ensure_ascii=False)+'\n')
            print(f'block={seed} {case}/{label}: {len(rows)} captures',flush=True)
        await page.screenshot(path=str(outdir/f'{seed}-{case}.png'))
    finally:
        for delta in deltas.values():
            await delta.close()
        await bs.stop()
        for session in sessions.values():
            await cli(session, port, 'close')
        if not page.is_closed():
            await page.close()


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/benchmarks/observation-v1')
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--holdout',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    encoder=tiktoken.get_encoding('cl100k_base')
    encoder.encode('warm tokenizer')
    metadata={'scope':'observation replay, NOT native MiniWoB success',
              'packages':{p:version(p) for p in ['browser-use','deltadom','playwright','tiktoken']},
              'python':platform.python_version(),'platform':platform.platform(),
              'miniwob_sha':subprocess.check_output(['git','-C',str(ROOT/'.bench/miniwob'),'rev-parse','HEAD'],text=True).strip(),
              'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol_sha256':hashlib.sha256((ROOT/'benchmarks/PROTOCOL-v2.md').read_bytes()).hexdigest(),
              'wheel_sha256':hashlib.sha256((ROOT/'dist/deltadom-0.3.0-cp312-abi3-macosx_11_0_arm64.whl').read_bytes()).hexdigest(),
              'agent_browser_version':json.loads((ROOT/'.bench/node/node_modules/agent-browser/package.json').read_text())['version'],
              'seeds':([44,55,66] if args.holdout else SEEDS) if not args.smoke else [11], 'cases':(['enter-password','click-tab','click-option'] if args.holdout else CASES) if not args.smoke else ['enter-text']}
    metadata['scope']='holdout observation replay' if args.holdout else 'development observation replay'
    metadata['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['src','python/deltadom'] for p in (ROOT/folder).iterdir() if p.suffix in ['.rs','.py','.js']}
    rows=[]
    with serve_miniwob() as base, fixture_server() as shop:
        async with async_playwright() as p:
            for seed in metadata['seeds']:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                browser=await p.chromium.launch(channel='chrome', args=[f'--remote-debugging-port={port}'])
                metadata['chrome']=browser.version
                try:
                    for case in metadata['cases']:
                        url=shop if case=='local-shop' else f'{base}/miniwob/{case}.html'
                        await run_case(browser,port,url,case,seed,args.output,encoder,rows)
                finally:
                    await browser.close()
    metadata.update(rows=len(rows),errors=sum(r['status']!='ok' for r in rows),
                    mutated_during_capture=sum(not r['page_unchanged'] for r in rows),
                    not_run=['model tasks','official score','paid cost','full prompt tokens','native action comparison'])
    (args.output/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':
    asyncio.run(main())
