import json

import pytest
from deltadom.binding import ActionBinding

HTML = '''<main><p>Unrelated</p><article><a href="/A">Record A</a><button>Mark</button></article>
<article><a href="/B">Record B</a><button>Mark</button></article></main>'''


async def setup(page):
    await page.route('http://binding.test/**', lambda r:r.fulfill(content_type='text/html',body=HTML))
    await page.goto('http://binding.test/list')
    return await ActionBinding.capture(page.get_by_role('button').first)


async def test_binding_survives_reorder_remount_wrapper_and_serialization(live):
    page,_=live
    binding,receipt=await setup(page)
    assert receipt['status']=='bound' and binding.data['mode']=='relational'
    assert binding.data['anchors']==[{'url':'http://binding.test/A','name':'Record A'}]
    binding=ActionBinding.from_json(binding.to_json())
    await page.evaluate('''()=>{let a=document.querySelector('article');a.replaceWith(a.cloneNode(true));
    document.querySelector('main').prepend(document.querySelectorAll('article')[1]);
    let b=document.querySelectorAll('button')[1], d=document.createElement('div');b.replaceWith(d);d.append(b);}''')
    element,result=await binding.resolve(page)
    assert result['status']=='resolved'
    assert await element.evaluate('e=>e.closest("article").querySelector("a").textContent')=='Record A'
    await element.dispose()
    await page.evaluate('document.querySelector("p").textContent="new unrelated text"')
    assert (await binding.click(page))['status']=='clicked'


@pytest.mark.parametrize('change',[
    'document.querySelector("article").remove()',
    'document.querySelector("article a").href="/different"',
    'document.querySelector("article a").textContent="different"',
    'document.querySelector("main").append(document.querySelector("article").cloneNode(true))',
])
async def test_binding_never_falls_back_to_position_or_first_duplicate(live,change):
    page,_=live
    binding,_=await setup(page)
    await page.evaluate(change)
    element,result=await binding.resolve(page)
    assert element is None and result['status']=='unresolved'


async def test_unsupported_and_unique_control_are_explicit(live):
    page,_=live
    await page.set_content('<main><button>Mark</button><button>Mark</button></main>')
    binding,result=await ActionBinding.capture(page.get_by_role('button').first)
    assert binding is None and result['reason']=='no_distinguishing_visible_identity'
    await page.set_content('<main><button>Continue</button></main>')
    binding,_=await ActionBinding.capture(page.get_by_role('button'))
    assert binding.data['mode']=='unique_control'
    await page.evaluate('document.querySelector("main").append(document.querySelector("button").cloneNode(true))')
    element,result=await binding.resolve(page)
    assert element is None and result['reason']=='ambiguous_identity'


async def test_two_plausible_context_links_not_arbitrarily_discarded(live):
    page,_=live
    await setup(page)
    await page.locator('article').first.evaluate('e=>e.insertAdjacentHTML("afterbegin",\'<a href="/owner/1">Owner</a>\')')
    binding,_=await ActionBinding.capture(page.get_by_role('button').first)
    assert len(binding.data['anchors'])==2
    await page.locator('a[href="/A"]').evaluate('e=>e.href="/B"')
    element,_result=await binding.resolve(page)
    assert element is None  # Retaining only the owner link would bind the wrong record.
    with pytest.raises(ValueError):
        ActionBinding.from_json(json.dumps({'version':1,'mode':'relational','target':{},'anchors':[],'document_url':'http://x/'}))


async def test_text_witnesses_survive_reorder_but_refuse_changed_record(live):
    page,_=live
    await page.set_content('<main><article><span>Record A</span><button>Mark</button></article>'
                           '<article><span>Record B</span><button>Mark</button></article></main>')
    binding,receipt=await ActionBinding.capture(page.get_by_role('button').first)
    assert receipt['binding']['mode']=='textual'
    binding=ActionBinding.from_json(binding.to_json())
    await page.evaluate('document.querySelector("main").prepend(document.querySelectorAll("article")[1])')
    element,_=await binding.resolve(page)
    assert await element.evaluate('e=>e.closest("article").querySelector("span").innerText')=='Record A'
    await element.dispose()
    await page.get_by_text('Record A',exact=True).evaluate('e=>e.textContent="Record C"')
    assert (await binding.resolve(page))[0] is None


async def test_text_fallback_does_not_guess_which_unique_field_is_stable(live):
    page,_=live
    await page.set_content('<main><article><span>A</span><span>$10</span><button>Mark</button></article>'
                           '<article><span>B</span><span>$20</span><button>Mark</button></article></main>')
    binding,_=await ActionBinding.capture(page.get_by_role('button').first)
    assert set(binding.data['texts'])=={'A','$10'}
    await page.get_by_text('$10',exact=True).evaluate('e=>e.textContent="$11"')
    assert (await binding.resolve(page))[0] is None


async def test_removed_control_does_not_widen_scope_to_another_record(live):
    page,_=live
    binding,_=await setup(page)
    await page.get_by_role('button').first.evaluate('e=>e.remove()')
    element,receipt=await binding.resolve(page)
    assert element is None and receipt['reason']=='identity_not_found'
