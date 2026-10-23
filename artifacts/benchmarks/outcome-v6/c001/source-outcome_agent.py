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
from deltadom.action_readback import ActionReadback
from deltadom.browser_use_delivery import deliver_read_evidence
from deltadom.link_outcome import LinkMembershipVerifier
from deltadom.outcome import OutcomeCheck, OutcomeVerifier
from deltadom.presence import PresenceVerifier
from deltadom.readback import ObservedEntity, Readback, match_entities
from observe_v2 import cli
from outcome_cli_actor import run_cli
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:18765"
BANNED = ["navigate", "search", "switch", "close", "evaluate", "read_file", "write_file",
          "replace_file", "upload_file", "save_as_pdf", "done", "screenshot"]


def finish_safe_actions(actions):
    # Preserve Browser Use's native deferred-done guard for our renamed finish tool.
    # A model cannot verify an unseen action result by queuing success after a write.
    for index, action in enumerate(actions):
        if index and action.model_dump(exclude_unset=True).get("finish") is not None:
            return actions[:index]
    return actions


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
               ROOT / "benchmarks/observe_v2.py", ROOT / "benchmarks/agent-browser.json",
               ROOT / "python/deltadom/link_outcome.py", ROOT / "python/deltadom/readback.py",
               ROOT / "python/deltadom/browser_use_delivery.py"]
    sources.append(ROOT / "python/deltadom/action_readback.py")
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
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        bs = BrowserSession(cdp_url=f"http://127.0.0.1:{port}", keep_alive=True,
                            enable_default_extensions=False)
        await bs.start()
        cdp = await page.context.new_cdp_session(page)
        bs.agent_focus_target_id = (await cdp.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
        tools = Tools(exclude_actions=BANNED)
        state = {"verifier": None, "writes_started": False, "events": [], "action_units": 0}
        v5 = args.arm in {"simple-fixed", "macro-simple", "inline", "auto-control", "auto-signal"}

        @tools.action("Finish with the actual outcome. Do not claim success based only on a click or toast.")
        async def finish(success: bool, text: str):
            if args.arm in {"candidate", "membership", "link"} and success:
                verifier = state["verifier"]
                if verifier is None or not verifier.matched:
                    return ActionResult(error="No current matched outcome receipt. Register checks before writes and verify, or finish success=false with uncertainty.")
            return ActionResult(is_done=True, success=success, extracted_content=text)

        @tools.action("Reload this page to independently read its current visible state. Counts as an action.")
        async def refresh_page():
            await bs.navigate_to(page.url)
            await page.wait_for_load_state("networkidle")
            return ActionResult(extracted_content="Page reloaded. Inspect fresh browser observation.")

        if args.arm in {"macro-simple", "inline"}:
            @tools.action("Click once and independently read a result view without navigating the working page for verification. click_index=0 means read only. readback_index is an observed result-view link, or 0 for the current page AFTER the click (including any navigation caused by the click). entity_indices are observed entity links, or [0] for the source detail page's unique main h1; [] returns full visible result text and links. Entity URLs/names and nonzero readback links are captured BEFORE the click. Each click costs one unit and each read costs one unit. Never automatically retries. Readback does NOT prove absence or safe retry; consider pending effects, quantities and other task requirements separately.")
            async def click_and_read(click_index: int, readback_index: int,
                                     entity_indices: list[int]):
                visible = await page.locator("a[href]:visible").evaluate_all(
                    "els => els.map(e => ({url:e.href,label:e.innerText.trim()}))"
                )
                readback_url = page.url
                if readback_index:
                    node = await bs.get_element_by_index(readback_index)
                    if node is None or node.node_name.lower() != "a" or not node.attributes.get("href"):
                        return ActionResult(error="Readback must be an observed link")
                    readback_url = urljoin(page.url, node.attributes["href"])
                    if readback_url not in {e["url"] for e in visible}:
                        return ActionResult(error="Readback is no longer visible")
                if not urlsplit(readback_url).path.startswith(f"/env/{task['env']}/"):
                    return ActionResult(error="Readback must stay within the environment UI")
                entities = []
                for index in entity_indices:
                    if index == 0:
                        headings = page.get_by_role("main").locator("h1:visible")
                        if await headings.count() != 1:
                            return ActionResult(error="Current detail page needs one visible main h1")
                        entities.append(ObservedEntity(page.url, (await headings.inner_text()).strip()))
                    else:
                        node = await bs.get_element_by_index(index)
                        if node is None or node.node_name.lower() != "a" or not node.attributes.get("href"):
                            return ActionResult(error="Entity must be an observed link")
                        url = urljoin(page.url, node.attributes["href"])
                        labels = {e["label"] for e in visible if e["url"] == url and e["label"]}
                        if len(labels) != 1:
                            return ActionResult(error="Entity has no unique current visible name")
                        entities.append(ObservedEntity(url, labels.pop()))
                # Ground both arms identically; the sole treatment is result representation.
                if len(entities) > 32 or len({e.url for e in entities}) != len(entities):
                    return ActionResult(error="Require at most 32 distinct observed entities")
                click_result = None
                click_completed_ns = None
                if click_index:
                    action_type = type(state["current_action"])
                    click_action = action_type.model_validate({"click": {"index": click_index}})
                    click_result = await original_act(click_action, browser_session=bs)
                    click_completed_ns = time.monotonic_ns()
                if not readback_index:
                    readback_url = page.url
                    if not urlsplit(readback_url).path.startswith(f"/env/{task['env']}/"):
                        return ActionResult(error="Resulting page is outside the environment UI")
                focus = bs.agent_focus_target_id
                try:
                    result = await Readback(page).read(readback_url)
                finally:
                    if focus:
                        await bs.get_or_create_cdp_session(target_id=focus, focus=True)
                # Full evidence retained for audit in both arms, even when not sent to model.
                state["events"].append({"readback": result, "entities": [e.__dict__ for e in entities]})
                if result["status"] == "read":
                    result["acquisition"]["click_completed_monotonic_ns"] = click_completed_ns
                    result["acquisition"]["order"] = "click attempt returned, then new result document loaded" if click_index else "new result document loaded; no click"
                    if args.arm == "inline" and entities:
                        result = {**match_entities(result["evidence"], entities),
                                  "readback_url": readback_url,
                                  "acquisition": result["acquisition"]}
                    else:
                        result["requested_entities"] = [e.__dict__ for e in entities]
                if click_result:
                    result["click_result"] = click_result.model_dump(exclude_none=True)
                return ActionResult(extracted_content=json.dumps(result, ensure_ascii=False))

        if args.arm == "link":
            @tools.action("Before adding the selected entity, prepare a result-view witness. entity_indices are observed entity link indices, or [0] for the current detail page with its unique visible main h1. readback_index is an observed result-view link (e.g. Cart/Starred). The program derives exact URLs/names; no CSS or invented fields. Browsing, sorting and filtering are allowed first. This only checks new membership, not selection optimality, quantities or other task requirements.")
            async def prepare_link_membership(entity_indices: list[int], readback_index: int):
                if state["verifier"] is not None:
                    return ActionResult(error="A witness is already prepared; use verify_link_membership")
                visible = await page.locator("a[href]:visible").evaluate_all(
                    "els => els.map(e => ({url:e.href,label:e.innerText.trim()}))"
                )
                node = await bs.get_element_by_index(readback_index)
                if node is None or node.node_name.lower() != "a" or not node.attributes.get("href"):
                    return ActionResult(error="Readback index must be an observed result-view link")
                readback = urljoin(page.url, node.attributes["href"])
                if readback not in {e["url"] for e in visible} or not urlsplit(readback).path.startswith(f"/env/{task['env']}/"):
                    return ActionResult(error="Readback must be a visible UI link within this environment")
                entities = []
                for index in entity_indices:
                    if index == 0:
                        headings = page.get_by_role("main").locator("h1:visible")
                        if await headings.count() != 1:
                            return ActionResult(error="Current detail page needs one visible main h1")
                        entities.append({"url": page.url, "label": (await headings.inner_text()).strip()})
                    else:
                        entity = await bs.get_element_by_index(index)
                        if entity is None or entity.node_name.lower() != "a" or not entity.attributes.get("href"):
                            return ActionResult(error="Each entity index must be an observed link")
                        url = urljoin(page.url, entity.attributes["href"])
                        labels = {e["label"] for e in visible if e["url"] == url and e["label"]}
                        if len(labels) != 1:
                            return ActionResult(error="Entity link has no unique visible name")
                        entities.append({"url": url, "label": labels.pop()})
                try:
                    verifier = LinkMembershipVerifier(entities, readback)
                    prepared = await verifier.prepare(page, bs.navigate_to)
                    state["verifier"] = verifier
                    state["events"].append(prepared)
                    return ActionResult(extracted_content=json.dumps(prepared, ensure_ascii=False))
                except (ValueError, TypeError) as exc:
                    return ActionResult(error=str(exc))

            @tools.action("Reload the prepared result view and check for the exact observed entity URLs and visible names. Reports membership only, not whether the chosen entity meets every task requirement. No writes or retries.")
            async def verify_link_membership():
                if state["verifier"] is None:
                    return ActionResult(error="Prepare the entity link witness before its relevant change")
                receipt = await state["verifier"].verify(page, bs.navigate_to)
                state["events"].append(receipt)
                return ActionResult(extracted_content=json.dumps(receipt, ensure_ascii=False))

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
            state["current_action"] = action
            payload = action.model_dump(exclude_none=True)
            names = list(payload)
            units = 2 if names in (["prepare_membership"], ["prepare_link_membership"]) else 1
            if names == ["click_and_read"]:
                units = 1 + bool(payload["click_and_read"]["click_index"])
            if state["action_units"] + units > 40:
                return ActionResult(is_done=True, success=False, extracted_content="40 action/navigation units exhausted")
            state["action_units"] += units
            link_navigation = False
            if names == ["click"] and payload["click"].get("index") is not None:
                node = await bs.get_element_by_index(payload["click"]["index"])
                link_navigation = bool(node and node.node_name.lower() == "a" and node.attributes.get("href"))
            if not link_navigation and not all(n in {"finish", "refresh_page", "verify_outcome", "register_checks", "prepare_membership", "verify_membership", "scroll", "wait", "go_back", "find_text", "find_elements"} for n in names):
                state["writes_started"] = True
            if state["verifier"] and not all(n in {"finish", "verify_outcome", "register_checks", "prepare_membership", "verify_membership", "prepare_link_membership", "verify_link_membership"} for n in names):
                state["verifier"].invalidate()
            state["events"].append({"action": action.model_dump(exclude_none=True)})
            if args.arm in {"auto-control", "auto-signal"} and names != ["finish"]:
                focus_after_action = None

                async def perform():
                    nonlocal focus_after_action
                    performed = await original_act(action, *a, **kw)
                    focus_after_action = bs.agent_focus_target_id
                    return performed

                result, receipt = await ActionReadback(page).run(
                    perform, force_read=args.arm == "auto-control" and names == ["click"] and not link_navigation,
                    read_allowed=lambda: state["action_units"] < 40,
                )
                if focus_after_action and bs.agent_focus_target_id != focus_after_action and receipt["read_performed"]:
                    await bs.get_or_create_cdp_session(target_id=focus_after_action, focus=True)
                if receipt["read_performed"]:
                    state["action_units"] += 1
                state["events"].append({"automatic_readback": receipt})
                if receipt["status"] != "not_triggered":
                    payload_text = json.dumps({"action_result": result.model_dump(exclude_none=True),
                                               "post_action_readback": receipt}, ensure_ascii=False)
                    result = result.model_copy(update={"extracted_content": payload_text,
                                                       "include_extracted_content_only_once": True})
            else:
                result = await original_act(action, *a, **kw)
            return deliver_read_evidence(result) if v5 else result

        tools.act = audited_act
        task_prompt = session_data["instruction"] + "\nInteract only with the current local website UI. Do not access evaluation controls, backend state, or external sites. Finish with success=false if unconfirmed."
        if args.arm in {"simple", "simple-fixed", "macro-simple", "inline", "auto-control", "auto-signal"}:
            task_prompt += "\nBefore reporting success, reload or reopen affected records and verify every task requirement against the freshly read visible state. Do not trust optimistic updates or success messages. Retry only when the readback clearly establishes the operation did not take effect."
        if v5:
            task_prompt += "\nIf a tool result contains acquisition.method=new_document_navigation, that evidence comes from an independently loaded UI document. It already meets the fresh-read requirement; do not reload again solely for freshness. The returned UI evidence, not a transport completion, establishes the visible state. The working page may still show an older optimistic state. Partial evidence never proves the whole task; check every requirement."
        if args.arm in {"macro-simple", "inline"}:
            task_prompt += "\nYou may combine one click and one fresh result-view read using click_and_read. It first executes one click attempt, THEN loads a NEW document in a temporary page and returns that document's evidence. Its acquisition metadata records this order. That returned readback already satisfies the reopen/reload requirement: do not repeat a reload solely for freshness when the evidence is sufficient. The browser_state still shows the original working page and may be older; use the returned independent readback for verification. Use entity_indices only for entity-link membership; use [] for all other requirements so the full result evidence is returned. No preparation is required. Missing links are unconfirmed, not proof that retrying is safe. A partial membership receipt never proves optimality, quantity or the whole task. Inspect all remaining requirements before finish."
        if args.arm == "candidate":
            task_prompt += "\nRegister outcome checks from the task and visible page before writes. Then perform actions and verify_outcome. The checks must cover the task, not just an easy subset. A matched receipt is only visible-page evidence. Never use desired state in a selector. If coverage or identity is uncertain, report that uncertainty."
        if args.arm == "membership":
            task_prompt += "\nWhen the task is fully evidenced by entity membership in a result view, prepare_membership before mutation controls, perform actions, then verify_membership. Use observed link indices and exact entity identity text, not guessed URLs or attributes. If this contract cannot cover the task, finish success=false and explain the unsupported requirements."
        if args.arm == "link":
            task_prompt += "\nUse prepare_link_membership before the relevant membership change, then verify_link_membership after. You may browse, sort or filter first. The witness proves only the selected entity appears in the selected result view; separately verify every other task requirement using fresh visible evidence. Never equate a membership witness with selection optimality or full task correctness. If the witness or other required evidence is unavailable, finish success=false."
        agent = Agent(task=task_prompt, llm=model, browser_session=bs, tools=tools,
                      use_vision=False, use_judge=False, enable_planning=False,
                      calculate_cost=False, max_actions_per_step=5 if v5 else 1, max_failures=2,
                      llm_timeout=600, step_timeout=650, file_system_path=files, directly_open_url=False)
        native_multi_act = agent.multi_act

        async def guarded_multi_act(actions):
            return await native_multi_act(finish_safe_actions(actions))

        agent.multi_act = guarded_multi_act
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
                      "phase": args.phase or ("development" if args.dev else "confirmation"),
                      "scope": ("agent-browser 0.39.1 native CLI with controlled scaffold" if args.arm == "agent-browser" else "Browser Use 0.13.11 native agent with restricted tools") + "; text-only desktop relay; not official paper harness score",
                      "claimed_success": claimed, "evaluation": verdict, "error": error,
                      "agent_errors": history.errors() if history and hasattr(history, "errors") else [],
                      "action_units": len(history.rows) if args.arm == "agent-browser" and history else state["action_units"],
                      "model_requests": model.calls, "provider_usage": None,
                      "max_actions_per_step": agent.settings.max_actions_per_step,
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
    parser.add_argument("--phase", choices=["development", "confirmation", "exploratory"])
    parser.add_argument("--condition", choices=["clean", "intervention"], required=True)
    parser.add_argument("--arm", choices=["native", "simple", "candidate", "membership", "link", "agent-browser", "simple-fixed", "macro-simple", "inline", "auto-control", "auto-signal"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
