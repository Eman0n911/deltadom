// Visible relational identity; no hidden attributes, absolute DOM path or ordinal fallback.
({mode, target, binding}) => {
  const visible = e => e instanceof Element && e.checkVisibility({checkVisibilityCSS:true,checkOpacity:true});
  const normalize = s => (s || '').replace(/\s+/g,' ').trim();
  const name = e => {
    if (e.hasAttribute('aria-labelledby'))
      return normalize(e.getAttribute('aria-labelledby').split(/\s+/).map(id=>document.getElementById(id)?.innerText || '').join(' '));
    if (e.hasAttribute('aria-label')) return normalize(e.getAttribute('aria-label'));
    if (e.labels?.length) return normalize([...e.labels].map(l=>l.innerText).join(' '));
    if (e.matches('input[type=button],input[type=submit],input[type=reset]')) return normalize(e.value);
    if (e.matches('input,textarea,select')) return '';
    return normalize(e.innerText);
  };
  const descriptor = e => ({tag:e.tagName.toLowerCase(), role:e.getAttribute('role') || '',
                            type:e.getAttribute('type') || '', name:name(e)});
  const controls = [...document.querySelectorAll('button,input:not([type=hidden]),textarea,select,a[href],[role=button],[role=checkbox],[role=switch]')].filter(visible);
  const same = (e,d) => JSON.stringify(descriptor(e)) === JSON.stringify(d);
  const link = e => ({url:e.href,name:normalize(e.innerText)});
  const links = root => [...root.querySelectorAll('a[href]')].filter(e=>visible(e) && normalize(e.innerText) && /^https?:$/.test(new URL(e.href).protocol));
  const key = a => JSON.stringify(a);
  const allLinks = links(document);
  const distinct = anchors => [...new Map(anchors.map(a=>[key(a),a])).values()].sort((a,b)=>key(a).localeCompare(key(b)));
  const contains = (root,anchors) => {
    const present = new Set(links(root).map(e=>key(link(e))));
    return anchors.every(a=>present.has(key(a)));
  };
  if (mode === 'capture') {
    if (!visible(target) || !controls.includes(target)) return {status:'unsupported',reason:'not_supported_visible_control'};
    const d = descriptor(target);
    if (!d.name) return {status:'unsupported',reason:'no_supported_accessible_name'};
    const peers = controls.filter(e=>same(e,d));
    for (let root=target.parentElement;root && root!==document.body;root=root.parentElement) {
      if (peers.filter(e=>root.contains(e)).length !== 1) continue;
      const anchors = distinct(links(root).filter(a => {
        const identity=key(link(a));
        return allLinks.filter(b=>key(link(b))===identity).every(b=>root.contains(b));
      }).map(link));
      if (anchors.length) return {status:'bound',binding:{version:1,document_url:location.href,
        target:d,anchors,mode:'relational'},scope_tag:root.tagName.toLowerCase()};
    }
    if (peers.length===1) return {status:'bound',binding:{version:1,document_url:location.href,
      target:d,anchors:[],mode:'unique_control'}};
    return {status:'unsupported',reason:'no_distinguishing_visible_identity',candidate_count:peers.length};
  }
  if (mode === 'resolve') {
    if (binding.version!==1 || binding.document_url!==location.href) return {status:'unresolved',reason:'document_changed',element:null};
    const peers = controls.filter(e=>same(e,binding.target));
    const candidates = binding.mode==='unique_control' ? peers : peers.filter(e=>{
      for (let root=e.parentElement;root && root!==document.body;root=root.parentElement) {
        if (peers.filter(p=>root.contains(p)).length===1 && contains(root,binding.anchors)) return true;
      }
      return false;
    });
    if (candidates.length!==1) return {status:'unresolved',reason:candidates.length?'ambiguous_identity':'identity_not_found',candidate_count:candidates.length,element:null};
    return {status:'resolved',candidate_count:1,element:candidates[0]};
  }
  throw Error('unsupported binding operation');
}
