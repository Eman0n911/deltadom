"""BreakingWeb development UI integration; 16 fixed cells, no model/scorer.

Inject loss of the caller's acknowledgement AFTER one actual UI action. The
component sees only ordinary UI evidence. No extra write retries are hidden.
"""
import argparse
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import urljoin

from deltadom.recovery import RecoveryLedger, WriteIntent
from outcome_agent import BASE, ROOT, http_json
from playwright.async_api import async_playwright
from recovery_controls import FreshCheck, Journal

ARMS = ["fresh_exact_check", "request_journal", "resource_journal", "candidate"]


async def main(output):
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((ROOT / "artifacts/benchmarks/outcome-v1/manifest.json").read_text())
    tasks = [manifest["dev"][0], manifest["confirmation"][0]]
    sources = [Path(__file__), ROOT / "benchmarks/recovery_controls.py",
               ROOT / "python/deltadom/recovery.py"]
    for source in sources:
        (output / source.name).write_bytes(source.read_bytes())
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                for task in tasks:
                    for condition in manifest["conditions"]:
                        for arm in ARMS:
                            context = await browser.new_context()
                            row = {"task": task["task_id"], "condition": condition, "arm": arm,
                                   "callbacks": 0, "reads": [], "attempts": []}
                            try:
                                params = {"task_id": task["task_id"], "seed": manifest["seed"]}
                                if condition == "intervention":
                                    params["variant_filename"] = task["variant"]
                                site = await asyncio.to_thread(http_json, f"/api/env/{task['env']}/session", params)
                                page = await context.new_page()
                                await page.goto(BASE + f"/env/{task['env']}" + site["start_path"] +
                                                f"?session={site['session_id']}&agent_mode=1", wait_until="networkidle")
                                if task["env"] == "gmail":
                                    label = "Project Update — Q1 Milestones"
                                    button = page.get_by_role("button", name="Star " + label, exact=True)
                                    identity = await button.evaluate("e=>e.closest('article').querySelector('a[href]').href")
                                    read_url = page.url
                                    effect = {"starred": True}
                                else:
                                    await page.get_by_role("link", name="Browse Electronics", exact=True).click()
                                    await page.get_by_role("combobox", name="Sort results").select_option(label="Price: Low to High")
                                    await page.wait_for_load_state("networkidle")
                                    await page.get_by_role("main").locator("a[href*='/product/']:visible").first.click()
                                    await page.wait_for_load_state("networkidle")
                                    identity = page.url
                                    label = (await page.get_by_role("main").locator("h1").inner_text()).strip()
                                    read_url = urljoin(page.url, await page.locator("a[aria-label^='Shopping cart']").get_attribute("href"))
                                    button = page.get_by_role("button", name=f"Add {label} to Cart", exact=True)
                                    effect = {"cart_membership": True}
                                body = await page.query_selector("body")
                                actor_url = page.url
                                intents = [WriteIntent("initial", identity, effect), WriteIntent("replanned", identity, effect)]
                                path = Path(tmp) / f"{len(rows)}.sqlite"

                                async def read_goal(_=None):
                                    probe = await context.new_page()
                                    try:
                                        response = await probe.goto(read_url, wait_until="networkidle")
                                        if not response or not response.ok or probe.url != read_url:
                                            raise ValueError("read failed or redirected")
                                        if task["env"] == "gmail":
                                            goal = await probe.get_by_role("button", name="Unstar " + label, exact=True).count() == 1
                                        else:
                                            links = await probe.get_by_role("main").locator("a[href]:visible").evaluate_all(
                                                "els=>els.map(e=>({url:e.href,label:e.innerText.trim()}))")
                                            goal = {"url": identity, "label": label} in links
                                        row["reads"].append({"url": probe.url, "goal_observed": goal})
                                        return goal
                                    finally:
                                        await probe.close()

                                def build():
                                    if arm == "fresh_exact_check":
                                        return FreshCheck(read_goal)
                                    if arm == "candidate":
                                        return RecoveryLedger(path)
                                    return Journal(path, resources=arm == "resource_journal", read_goal=read_goal)

                                runner = build()

                                async def click_once():
                                    row["callbacks"] += 1
                                    await button.click()
                                    await page.wait_for_load_state("networkidle")

                                async def lost_ack():
                                    await click_once()
                                    raise ConnectionError("injected caller acknowledgement loss after UI action")

                                try:
                                    await runner.execute(intents[0], lost_ack)
                                except ConnectionError:
                                    row["attempts"].append({"status": "injected_ack_loss"})
                                runner = build()  # reopen persistent storage; component has no old Python state
                                resumed = await runner.execute(intents[1], click_once)
                                row["attempts"].append({"status": resumed["status"]})
                                # Read-only reconciliation for the original intent. Never releases its fence.
                                async def read_with_evidence():
                                    goal = await read_goal()
                                    return goal, row["reads"][-1]

                                receipt = await runner.reconcile(intents[0], read_with_evidence)
                                row.update(status="completed", receipt=receipt,
                                           final_goal_observed=receipt["goal_observed"],
                                           source_document_preserved=await body.evaluate("e=>e.isConnected"),
                                           source_url_preserved=page.url == actor_url,
                                           remaining_pages=len(context.pages))
                                if arm == "candidate":
                                    row["ledger_events"] = runner.events()
                            except Exception as exc:  # noqa: BLE001 -- all fixed cells retained
                                row.update(status="error", error=type(exc).__name__ + ": " + str(exc))
                            finally:
                                await context.close()
                            rows.append(row)
                            with (output / "rows.jsonl").open("a") as stream:
                                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                            print(task["env"], condition, arm, row["status"], row["callbacks"], row.get("final_goal_observed"), flush=True)
        finally:
            await browser.close()
    (output / "result.json").write_text(json.dumps({
        "scope": "16 scripted browser recovery checks, two previously used development surfaces; no model or official score",
        "upstream": manifest["upstream"], "seed": manifest["seed"],
        "sources": {str(s.relative_to(ROOT)): hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
        "rows": rows}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args().output))
