({key, mode = 'capture', documentId, nodeId}) => {
  let state = window[key];
  if (!state) {
    state = {
      // getRandomValues works on HTTP/about:blank too; randomUUID requires a secure context.
      document: btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16)))).replace(/=+$/, ''),
      ids: new WeakMap(), next: 1, current: new Map(),
      lastMutation: performance.now(), observers: new Map()
    };
    const observer = new MutationObserver(() => { state.lastMutation = performance.now(); });
    observer.observe(document, {subtree:true, childList:true, attributes:true, characterData:true});
    state.observers.set(document, observer);
    const changed = () => { state.lastMutation = performance.now(); };
    state.changed = changed;
    // Actions can schedule a delayed DOM/network update without immediately mutating the DOM.
    state.events = ['input','change','click','keydown','pointerup','submit'];
    for(const event of state.events)document.addEventListener(event, changed, true);
    Object.defineProperty(window, key, {value:state, configurable:true});
  }
  if (mode === 'idle') return {document:state.document, idle:performance.now()-state.lastMutation};
  if (mode === 'resolve') {
    const el=state.current.get(nodeId);
    return state.document === documentId && el?.isConnected && el.nodeType === 1 ? el : null;
  }
  if (mode === 'close') {
    for (const ob of state.observers.values()) ob.disconnect();
    for(const event of state.events)document.removeEventListener(event,state.changed,true);
    delete window[key]; return null;
  }
  const ids=state.ids, current=new Map(), warnings=new Set();
  const excluded=new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','HEAD','META','LINK']);
  const roles=new Set(['button','link','textbox','checkbox','radio','combobox','listbox','option','slider','spinbutton','switch','tab','menuitem','menuitemcheckbox','menuitemradio','treeitem']);
  const attrsList=['role','type','aria-label','aria-labelledby','aria-describedby','aria-checked','aria-expanded','aria-selected','aria-disabled','aria-pressed','aria-current','aria-valuenow','aria-valuetext','placeholder','title','alt','href','name','for','id','required','readonly','multiple','contenteditable','tabindex'];
  const clean=s=>(s||'').replace(/\s+/g,' ').trim();
  let visited=0;
  function stable(n) {if(!ids.has(n))ids.set(n,state.next++);return ids.get(n);}
  function walk(el, depth, inSelect=false) {
    if (++visited>50000 || depth>256) throw new Error('DeltaDOM capture limit exceeded');
    if(el.nodeType===3) {
      const text=clean(el.textContent);
      if(!text)return null;
      return {id:stable(el),tag:'#text',role:'',text,attrs:{},interactive:false,children:[]};
    }
    if(el.nodeType!==1 || excluded.has(el.tagName))return null;
    const style=getComputedStyle(el);
    if(style.display==='none' || el.hidden || el.getAttribute('aria-hidden')==='true')return null;
    const visible=style.visibility!=='hidden' && style.visibility!=='collapse';
    if(!visible)return null;
    const tag=el.tagName.toLowerCase(), role=el.getAttribute('role')||'';
    const interactive=roles.has(role)||['button','input','select','textarea','option','summary'].includes(tag)||(tag==='a'&&el.hasAttribute('href'))||el.isContentEditable||el.tabIndex>=0||typeof el.onclick==='function'||el.hasAttribute('onclick')||style.cursor==='pointer';
    const attrs={};
    for(const name of attrsList)if(el.hasAttribute(name))attrs[name]=el.getAttribute(name);
    // Preserve the page's own icon description when an otherwise unnamed control uses a font icon.
    // Never invent a label from the class; it remains untrusted page data.
    if(interactive && !clean(el.textContent) && !attrs['aria-label'] && !attrs.title && el.hasAttribute('class'))attrs.class=el.getAttribute('class');
    if('disabled' in el)attrs.disabled=String(el.disabled);
    if(el.inert)attrs.inert='true';
    if(tag==='input') {
      attrs.value=el.type==='password'?'[REDACTED]':el.value;
      if(['checkbox','radio'].includes(el.type))attrs.checked=String(el.checked);
    }
    if(tag==='textarea'||tag==='select')attrs.value=el.value;
    if(tag==='option')attrs.selected=String(el.selected);
    if(tag==='iframe') {attrs.boundary='unsupported_iframe';warnings.add('iframe contents are not captured');}
    if(tag==='canvas')warnings.add('canvas pixels are not captured');
    const children=[];
    // Open shadow trees are traversed once, including assigned slot nodes.
    let source=el.childNodes;
    if(el.shadowRoot) {
      source=el.shadowRoot.childNodes;
      if(!state.observers.has(el.shadowRoot)) {
        const ob=new MutationObserver(()=>{state.lastMutation=performance.now();});
        ob.observe(el.shadowRoot,{subtree:true,childList:true,attributes:true,characterData:true});
        state.observers.set(el.shadowRoot,ob);
      }
    } else if(tag==='slot') {
      const assigned=el.assignedNodes(); if(assigned.length)source=assigned;
    }
    if(tag!=='textarea'&&tag!=='input')for(const child of source){
      const n=walk(child,depth+1,inSelect||tag==='select');if(n)children.push(n);
    }
    if(!interactive&&!children.length&&!['img','iframe','canvas','hr'].includes(tag))return null;
    const id=stable(el);current.set(id,el);
    return {id,tag,role,text:'',attrs,interactive,children};
  }
  const root=document.body?walk(document.body,0):null, nodes=[];
  function flatten(n,parent,order){
    const {children,...data}=n;nodes.push({...data,parent,order});
    children.forEach((c,i)=>flatten(c,n.id,i));
  }
  if(root)flatten(root,0,0);
  state.current=current;
  for(const [root,ob] of state.observers)if(root!==document&&!root.host.isConnected){ob.disconnect();state.observers.delete(root);}
  return {document:state.document,url:location.href,nodes,warnings:[...warnings],visited};
}
