import pytest
from deltadom.binding import ActionBinding
from deltadom.dispatch import guarded_click

HTML='''<main><article><a href="/A">Record A</a><button>Approve</button></article>
<article><a href="/B">Record B</a><button>Approve</button></article></main>
<script>window.effects=[];document.addEventListener('click',e=>{
 if(e.target.tagName==='BUTTON')window.effects.push(e.target.closest('article').querySelector('a').getAttribute('href'));
});</script>'''


async def setup(page):
    await page.route('http://gate.test/**',lambda r:r.fulfill(content_type='text/html',body=HTML))
    await page.goto('http://gate.test/list')
    binding,_=await ActionBinding.capture(page.get_by_role('button').first)
    return binding


async def test_guard_preserves_real_click_and_removes_itself(live):
    page,_=live
    binding=await setup(page)
    receipt=await guarded_click(binding,page)
    assert receipt['status']=='clicked'
    assert await page.evaluate('window.effects')==['/A']
    assert all(e['trusted'] for e in receipt['events'])
    assert await page.evaluate('window.__deltadomActiveDispatch===undefined')


@pytest.mark.parametrize('event,where',[
    ('pointermove','target'),('pointerdown','target'),('click','document'),
])
async def test_changed_identity_is_checked_during_input_propagation(live,event,where):
    page,_=live
    binding=await setup(page)
    await page.evaluate('''({event,where})=>{
      const target=document.querySelector('button');
      (where==='target'?target:document).addEventListener(event,()=>{
        const a=target.closest('article').querySelector('a');a.href='/Z';a.textContent='Record Z';
      },true);
    }''',{'event':event,'where':where})
    receipt=await guarded_click(binding,page)
    assert receipt['status']=='blocked'
    assert await page.evaluate('window.effects')==[]
    assert await page.evaluate('window.__deltadomActiveDispatch===undefined')


async def test_timeout_is_not_retried_and_guard_is_removed(live):
    page,_=live
    binding=await setup(page)
    await page.get_by_role('button').first.evaluate('e=>e.disabled=true')
    receipt=await guarded_click(binding,page,timeout_ms=100)
    assert receipt['status']=='uncertain'
    assert await page.evaluate('window.effects')==[]
    assert await page.evaluate('window.__deltadomActiveDispatch===undefined')


async def test_visual_picker_blocks_selection_then_saved_binding_replays(live):
    from deltadom.binding_cli import install_picker
    page,_=live
    await setup(page)
    captures=[]

    async def receive(result):captures.append(result)

    await install_picker(page,receive)
    await page.get_by_role('button').first.click(modifiers=['Alt'])
    await page.wait_for_timeout(30)
    assert len(captures)==1 and captures[0]['status']=='bound'
    assert await page.evaluate('window.effects')==[]
    binding=ActionBinding.from_json(ActionBinding(captures[0]['binding']).to_json())
    assert (await guarded_click(binding,page))['status']=='clicked'
    assert await page.evaluate('window.effects')==['/A']
