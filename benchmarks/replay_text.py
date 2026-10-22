"""Matched-information text codec comparison using immutable 0.2.0 snapshots."""
import hashlib
import json
from pathlib import Path
from collections import defaultdict

import tiktoken
from deltadom import DeltaSession, StateMirror, TextMirror

root = Path(__file__).resolve().parents[1]
source = root / 'artifacts/benchmarks/observation-v1'
out = root / 'artifacts/benchmarks/serialization-v2'
out.mkdir(exist_ok=False)
encoder = tiktoken.get_encoding('cl100k_base')
rows = []
for seed in [11, 22, 33]:
    for case in ['enter-text', 'login-user', 'click-checkboxes', 'email-inbox', 'local-shop']:
        sender, structured, receiver = DeltaSession(), StateMirror(), TextMirror()
        for step in range(8 if case == 'local-shop' else 6):
            file = source / f'{seed}-{case}-{step}-deltadom-delta.json'
            old = json.loads(file.read_text())
            nodes = structured.apply(old)
            new = json.loads(sender.process_frame(json.dumps(dict(document=old['document'], url=old['url'], nodes=nodes))))
            assert receiver.apply(new['text']) == nodes
            name = f'{seed}-{case}-{step}.txt'
            (out/name).write_text(new['text'])
            rows.append(dict(seed=seed, case=case, step=step, raw=name,
                source_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                before_tokens=len(encoder.encode(old['text'],disallowed_special=())),
                after_tokens=len(encoder.encode(new['text'],disallowed_special=())), exact=True))
totals = defaultdict(lambda:dict(before_tokens=0,after_tokens=0,frames=0))
for r in rows:
    total=totals['local-shop' if r['case']=='local-shop' else 'MiniWoB-derived']
    for key in ['before_tokens','after_tokens']: total[key]+=r[key]
    total['frames']+=1
(out/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
(out/'summary.json').write_text(json.dumps(totals,indent=2)+'\n')
print(json.dumps(totals,indent=2))
