"""Real native action and MessageManager integration. No model or task score."""

import asyncio
import hashlib
import json
import socket
import tempfile
from pathlib import Path

from browser_use import BrowserSession, Tools
from browser_use.agent.message_manager.service import MessageManager
from browser_use.agent.views import AgentStepInfo
from browser_use.filesystem.file_system import FileSystem
from browser_use.llm.messages import SystemMessage
from deltadom.action_readback import ActionReadback
from deltadom.browser_use_delivery import attach_readback
from outcome_agent import BANNED, BASE, ROOT, http_json
from playwright.async_api import async_playwright


async def main():
    output = ROOT / "artifacts/benchmarks/outcome-v6/native-integration.json"
    if output.exists():
        raise FileExistsError(output)
    rows = []
    async with async_playwright() as p:
        for condition in ["clean", "intervention"]:
            params = {"task_id": "gmail_star_email", "seed": 42}
            if condition == "intervention":
                params["variant_filename"] = "gmail_star_email__star_retry.yaml"
            site = await asyncio.to_thread(http_json, "/api/env/gmail/session", params)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            browser = await p.chromium.launch(channel="chrome", args=[f"--remote-debugging-port={port}"])
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(BASE + "/env/gmail" + site["start_path"] +
                            f"?session={site['session_id']}&agent_mode=1", wait_until="networkidle")
            bs = BrowserSession(cdp_url=f"http://127.0.0.1:{port}", keep_alive=True,
                                enable_default_extensions=False)
            await bs.start()
            cdp = await context.new_cdp_session(page)
            bs.agent_focus_target_id = (await cdp.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
            try:
                snapshot = await bs.get_browser_state_summary()
                indices = [key for key, node in snapshot.dom_state.selector_map.items()
                           if node.attributes.get("aria-label") == "Star Project Update — Q1 Milestones"]
                assert len(indices) == 1
                tools = Tools(exclude_actions=BANNED)
                action_type = tools.registry.create_action_model()
                action = action_type.model_validate({"click": {"index": indices[0]}})

                async def click_once(native_tools=tools, native_action=action, native_session=bs):
                    return await native_tools.act(native_action, browser_session=native_session)

                original, receipt = await ActionReadback(page).run(click_once)
                assert not original.error
                assert len(receipt["writes"]) == 1 and receipt["read_performed"]
                delivered = attach_readback(original, receipt)
                with tempfile.TemporaryDirectory() as tmp:
                    manager = MessageManager(task="mechanical native integration; no model", system_message=SystemMessage(content="audit"),
                                             file_system=FileSystem(base_dir=tmp))
                    manager._update_agent_history_description(result=[delivered],
                        step_info=AgentStepInfo(step_number=0, max_steps=40))
                    read = manager.state.read_state_description
                    assert delivered.extracted_content in read
                    controls = receipt["evidence"]["controls"]
                    starred = any(c["label"] == "Unstar Project Update — Q1 Milestones" for c in controls)
                    assert starred == (condition == "clean")
                    rows.append({"condition": condition, "native_action": action.model_dump(exclude_none=True),
                                 "original_result": original.model_dump(exclude_none=True), "receipt": receipt,
                                 "original_result_unchanged": "post_action_readback" not in (original.extracted_content or ""),
                                 "full_payload_delivered_to_native_read_state": True,
                                 "read_state": read, "postcondition_visible": starred,
                                 "no_model_requests": True})
            finally:
                await bs.stop()
                await browser.close()
    files = [Path(__file__), ROOT / "python/deltadom/action_readback.py",
             ROOT / "python/deltadom/browser_use_delivery.py", ROOT / "python/deltadom/readback.py"]
    output.write_text(json.dumps({"scope": "2 mechanical native tool + message-construction checks; no model, no scorer",
                                 "sources": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
                                 "rows": rows}, ensure_ascii=False, indent=2) + "\n")
    print("native click -> completed HTTP request -> independent UI read -> native read-state: 2/2 passed")


if __name__ == "__main__":
    asyncio.run(main())
