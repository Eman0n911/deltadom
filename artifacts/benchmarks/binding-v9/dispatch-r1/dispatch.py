"""Visible identity guard at trusted input dispatch, not a server transaction.

The guard runs in window capture listeners. It cannot undo earlier window
listeners, side effects in previous events, or hidden handler semantics.
"""
import uuid

from .binding import SCRIPT, ActionBinding

_INSTALL = r'''({key,binding})=>{
  if (window.__deltadomActiveDispatch) return {status:'busy'};
  const resolve = RESOLVER;
  const state = {events:[],blocked:false,reason:null};
  const types = ['pointerdown','mousedown','pointerup','mouseup','click','auxclick','dblclick'];
  const handler = event=>{
    const live = resolve({mode:'resolve',binding});
    const targetMatches = live.element && (event.target===live.element || live.element.contains(event.target));
    const valid = !state.blocked && event.isTrusted && targetMatches;
    state.events.push({type:event.type,trusted:event.isTrusted,valid:!!valid});
    if (!valid) {
      state.blocked = true;
      state.reason ||= live.reason || (event.isTrusted?'event_target_changed':'untrusted_event');
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  };
  for (const type of types) window.addEventListener(type,handler,{capture:true,passive:false});
  window.__deltadomActiveDispatch={key,state,remove:()=>{
    for (const type of types) window.removeEventListener(type,handler,true);
  }};
  return {status:'installed'};
}'''.replace('RESOLVER', SCRIPT)

_REMOVE = r'''key=>{
  const guard=window.__deltadomActiveDispatch;
  if (!guard || guard.key!==key) return null;
  guard.remove();
  delete window.__deltadomActiveDispatch;
  return guard.state;
}'''


async def guarded_click(binding: ActionBinding, page, *, timeout_ms=1000):
    """Send one physical click, stopping changed visible identities at dispatch.

    This observes and guards input, not the resulting business operation. It does
    not retry. Concurrent guarded clicks on one page are rejected, not queued.
    """
    element, receipt = await binding.resolve(page)
    if element is None:
        return receipt
    key = uuid.uuid4().hex
    installed = False
    error = None
    state = None
    try:
        setup = await page.evaluate(_INSTALL, {'key':key,'binding':binding.data})
        if setup['status'] != 'installed':
            return {'status':'unresolved','reason':'another_dispatch_in_progress'}
        installed = True
        try:
            await element.click(timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001 -- never retry a possibly delivered click
            error = type(exc).__name__ + ': ' + str(exc)
    finally:
        await element.dispose()
        if installed:
            try:
                state = await page.evaluate(_REMOVE,key)
            except Exception as exc:  # noqa: BLE001 -- navigation can destroy the old document
                error = error or type(exc).__name__ + ': ' + str(exc)
    if state is None:
        return {'status':'uncertain','reason':'dispatch_receipt_unavailable','error':error}
    if state['blocked']:
        return {'status':'blocked','reason':state['reason'],'events':state['events'],'error':error,
                'scope':'input blocked; earlier listener side effects cannot be undone'}
    clicked = any(e['type']=='click' and e['valid'] for e in state['events'])
    return {'status':'clicked' if clicked else 'uncertain','events':state['events'],'error':error,
            'scope':'trusted UI input only; outcome not verified'}
