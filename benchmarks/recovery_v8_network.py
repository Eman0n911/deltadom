"""Real HTTP/Chrome replay faults. Deliberately includes three non-winning cases."""
import argparse
import asyncio
import hashlib
import json
import socket
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from deltadom.network_fence import NetworkFence
from deltadom.recovery import RecoveryLedger, WriteIntent
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
CASES = ["single", "parallel_identical", "lost_reply_retry", "browser_restart",
         "different_bodies", "equivalent_different_bytes", "legitimate_repeat", "redirect_307"]
ARMS = ["native_playwright", "resource_journal", "memory_request_gate", "durable_request_gate"]


@contextmanager
def server():
    events, counts, lock = [], {}, threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            args = parse_qs(urlsplit(self.path).query)
            mode, sid = args["case"][0], args["sid"][0]
            endpoint = f"/effect?case={mode}&sid={sid}"
            bodies = ['{"item":"A"}']
            if mode == "different_bodies":
                bodies.append('{"item":"B"}')
            elif mode == "equivalent_different_bytes":
                bodies.append('{ "item" : "A" }')
            elif mode in {"parallel_identical", "lost_reply_retry", "legitimate_repeat"}:
                bodies *= 2
            script = f'''
            const bodies={json.dumps(bodies)};
            async function send(body) {{
              try {{ let r=await fetch({json.dumps(endpoint)},{{method:'POST',body}});
                return {{status:r.status,text:await r.text()}};
              }} catch(e) {{return {{error:e.name}};}}
            }}
            async function run() {{
              window.results=[];
              if ({json.dumps(mode)}==='parallel_identical')
                window.results=await Promise.all(bodies.map(send));
              else for(const body of bodies) window.results.push(await send(body));
              document.querySelector('p').textContent=JSON.stringify(window.results);
              window.finished=true;
            }}
            '''
            if "resume" in args:
                script += "run();"
            content = ('<main><button onclick="run()">Submit</button><p>Ready</p></main>'
                       f'<script>{script}</script>').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            args = parse_qs(urlsplit(self.path).query)
            mode, sid = args["case"][0], args["sid"][0]
            body = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
            with lock:
                counts[sid] = counts.get(sid, 0) + 1
                n = counts[sid]
                events.append({"sid": sid, "path": self.path, "body": body, "effect_number": n})
            if mode == "lost_reply_retry" and n == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if mode == "redirect_307" and urlsplit(self.path).path == "/effect":
                self.send_response(307)
                self.send_header('Location', self.path.replace('/effect?', '/redirect-target?'))
                self.end_headers()
                return
            data = b'{"ack":true}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}', events
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class MemoryPermits:
    def __init__(self):
        self.seen = set()

    def admit_forward(self, intent, signature):
        key = (intent.operation_id, signature)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


async def run_cell(browser, origin, events, directory, case, arm):
    sid = case + '-' + arm
    url = origin + f'/?case={case}&sid={sid}'
    path = directory / (sid + '.sqlite')
    intent = WriteIntent(sid, sid, {"one_logical_submit": True})
    store = RecoveryLedger(path)
    decisions, outputs = [], []
    row = {"case": case, "arm": arm, "desired_effects": 2 if case in {
        "different_bodies", "legitimate_repeat"} else 1, "actor_callbacks": 0}

    async def new_context():
        context = await browser.new_context(service_workers="block")
        if arm in {"memory_request_gate", "durable_request_gate"}:
            permits = MemoryPermits() if arm == "memory_request_gate" else RecoveryLedger(path)
            fence = await NetworkFence(context, permits, intent, origin=origin).install()
        else:
            # Routing disables browser cache; match this condition in all four arms.
            await context.route("**/*", lambda route: route.continue_())
            fence = None
        return context, fence

    context, fence = await new_context()
    try:
        page = await context.new_page()
        await page.goto(url)

        async def submit_once():
            row["actor_callbacks"] += 1
            await page.get_by_role('button', name='Submit', exact=True).click()
            await page.wait_for_function('window.finished===true')

        if arm == "native_playwright":
            await submit_once()
        else:
            await store.execute(intent, submit_once)
        outputs.append(await page.evaluate('window.results'))
    finally:
        if fence:
            decisions.extend(fence.decisions)
        await context.close()
    if case == "browser_restart":
        context, fence = await new_context()
        try:
            page = await context.new_page()
            # Resume is page-originated code: no second tool/actor callback.
            await page.goto(url + '&resume=1')
            await page.wait_for_function('window.finished===true')
            outputs.append(await page.evaluate('window.results'))
        finally:
            if fence:
                decisions.extend(fence.decisions)
            await context.close()
    actual = [event for event in events if event["sid"] == sid]
    row.update(server_effects=len(actual), extra_effects=max(0, len(actual)-row["desired_effects"]),
               missing_effects=max(0, row["desired_effects"]-len(actual)),
               correct_effect_count=len(actual) == row["desired_effects"],
               decisions=decisions, UI_results=outputs, server_events=actual, status="completed")
    return row


async def main(output):
    output.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), ROOT / 'python/deltadom/network_fence.py', ROOT / 'python/deltadom/recovery.py']
    for file in files:
        (output / file.name).write_bytes(file.read_bytes())
    rows = []
    with server() as (origin, events), tempfile.TemporaryDirectory() as tmp:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                for case in CASES:
                    for arm in ARMS:
                        try:
                            row = await run_cell(browser, origin, events, Path(tmp), case, arm)
                        except Exception as exc:  # noqa: BLE001 -- retain whole matrix
                            row = {"case": case, "arm": arm, "status": "error", "error": str(exc)}
                        rows.append(row)
                        with (output / 'rows.jsonl').open('a') as stream:
                            stream.write(json.dumps(row) + '\n')
                        print(case, arm, row['status'], row.get('server_effects'), flush=True)
            finally:
                await browser.close()
    summary = {arm: {"cells": sum(r['arm']==arm for r in rows),
                     "correct_effect_counts": sum(r['arm']==arm and r.get('correct_effect_count', False) for r in rows),
                     "extra_effects": sum(r.get('extra_effects', 0) for r in rows if r['arm']==arm),
                     "missing_effects": sum(r.get('missing_effects', 0) for r in rows if r['arm']==arm),
                     "errors": sum(r['arm']==arm and r['status']=='error' for r in rows)} for arm in ARMS}
    (output / 'result.json').write_text(json.dumps({
        "scope": "8 constructed real-browser HTTP cases x4 arms; not BreakingWeb or model/task scores",
        "sources": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        "summary": summary, "rows": rows}, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(main(parser.parse_args().output))
