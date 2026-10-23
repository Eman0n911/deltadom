"""Installed CLI smoke: one local server write, then refuse a changed identity."""
import argparse
import asyncio
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from deltadom import ActionBinding
from playwright.async_api import async_playwright


async def main(python,output):
    state={'record':'A','writes':[]}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            first=state['record']
            html=f'''<main><article><a href="/{first}">Record {first}</a><button onclick="fetch('/mark/{first}',{{method:'POST'}})">Mark</button></article>
            <article><a href="/B">Record B</a><button onclick="fetch('/mark/B',{{method:'POST'}})">Mark</button></article></main>'''.encode()
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html)
        def do_POST(self):
            state['writes'].append(self.path)
            self.send_response(200);self.end_headers();self.wfile.write(b'OK')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    rows=[]
    try:
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'selected action.json'
            async with async_playwright() as p:
                browser=await p.chromium.launch(channel='chrome');page=await browser.new_page()
                await page.goto(f'http://127.0.0.1:{server.server_port}/records')
                binding,_=await ActionBinding.capture(page.get_by_role('button').first)
                file.write_text(binding.to_json())
                await browser.close()
            for record,expected in [('A',0),('Z',2)]:
                state['record']=record
                result=await asyncio.to_thread(subprocess.run,[python,'-m','deltadom.cli','bound-click',str(file),'--headless','--json','--channel','chrome'],capture_output=True,text=True,timeout=30)
                rows.append({'record':record,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'writes':list(state['writes'])})
                assert result.returncode==expected,rows[-1]
                assert state['writes']==['/mark/A'],rows[-1]
            assert json.loads(rows[0]['stdout'])['status']=='clicked'
            assert json.loads(rows[1]['stdout'])['status']=='unresolved'
    finally:
        server.shutdown();server.server_close();thread.join()
        output.write_text(json.dumps({'scope':'local test server; installed CLI process; not external task score','rows':rows},indent=2)+'\n')
    print('installed CLI: one intended write, changed identity refused')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();asyncio.run(main(args.python,args.output))
