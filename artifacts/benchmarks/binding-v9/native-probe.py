import os
os.environ['ANONYMIZED_TELEMETRY']='false'
os.environ['BROWSER_USE_LOGGING_LEVEL']='error'
import asyncio,socket,json,logging
from types import SimpleNamespace
from playwright.async_api import async_playwright
from browser_use import BrowserSession,Tools,Agent
from browser_use.dom.views import DOMInteractedElement
async def main():
 async with async_playwright() as p:
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  b=await p.chromium.launch(channel='chrome',args=[f'--remote-debugging-port={port}'])
  c=await b.new_context(); page=await c.new_page()
  html=('<main><article><a href="/record/A">Invoice A</a><button>Approve</button></article><article><a href="/record/B">Invoice B</a><button>Approve</button></article></main><script>window.clicked=[];document.addEventListener("click",e=>{if(e.target.tagName==="BUTTON")window.clicked.push(e.target.parentElement.querySelector("a").textContent)})</script>')
  await c.route("http://replay.test/**", lambda route:route.fulfill(content_type="text/html",body=html))
  await page.goto("http://replay.test/list")
  bs=BrowserSession(cdp_url=f'http://127.0.0.1:{port}',keep_alive=True,enable_default_extensions=False);await bs.start()
  cd=await c.new_cdp_session(page);bs.agent_focus_target_id=(await cd.send('Target.getTargetInfo'))['targetInfo']['targetId']
  try:
   before=await bs.get_browser_state_summary(include_screenshot=False)
   buttons=[(i,n) for i,n in before.dom_state.selector_map.items() if n.node_name.lower()=='button']
   print('before',[(i,n.xpath,n.element_hash,n.ax_node.name) for i,n in buttons])
   idx,node=buttons[0];hist=DOMInteractedElement.load_from_enhanced_dom_tree(node)
   await page.evaluate('document.querySelector("main").prepend(document.querySelectorAll("article")[1])')
   after=await bs.get_browser_state_summary(include_screenshot=False)
   ts=Tools(); cls=ts.registry.create_action_model(); action=cls.model_validate({'click':{'index':idx}})
   matched=await Agent._update_action_indices(SimpleNamespace(logger=logging.getLogger('probe')),hist,action,after)
   print('match',matched.model_dump(exclude_none=True))
   res=await ts.act(matched,browser_session=bs)
   print(json.dumps({'clicked':await page.evaluate('window.clicked'),'action_result':res.model_dump(exclude_none=True)}))
  finally:await bs.stop();await b.close()
asyncio.run(main())
