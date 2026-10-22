"""Real Browser Use Agent callback wiring with a scripted responder, NOT a model trial."""
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile

os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['BROWSER_USE_CLOUD_SYNC'] = 'false'
os.environ['BROWSER_USE_LOGGING_LEVEL'] = 'error'
from browser_use import Agent, BrowserSession
from browser_use.llm.views import ChatInvokeCompletion
from deltadom.demo import fixture_server
from deltadom.recording import BrowserUseRecorder
from deltadom.tape import read_tape
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/benchmarks/native-agent-contract'


class ScriptedResponder:
    """A test double, explicitly not a language model or benchmark actor."""
    model = 'contract-test-double'
    provider = 'test'
    name = 'contract-test-double'
    model_name = model
    _verified_api_keys = True

    def __init__(self):
        self.received = []

    async def ainvoke(self, messages, output_format=None, **kwargs):
        self.received.append([m.model_dump(mode='json') for m in messages])
        return ChatInvokeCompletion(completion=output_format.model_validate({
            'evaluation_previous_goal': 'Interface check only',
            'memory': 'No autonomous task or score', 'next_goal': 'End interface check',
            'action': [{'done': {'text': 'Callback interface check only', 'success': True}}],
        }), usage=None)


async def main():
    OUT.mkdir(exist_ok=False)
    with fixture_server() as url, tempfile.TemporaryDirectory() as files:
        async with async_playwright() as p:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            browser = await p.chromium.launch(channel='chrome', args=[f'--remote-debugging-port={port}'])
            session = BrowserSession(cdp_url=f'http://127.0.0.1:{port}', keep_alive=True,
                                     enable_default_extensions=False)
            responder = ScriptedResponder()
            try:
                agent = Agent(task='Exercise the recording callback on the local sample.',
                              llm=responder, browser_session=session, use_vision=False,
                              initial_actions=[{'navigate': {'url': url}}],
                              use_judge=False, enable_planning=False, calculate_cost=False,
                              file_system_path=files)
                with BrowserUseRecorder(OUT / 'agent.ddt') as recorder:
                    await agent.run(max_steps=1, on_step_end=recorder.on_step_end)
                records = [json.loads(x.text) for x in read_tape(OUT / 'agent.ddt')]
                assert len(records) == len(responder.received) == 1
                assert records[0]['messages'] == responder.received[0]
                assert 'Choose 7' in json.dumps(records[0]['messages'])
                report = {'status': 'pass', 'browser_use': '0.13.11', 'browser': browser.version,
                          'actual_agent_run': True, 'scripted_responder': True,
                          'recorded_messages_equal_to_responder_inputs': True,
                          'model_calls': 0, 'provider_usage': None,
                          'not_run': ['model task success', 'cost savings', 'autonomous benchmark'],
                          'scope': 'callback wiring only; done action is scripted, not scored'}
                (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(report, indent=2))
            finally:
                await session.stop()
                await browser.close()


asyncio.run(main())
