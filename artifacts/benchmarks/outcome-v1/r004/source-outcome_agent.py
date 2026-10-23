"""BreakingWeb outcome experiment with native Browser Use and a desktop mailbox.

Model input contains only the rendered task and native browser observations.
The official evaluator is called after the episode, never delivered to the actor.
"""

import argparse
import asyncio
import hashlib
import json
import os
import socket
import tempfile
import time
import urllib.request
from contextlib import AsyncExitStack
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urljoin, urlsplit

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["BROWSER_USE_CLOUD_SYNC"] = "false"
os.environ["BROWSER_USE_LOGGING_LEVEL"] = "error"

from browser_use import Agent, BrowserSession, Tools
from browser_use.agent.views import ActionResult
from browser_use.llm.views import ChatInvokeCompletion
from deltadom.outcome import OutcomeCheck, OutcomeVerifier
from deltadom.presence import PresenceVerifier
from observe_v2 import cli
from outcome_cli_actor import run_cli
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:18765"
BANNED = ["navigate", "search", "switch", "close", "evaluate", "read_file", "write_file",
          "replace_file", "upload_file", "save_as_pdf", "done", "screenshot"]


def http_json(path, payload):
    request = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request, timeout=30))


class DesktopMailbox:
    model = "WorkBuddy-Deepseek-V4.1-Flash"
    provider = "desktop-manual-relay"
    name = model
    model_name = model
    _verified_api_keys = True

    def __init__(self, folder):
        self.folder = folder
        self.calls = 0

    async def ainvoke(self, messages, output_format=None, **kwargs):
        self.calls += 1
        request_id = f"{self.calls:03d}"
        packet = {"request_id": request_id,
                  "messages": [m.model_dump(mode="json") for m in messages],
                  "output_schema": output_format.model_json_schema() if output_format else None}
        (self.folder / f"request-{request_id}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2))
        pending = self.folder / "pending.tmp"
        pending.write_text(json.dumps({"request": f"request-{request_id}.json",
                                       "response": f"response-{request_id}.json"}))
        pending.replace(self.folder / "pending.json")
        response = self.folder / f"response-{request_id}.json"
        deadline = time.monotonic() + 600
        while not response.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("Desktop model reply not received within 600 seconds")
            await asyncio.sleep(0.5)
        raw = response.read_text()
        completion = output_format.model_validate_json(raw) if output_format else raw
        return ChatInvokeCompletion(completion=completion, usage=None)


async def run(args):
    manifest = json.loads((ROOT / "artifacts/benchmarks/outcome-v1/manifest.json").read_text())
    tasks = manifest["dev" if args.dev else "confirmation"]
    task = next(t for t in tasks if t["task_id"] == args.task)
    args.output.mkdir(parents=True, exist_ok=False)
    mailbox = args.output / "mailbox"
    mailbox.mkdir()
    sources = [Path(__file__), ROOT / "benchmarks/outcome_cli_actor.py",
               ROOT / "python/deltadom/outcome.py", ROOT / "python/deltadom/presence.py",
               ROOT / "benchmarks/observe_v2.py", ROOT / "benchmarks/agent-browser.json"]
    (args.output / "source-binding.json").write_text(json.dumps({
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }, indent=2))
    for source in sources:
        (args.output / ("source-" + source.name)).write_bytes(source.read_bytes())
    (args.output / "environment.json").write_text(json.dumps({
        "browser_use": version("browser-use"), "playwright": version("playwright"),
        "agent_browser": json.loads((ROOT / ".bench/node/node_modules/agent-browser/package.json").read_text())["version"],
        "breakingweb": manifest["upstream"], "seed": manifest["seed"],
        "model_channel": model_channel if (model_channel := manifest.get("model_channel")) else "desktop relay",
    }, indent=2))
    params = {"task_id": task["task_id"], "seed": manifest["seed"]}
    if args.condition == "intervention":
        params["variant_filename"] = task["variant"]
    session_data = await asyncio.to_thread(http_json, f"/api/env/{task['env']}/session", params)
    sid = session_data["session_id"]
    cli_name = "dd-" + hashlib.sha256(sid.encode()).hexdigest()[:10]
    url = BASE + f"/env/{task['env']}" + session_data["start_path"] + f"?session={sid}&agent_mode=1"
    (args.output / "session.json").write_text(json.dumps(session_data, indent=2))
    model = DesktopMailbox(mailbox)
    async with AsyncExitStack() as stack:
        p = await stack.enter_async_context(async_playwright())
        files = stack.enter_context(tempfile.TemporaryDirectory())
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        browser = await p.chromium.launch(channel="chrome", args=[f"--remote-debugging-port={port}"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        bs = BrowserSession(cdp_url=f"http://127.0.0.1:{port}", keep_alive=True,
                            enable_default_extensions=False)
        await bs.start()
        cdp = await page.context.new_cdp_session(page)
        bs.agent_focus_target_id = (await cdp.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
        tools = Tools(exclude_actions=BANNED)
        state = {"verifier": None, "writes_started": False, "events": [], "action_units": 0}

        @tools.action("Finish with the actual outcome. Do not claim success based only on a click or toast.")
        async def finish(success: bool, text: str):
            if args.arm in {"candidate", "membership"} and success:
                verifier = state["verifier"]
                if verifier is None or not verifier.matched:
                    return ActionResult(error="No current matched outcome receipt. Register checks before writes and verify, or finish success=false with uncertainty.")
            return ActionResult(is_done=True, success=success, extracted_content=text)

        @tools.action("Reload this page to independently read its current visible state. Counts as an action.")
        async def refresh_page():
            await bs.navigate_to(page.url)
            await page.wait_for_load_state("networkidle")
            return ActionResult(extracted_content="Page reloaded. Inspect fresh browser observation.")

        if args.arm == "membership":
            @tools.action("Before mutation controls, register a NEW MEMBERSHIP outcome using 2..8 exact visible identity strings per entity and the index of an observed result-view link. No CSS or guessed attributes. The tool verifies each entity is uniquely visible here, absent in the result view, and returns here. Suitable only if presence in that selected result view really proves the requested change. Unsupported task types must remain unconfirmed.")
            async def prepare_membership(entities: list[list[str]], readback_index: int):
                if state["writes_started"] or state["verifier"] is not None:
                    return ActionResult(error="Contract frozen or mutation controls already used")
                node = await bs.get_element_by_index(readback_index)
                if node is None or node.node_name.lower() != "a" or not node.attributes.get("href"):
                    return ActionResult(error="Use a currently observed link index")
                url = urljoin(page.url, node.attributes["href"])
                links = await page.locator("a[href]:visible").evaluate_all("els => els.map(e => e.href)")
                if url not in links or not urlsplit(url).path.startswith(f"/env/{task['env']}/"):
                    return ActionResult(error="Result view must be an observed link within this environment UI")
                try:
                    verifier = PresenceVerifier(entities, url)
                    prepared = await verifier.prepare(page, bs.navigate_to)
                    state["verifier"] = verifier
                    state["events"].append(prepared)
                    return ActionResult(extracted_content=json.dumps(prepared, ensure_ascii=False))
                except (ValueError, TypeError) as exc:
                    return ActionResult(error=str(exc))

            @tools.action("Independently reload the registered result view and verify the grounded entities newly appear there. No writes or automatic retries.")
            async def verify_membership():
                if state["verifier"] is None:
                    return ActionResult(error="Prepare a valid membership contract first")
                result = await state["verifier"].verify(page, bs.navigate_to)
                state["events"].append(result)
                return ActionResult(extracted_content=json.dumps(result, ensure_ascii=False))

        if args.arm == "candidate":
            @tools.action("Before editing/clicking mutation controls, freeze ALL task outcome checks. readback_index is the current observed link index to a same-site result view, or 0 for this page. Never reconstruct truncated URLs. Each check: key, scope CSS, exact visible identity text inside scope, target CSS relative to scope (independent of expected value), kind text/value/checked/attribute, expected string or boolean, optional attribute aria-pressed/aria-checked/aria-selected/aria-label/title. Only page-visible evidence; no evaluator access. A static unchanged label cannot prove a changed state.")
            async def register_checks(checks: list[dict], readback_index: int):
                if state["writes_started"] or state["verifier"] is not None:
                    return ActionResult(error="Contract already frozen or actions started")
                if readback_index:
                    node = await bs.get_element_by_index(readback_index)
                    if node is None or node.node_name.lower() != "a" or not node.attributes.get("href"):
                        return ActionResult(error="Readback index must be a current visible link")
                    readback_url = urljoin(page.url, node.attributes["href"])
                else:
                    readback_url = page.url
                visible_links = await page.locator("a[href]:visible").evaluate_all("els => els.map(e => e.href)")
                if readback_url not in {*visible_links, page.url} or not urlsplit(readback_url).path.startswith(f"/env/{task['env']}/"):
                    return ActionResult(error="Readback must be a currently observed UI link in this environment, never an API, launch page, or evaluator")
                try:
                    state["verifier"] = OutcomeVerifier([OutcomeCheck(**c) for c in checks], readback_url=readback_url, timeout_ms=10000)
                except (ValueError, TypeError) as exc:
                    return ActionResult(error=str(exc))
                return ActionResult(extracted_content="Contract frozen. This does not certify completeness of task interpretation.")

            @tools.action("Reload and check all frozen outcome conditions against visible page fields; returns compact field evidence. Does not retry writes. Counts as one action.")
            async def verify_outcome():
                if state["verifier"] is None:
                    return ActionResult(error="Register checks first")
                receipt = await state["verifier"].verify(page)
                state["events"].append(receipt)
                return ActionResult(extracted_content=json.dumps(receipt, ensure_ascii=False))

        original_act = tools.act

        async def audited_act(action, *a, **kw):
            payload = action.model_dump(exclude_none=True)
            names = list(payload)
            units = 2 if names == ["prepare_membership"] else 1
            if state["action_units"] + units > 40:
                return ActionResult(is_done=True, success=False, extracted_content="40 action/navigation units exhausted")
            state["action_units"] += units
            link_navigation = False
            if names == ["click"] and payload["click"].get("index") is not None:
                node = await bs.get_element_by_index(payload["click"]["index"])
                link_navigation = bool(node and node.node_name.lower() == "a" and node.attributes.get("href"))
            if not link_navigation and not all(n in {"finish", "refresh_page", "verify_outcome", "register_checks", "prepare_membership", "verify_membership", "scroll", "wait", "go_back", "find_text", "find_elements"} for n in names):
                state["writes_started"] = True
            if state["verifier"] and not all(n in {"finish", "verify_outcome", "register_checks", "prepare_membership", "verify_membership"} for n in names):
                state["verifier"].invalidate()
            state["events"].append({"action": action.model_dump(exclude_none=True)})
            return await original_act(action, *a, **kw)

        tools.act = audited_act
        task_prompt = session_data["instruction"] + "\nInteract only with the current local website UI. Do not access evaluation controls, backend state, or external sites. Finish with success=false if unconfirmed."
        if args.arm == "simple":
            task_prompt += "\nBefore reporting success, reload or reopen affected records and verify every task requirement against the freshly read visible state. Do not trust optimistic updates or success messages. Retry only when the readback clearly establishes the operation did not take effect."
        if args.arm == "candidate":
            task_prompt += "\nRegister outcome checks from the task and visible page before writes. Then perform actions and verify_outcome. The checks must cover the task, not just an easy subset. A matched receipt is only visible-page evidence. Never use desired state in a selector. If coverage or identity is uncertain, report that uncertainty."
        if args.arm == "membership":
            task_prompt += "\nWhen the task is fully evidenced by entity membership in a result view, prepare_membership before mutation controls, perform actions, then verify_membership. Use observed link indices and exact entity identity text, not guessed URLs or attributes. If this contract cannot cover the task, finish success=false and explain the unsupported requirements."
        agent = Agent(task=task_prompt, llm=model, browser_session=bs, tools=tools,
                      use_vision=False, use_judge=False, enable_planning=False,
                      calculate_cost=False, max_actions_per_step=1, max_failures=2,
                      llm_timeout=600, step_timeout=650, file_system_path=files, directly_open_url=False)
        error = None
        history = None
        started = time.monotonic()
        try:
            history = await asyncio.wait_for(
                run_cli(model, port, page, session_data["instruction"], cli_name)
                if args.arm == "agent-browser" else agent.run(max_steps=40), timeout=2400
            )
        except Exception as exc:  # noqa: BLE001 -- retain every harness failure in the denominator
            error = type(exc).__name__ + ": " + str(exc)
        finally:
            if history is not None:
                history.save_to_file(args.output / "history.json")
            await page.screenshot(path=str(args.output / "final.png"))
            # Seal actor output before requesting judge-only evidence.
            claimed = history.is_successful() if history else None
            (args.output / "actor-sealed.json").write_text(json.dumps({"claimed_success": claimed, "error": error}))
            verdict = await asyncio.to_thread(http_json, f"/api/env/{task['env']}/evaluate", {"session_id": sid})
            report = {"arm": args.arm, "task": args.task, "condition": args.condition,
                      "scope": ("agent-browser 0.39.1 native CLI with controlled scaffold" if args.arm == "agent-browser" else "Browser Use 0.13.11 native agent with restricted tools") + "; text-only desktop relay; not official paper harness score",
                      "claimed_success": claimed, "evaluation": verdict, "error": error,
                      "agent_errors": history.errors() if history and hasattr(history, "errors") else [],
                      "action_units": len(history.rows) if args.arm == "agent-browser" and history else state["action_units"],
                      "model_requests": model.calls, "provider_usage": None,
                      "model_usage_note": "Counts mailbox requests, not all WorkBuddy internal generations/tool turns; desktop context and tokens unavailable",
                      "wall_seconds": time.monotonic() - started, "events": state["events"]}
            (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            (mailbox / "finished.json").write_text(json.dumps({"finished": True}))
            await bs.stop()
            if args.arm == "agent-browser":
                try:
                    await cli(cli_name, port, "close")
                except (RuntimeError, TimeoutError) as exc:
                    (args.output / "cleanup-error.txt").write_text(str(exc))
            await browser.close()
            print(json.dumps({k: v for k, v in report.items() if k != "events"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--condition", choices=["clean", "intervention"], required=True)
    parser.add_argument("--arm", choices=["native", "simple", "candidate", "membership", "agent-browser"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
