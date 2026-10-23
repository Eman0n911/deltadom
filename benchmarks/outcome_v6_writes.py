"""Fixed single-write component checks on two prior development surfaces.

These are manually scripted UI transactions, NOT autonomous agent task scores.
Exactly one write per case, no retries, no evaluator or private state access.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

from deltadom.action_readback import ActionReadback
from outcome_agent import BASE, ROOT, http_json
from playwright.async_api import async_playwright

OUT = ROOT / "artifacts/benchmarks/outcome-v6/single-write.json"


async def fresh_goal(page, url, env, identity):
    probe = await page.context.new_page()
    try:
        await probe.goto(url, wait_until="networkidle")
        if env == "gmail":
            button = probe.get_by_role("button", name="Unstar " + identity["label"], exact=True)
            matched = await button.count() == 1 and await button.is_visible()
        else:
            links = await probe.get_by_role("main").locator("a[href]:visible").evaluate_all(
                "els=>els.map(e=>({url:e.href,label:e.innerText.trim()}))"
            )
            matched = any(e == identity for e in links)
        return {"visible_goal": matched, "url": probe.url}
    finally:
        await probe.close()


async def main(output):
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    frozen = json.loads((ROOT / "artifacts/benchmarks/outcome-v1/manifest.json").read_text())
    tasks = [frozen["dev"][0], frozen["confirmation"][0]]
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        try:
            for task in tasks:
                for condition in ["clean", "intervention"]:
                    for arm in ["explicit_goal_check", "auto-control", "auto-signal"]:
                        row = {"task": task["task_id"], "condition": condition, "arm": arm}
                        context = await browser.new_context()
                        try:
                            params = {"task_id": task["task_id"], "seed": frozen["seed"]}
                            if condition == "intervention":
                                params["variant_filename"] = task["variant"]
                            s = await asyncio.to_thread(http_json, f"/api/env/{task['env']}/session", params)
                            page = await context.new_page()
                            await page.goto(BASE + f"/env/{task['env']}" + s["start_path"] +
                                            f"?session={s['session_id']}&agent_mode=1", wait_until="networkidle")
                            if task["env"] == "gmail":
                                identity = {"label": "Project Update — Q1 Milestones"}
                                goal_url = page.url
                                button = page.get_by_role("button", name="Star " + identity["label"], exact=True)
                            else:
                                await page.get_by_role("link", name="Browse Electronics", exact=True).click()
                                await page.get_by_role("combobox", name="Sort results").select_option(label="Price: Low to High")
                                await page.wait_for_load_state("networkidle")
                                await page.get_by_role("main").locator("a[href*='/product/']:visible").first.click()
                                await page.wait_for_load_state("networkidle")
                                identity = {"url": page.url, "label": (await page.get_by_role("main").locator("h1").inner_text()).strip()}
                                cart = page.locator("a[aria-label^='Shopping cart']")
                                goal_url = urljoin(page.url, await cart.get_attribute("href"))
                                button = page.get_by_role("button", name=f"Add {identity['label']} to Cart", exact=True)
                            before_url = page.url
                            body = await page.query_selector("body")
                            before = await fresh_goal(page, goal_url, task["env"], identity)
                            row.update(identity=identity, initial_goal=before, explicit_write_calls=1)
                            if arm == "explicit_goal_check":
                                await button.click()
                                await page.wait_for_load_state("networkidle")
                                runtime = await fresh_goal(page, goal_url, task["env"], identity)
                            else:
                                _, runtime = await ActionReadback(page).run(button.click, force_read=arm == "auto-control")
                            # This extra controller read is measurement only. Never fed to the component.
                            after = await fresh_goal(page, goal_url, task["env"], identity)
                            row.update(runtime=runtime, independent_ui_check=after,
                                       source_document_preserved=await body.evaluate("e=>e.isConnected"),
                                       source_url_preserved=page.url == before_url,
                                       remaining_pages=len(context.pages), status="completed")
                        except Exception as exc:  # noqa: BLE001 -- retain all 12 cells
                            row.update(status="error", error=type(exc).__name__ + ": " + str(exc))
                        finally:
                            await context.close()
                        rows.append(row)
                        with output.with_suffix(".jsonl").open("a") as stream:
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                        print(task["env"], condition, arm, row["status"], row.get("independent_ui_check", {}).get("visible_goal"), flush=True)
        finally:
            await browser.close()
    sources = [Path(__file__), ROOT / "python/deltadom/action_readback.py", ROOT / "python/deltadom/readback.py"]
    output.write_text(json.dumps({"scope": "12 scripted single-write regression checks, two already-used development surfaces; not model/task scores",
                               "automatic_retries": 0, "upstream": frozen["upstream"],
                               "sources": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
                               "rows": rows}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    asyncio.run(main(parser.parse_args().output))
