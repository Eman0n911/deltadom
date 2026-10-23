"""Independent exact full-context baseline, no semantic-row or site selectors."""
import json

CONTEXTS='''elements=>elements.map(e=>{
 const values=[];const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
 for(let root=e.parentElement;root && root!==document.body;root=root.parentElement){
  if(elements.filter(p=>root.contains(p)).length!==1)continue;
  values.push(JSON.stringify({text:norm(root.innerText),links:[...root.querySelectorAll('a[href]')]
    .filter(a=>a.checkVisibility()).map(a=>[a.href,norm(a.innerText)])}));
 }
 return values;
})'''


class ContextCheck:
    def __init__(self,name,fingerprint,document_url,role):
        self.name=name;self.fingerprint=fingerprint;self.document_url=document_url;self.role=role

    @classmethod
    async def capture(cls,page,target,name):
        role=await target.get_attribute('role') or 'button'
        peers=page.get_by_role(role,name=name,exact=True)
        contexts=await peers.evaluate_all(CONTEXTS)
        original=await target.element_handle()
        try:
            index=await peers.evaluate_all('(elements,original)=>elements.indexOf(original)',original)
        finally:await original.dispose()
        if index<0:return None
        if len(contexts)==1:return cls(name,None,page.url,role)
        for fingerprint in contexts[index]:
            if sum(fingerprint in c for c in contexts)==1:
                return cls(name,fingerprint,page.url,role)
        return None

    async def click(self,page,*,timeout_ms=1000):
        if page.url!=self.document_url:return {'status':'unresolved'}
        peers=page.get_by_role(self.role,name=self.name,exact=True)
        if self.fingerprint is not None:
            contexts=await peers.evaluate_all(CONTEXTS)
            indices=[i for i,c in enumerate(contexts) if self.fingerprint in c]
            if len(indices)!=1:return {'status':'unresolved'}
            peers=peers.nth(indices[0])
        await peers.click(timeout=timeout_ms)
        return {'status':'clicked','fingerprint':json.loads(self.fingerprint) if self.fingerprint else None}
