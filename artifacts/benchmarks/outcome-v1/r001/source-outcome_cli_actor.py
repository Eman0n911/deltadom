"""Same desktop decision channel over real agent-browser CLI tools.

This is a controlled CLI scaffold; agent-browser does not ship an LLM agent loop.
"""

import asyncio
import json
from typing import Literal

from browser_use.llm.messages import SystemMessage, UserMessage
from observe_v2 import cli
from pydantic import BaseModel


class CLIAction(BaseModel):
    action: Literal["click", "fill", "scroll_down", "scroll_up", "back", "refresh", "finish"]
    target: str = ""
    text: str = ""
    success: bool = False


class CLIHistory:
    def __init__(self, rows, success):
        self.rows, self.success = rows, success

    def is_successful(self):
        return self.success

    def save_to_file(self, path):
        path.write_text(json.dumps(self.rows, ensure_ascii=False, indent=2))


async def run_cli(model, port, page, task, name):
    rows, success = [], False
    instructions = SystemMessage(content=(
        "Complete the user's browser task using agent-browser native snapshot refs. "
        "Only interact with the current local website UI; no evaluator, backend state or external sites. "
        "Return one JSON action. click/fill use e-number refs (e.g. e5). "
        "Use refresh to independently read page state, back for previous page, scroll_down/up for scrolling. "
        "Finish with success=false if unconfirmed. Do not claim success based only on a click or toast."
    ))
    last_error = None
    for step in range(40):
        snapshot, _ = await cli(name, port, "snapshot")
        prompt = json.dumps({"task": task, "step": step + 1, "budget": 40,
                             "action_history": rows, "last_error": last_error,
                             "snapshot": snapshot}, ensure_ascii=False)
        action = (await model.ainvoke([instructions, UserMessage(content=prompt)], CLIAction)).completion
        last_error = None
        try:
            if action.action == "finish":
                success = action.success
                rows.append({"action": action.model_dump()})
                break
            if action.action in {"click", "fill"}:
                ref = action.target.lstrip("@")
                if not (ref.startswith("e") and ref[1:].isdigit()):
                    raise ValueError("target must be an observed e-number ref")
                await cli(name, port, action.action, "@" + ref,
                          *([action.text] if action.action == "fill" else []))
            elif action.action == "refresh":
                await cli(name, port, "reload")
            elif action.action == "back":
                await cli(name, port, "back")
            else:
                await cli(name, port, "scroll", "down" if action.action == "scroll_down" else "up", "600")
        except (RuntimeError, ValueError, TimeoutError) as exc:
            last_error = type(exc).__name__ + ": " + str(exc)
        rows.append({"action": action.model_dump(), "error": last_error})
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(0.1)
    return CLIHistory(rows, success)
