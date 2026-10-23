"""Pick one visible action in a browser; save and replay its identity locally."""
import asyncio
import json
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .binding import SCRIPT, ActionBinding
from .dispatch import guarded_click
from .runtime import launch_browser

_PICKER = r'''(()=>{
  if (window!==window.top || window.__deltadomPickerInstalled) return;
  window.__deltadomPickerInstalled=true;
  let picking=false;
  const capture=CAPTURE;
  const selector='button,input:not([type=hidden]),textarea,select,a[href],[role=button],[role=checkbox],[role=switch]';
  const handler=event=>{
    if(event.type==='pointerdown' && event.altKey){
      picking=true;
      const target=event.target.closest(selector);
      const result=target?capture({mode:'capture',target}):{status:'unsupported',reason:'not_a_supported_control'};
      window.__deltadomSelected(result);
    }
    if(picking){event.preventDefault();event.stopImmediatePropagation();if(event.type==='click')picking=false;}
  };
  for(const type of ['pointerdown','mousedown','pointerup','mouseup','click'])
    window.addEventListener(type,handler,{capture:true,passive:false});
})()'''.replace('CAPTURE',SCRIPT)


def check_url(url):
    if urlsplit(url).scheme not in {'http','https'}:
        raise ValueError('只支持 http 或 https 网页。')


def save_new_binding(destination, value):
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as stream:
        stream.write(value+'\n')


async def install_picker(page, callback):
    async def selected(source, result):
        if source['frame']==page.main_frame:
            await callback(result)
    await page.expose_binding('__deltadomSelected',selected)
    await page.add_init_script(_PICKER)
    await page.evaluate(_PICKER)


async def pick(url, output, *, channel='auto'):
    check_url(url)
    destination=Path(output)
    if destination.exists():raise ValueError(f'文件已存在，请换一个保存位置：{destination}')
    async with async_playwright() as p:
        browser,_=await launch_browser(p,channel,headless=False)
        page=await browser.new_page()
        selected=asyncio.get_running_loop().create_future()

        async def receive(result):
            if result['status']=='bound' and not selected.done():selected.set_result(result['binding'])
            elif result['status']!='bound':print('暂不能可靠识别这个控件：'+result['reason'],flush=True)

        await install_picker(page,receive)
        def closed():
            if not selected.done():selected.set_exception(ValueError('浏览器已关闭，没有保存目标。'))
        page.on('close',closed)
        try:
            await page.goto(url)
            print('在浏览器中找到目标，按住 Alt（Mac 为 Option）再点击。普通点击可正常浏览。',flush=True)
            print('只保存这一次选取的目标；不录制此前的浏览步骤。',flush=True)
            binding=ActionBinding(await selected)
            await asyncio.to_thread(save_new_binding,destination,binding.to_json())
            print(f'已保存：{destination.resolve()}\n目标：{binding.data["target"]["name"]}',flush=True)
            names=[a['name'] for a in binding.data['anchors']] or binding.data.get('texts',[])
            print('记录依据：'+('；'.join(names) if names else '页面中唯一的同名控件'),flush=True)
        finally:await browser.close()


async def click_file(file, *, channel='auto', headless=False, wait_for_login=False, json_output=False):
    binding=ActionBinding.from_json(Path(file).read_text())
    check_url(binding.data['document_url'])
    if headless and wait_for_login:raise ValueError('后台模式不能等待手动登录。')
    async with async_playwright() as p:
        browser,_=await launch_browser(p,channel,headless=headless)
        page=await browser.new_page()
        try:
            await page.goto(binding.data['document_url'])
            if wait_for_login:
                await asyncio.to_thread(input,'完成登录并返回原页面后，按回车执行一次点击：')
            receipt=await guarded_click(binding,page)
            if headless and receipt['status'] in {'clicked','uncertain'}:
                try:
                    await page.wait_for_load_state('networkidle',timeout=5000)
                    receipt['page_settle']='network_idle; not business confirmation'
                except PlaywrightTimeoutError:
                    receipt['page_settle']='timeout; outstanding activity may remain'
            if json_output:print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)
            else:
                messages={'clicked':'已发出一次点击，业务结果尚未核验。',
                          'blocked':'已拦截后续输入：点击期间目标发生了变化。',
                          'unresolved':'已停止：当前不能唯一识别保存的目标。',
                          'uncertain':'执行状态尚未确认，请先检查页面，不要直接重试。'}
                print(f'目标：{binding.data["target"]["name"]}\n'+messages[receipt['status']],flush=True)
            if not headless:
                await asyncio.to_thread(input,'请在浏览器中核对结果；按回车关闭浏览器。')
            return receipt
        finally:await browser.close()


async def demo(output, *, channel='auto', headless=False, delay=1.0, keep_open=False):
    html=files('deltadom').joinpath('binding-demo.html').read_text()
    rows=[]
    destination=Path(output);destination.parent.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser,_=await launch_browser(p,channel,headless=headless)
        page=await browser.new_page(viewport={'width':960,'height':680})
        await page.route('http://deltadom-demo.test/**',lambda r:r.fulfill(content_type='text/html',body=html))
        try:
            for mode in ['normal','locator_race','guard_race','reorder']:
                await page.goto('http://deltadom-demo.test/records')
                await page.evaluate('mode=>window.setMode(mode)',mode)
                target=page.get_by_role('article').filter(has=page.get_by_role('link',name='记录 A',exact=True)).get_by_role('button',name='标记完成',exact=True)
                binding,_=await ActionBinding.capture(target)
                if mode=='reorder':await page.evaluate('document.querySelector("main").prepend(document.querySelectorAll("article")[1])')
                await page.wait_for_timeout(delay*1000)
                if mode=='locator_race':
                    await target.click();receipt={'status':'clicked'}
                else:receipt=await guarded_click(binding,page)
                effects=await page.evaluate('window.effects')
                expected=effects==(['/Z'] if mode=='locator_race' else [] if mode=='guard_race' else ['/A'])
                rows.append({'case':mode,'receipt':receipt,'effects':effects,'expected_observed':expected})
                await page.locator('#status').evaluate('(e,text)=>e.textContent=text',
                    '已拦截：目标在鼠标移动时变了。' if mode=='guard_race' else '实际操作记录：'+', '.join(effects))
                await page.screenshot(path=str(destination.with_name(destination.stem+'-'+mode+'.png')))
                print(mode,receipt['status'],effects,flush=True)
                await page.wait_for_timeout(delay*1000)
            if keep_open:await asyncio.to_thread(input,'演示结束，按回车关闭浏览器。')
        finally:await browser.close()
    destination.write_text(json.dumps({'scope':'local mechanism demonstration; not benchmark task scores','cases':rows},ensure_ascii=False,indent=2)+'\n')
    if not all(r['expected_observed'] for r in rows):raise ValueError('演示结果与预期不一致，请查看结果文件。')
    print(f'四种行为均已复现，结果：{destination.resolve()}',flush=True)
