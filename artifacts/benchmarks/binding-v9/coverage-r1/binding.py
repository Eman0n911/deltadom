"""Record-relative action replay from visible identity, without hand-written selectors.

Supported names are a conservative DOM subset, not a complete accessible-name
implementation. Bindings do not encode task goals or guarantee server outcomes.
"""
import json
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path(__file__).with_suffix('.js').read_text()


@dataclass(frozen=True)
class ActionBinding:
    data: dict

    @classmethod
    async def capture(cls, locator):
        result = await locator.evaluate('(target)=>(' + SCRIPT + ')({mode:"capture",target})')
        if result['status'] != 'bound':
            return None, result
        return cls(result['binding']), result

    @classmethod
    def from_json(cls, value):
        data = json.loads(value)
        if (data.get('version') != 1 or data.get('mode') not in {'relational', 'unique_control'}
                or not isinstance(data.get('target'), dict) or not isinstance(data.get('anchors'), list)
                or not isinstance(data.get('document_url'), str)
                or (data['mode'] == 'relational' and not data['anchors'])):
            raise ValueError('invalid action binding')
        return cls(data)

    def to_json(self):
        return json.dumps(self.data, ensure_ascii=False, sort_keys=True)

    async def resolve(self, page):
        handle = await page.evaluate_handle(SCRIPT, {'mode': 'resolve', 'binding': self.data})
        try:
            status = await (await handle.get_property('status')).json_value()
            if status != 'resolved':
                return None, await handle.json_value()
            element = (await handle.get_property('element')).as_element()
            return element, {'status': 'resolved', 'candidate_count': 1}
        finally:
            await handle.dispose()

    async def click(self, page, *, timeout_ms=1000):
        element, receipt = await self.resolve(page)
        if element is None:
            return receipt
        try:
            await element.click(timeout=timeout_ms)
            return {**receipt, 'status': 'clicked', 'scope': 'one UI click; outcome not verified'}
        finally:
            await element.dispose()
