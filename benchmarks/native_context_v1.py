"""Native MessageManager contract check; no model or agent task success claim."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['BROWSER_USE_CLOUD_SYNC'] = 'false'
from browser_use.agent.message_manager.service import MessageManager
from browser_use.filesystem.file_system import FileSystem
from browser_use.llm.messages import SystemMessage, UserMessage
from deltadom.recording import BrowserUseRecorder
from deltadom.tape import read_tape
import tiktoken

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/benchmarks/native-context-v1'


async def main():
    OUT.mkdir(exist_ok=False)
    enc = tiktoken.get_encoding('cl100k_base')
    rows = []
    with tempfile.TemporaryDirectory() as tmp, BrowserUseRecorder(OUT / 'inputs.ddt') as recorder:
        manager = MessageManager('Contract check only', SystemMessage(content='Native context check'),
                                 FileSystem(tmp))
        state = SimpleNamespace(n_steps=0, last_model_output=None, last_result=[])
        agent = SimpleNamespace(_message_manager=manager, state=state)
        for i in range(6):
            source = ROOT / f'artifacts/benchmarks/observation-v2/11-login-user-{i}-browser-use.txt'
            text = source.read_text()
            # Exercise the real state-slot semantics with the real native DOM text.
            # Only the slot is under test; this is not AgentMessagePrompt/full wire serialization.
            manager._set_message_with_type(UserMessage(content=text), 'state')
            messages = manager.get_messages()
            original = [m.model_dump(mode='json') for m in messages]
            state.n_steps = i + 1
            await recorder.on_step_end(agent)
            assert original == [m.model_dump(mode='json') for m in messages]
            assert len(messages) == 2
            assert messages[-1].content == text
            serialized = json.dumps(original, ensure_ascii=False, separators=(',', ':'))
            (OUT / f'{i+1}-messages.json').write_text(serialized)
            rows.append({'step': i + 1, 'messages': len(messages),
                         'serialized_input_tokens_proxy': len(enc.encode(serialized)),
                         'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    decoded = list(read_tape(OUT / 'inputs.ddt'))
    for row in decoded:
        recorded = json.loads(row.text)['messages']
        expected = json.loads((OUT / f'{row.seq}-messages.json').read_text())
        assert recorded == expected
    report = {'browser_use': '0.13.11', 'states': len(rows), 'state_slot_replaces_previous': True,
              'recorded_messages_equal': True, 'llm_input_reduction': 0,
              'scope': 'native MessageManager state-slot contract; no actor/model/provider calls',
              'not_run': ['full agent loop', 'provider wire request', 'provider usage', 'model success'],
              'rows': rows}
    (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


asyncio.run(main())
