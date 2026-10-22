"""Record copied model reply verbatim, then execute its JSON without repairs."""
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

URL='http://127.0.0.1:8879'
state=json.load(urlopen(URL))
raw=sys.stdin.read()
p=Path(state['prompt_file']).with_name(f"{state['arm']}-{state['task']}-{state['turn']}-raw-reply.txt")
p.write_text(raw,encoding='utf-8')
action=json.loads(raw)
request=Request(URL,data=json.dumps(action).encode(),headers={'Content-Type':'application/json'},method='POST')
response=json.load(urlopen(request,timeout=90))
print(json.dumps({k:v for k,v in response.items() if k!='prompt'},ensure_ascii=False))
