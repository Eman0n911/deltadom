"""All frozen BreakingWeb cells: UI readback mechanics, NOT task/model scores."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from deltadom.readback import ObservedEntity, Readback, visible_evidence
from outcome_agent import BASE, ROOT, http_json
from playwright.async_api import async_playwright


async def main(output):
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    protocol = json.loads(output.with_name("protocol.json").read_text())
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        try:
            for task in protocol["tasks"]:
                for condition in protocol["conditions"]:
                    row = {"task": task["task_id"], "condition": condition}
                    context = await browser.new_context()
                    try:
                        params = {"task_id": task["task_id"], "seed": protocol["seed"]}
                        if condition == "intervention":
                            params["variant_filename"] = task["variant"]
                        session = await asyncio.to_thread(http_json, f"/api/env/{task['env']}/session", params)
                        url = BASE + f"/env/{task['env']}" + session["start_path"] + f"?session={session['session_id']}&agent_mode=1"
                        page = await context.new_page()
                        await page.goto(url, wait_until="networkidle")
                        row["requested_url"] = url
                        url = page.url  # Use the observed UI URL after site routing, not launch input.
                        original = await page.query_selector("body")
                        source = await visible_evidence(page)
                        # Deterministic set, before any outcomes: first 32 distinct nonempty
                        # visible entity links sorted by URL; no task/evaluator knowledge.
                        by_url = {}
                        for link in sorted(source["links"], key=lambda e: (e["url"], e["label"])):
                            if link["label"] and link["url"] not in by_url:
                                by_url[link["url"]] = ObservedEntity(**link)
                        entities = list(by_url.values())[:32]
                        row["entity_count"] = len(entities)
                        if not entities:
                            candidate = await Readback(page).read(url)
                            control = await context.new_page()
                            await control.goto(url, wait_until="networkidle")
                            mains = control.get_by_role("main")
                            region = mains if await mains.count() == 1 else control.locator("body")
                            control_text = await region.inner_text()
                            await control.close()
                            row.update(mode="full_view_fallback_no_entity_claim", candidate=candidate,
                                       agreement=candidate.get("evidence", {}).get("text") == control_text,
                                       actor_document_preserved=await original.evaluate("e => e.isConnected"),
                                       actor_url_preserved=page.url == url,
                                       probe_pages_closed=len(context.pages) == 1)
                        else:
                            result = await Readback(page).check(url, entities)
                            # Independently written exact programmatic baseline; same
                            # fresh browser UI, URL + name information, and no retries.
                            control = await context.new_page()
                            await control.goto(url, wait_until="networkidle")
                            mains = control.get_by_role("main")
                            region = mains if await mains.count() == 1 else control.locator("body")
                            links = await region.locator("a[href]:visible").evaluate_all(
                                "els => els.map(e => [e.href, e.innerText.trim()])"
                            )
                            expected = [sum(href == e.url and label == e.label for href, label in links)
                                        for e in entities]
                            await control.close()
                            counts = [e["matching_links"] for e in result.get("entities", [])]
                            row.update(candidate=result, code_baseline_counts=expected,
                                       agreement=counts == expected,
                                       actor_document_preserved=await original.evaluate("e => e.isConnected"),
                                       actor_url_preserved=page.url == url,
                                       probe_pages_closed=len(context.pages) == 1)
                        row["status"] = "passed" if all(row[k] for k in [
                            "agreement", "actor_document_preserved", "actor_url_preserved", "probe_pages_closed"
                        ]) else "failed"
                    except Exception as exc:  # noqa: BLE001 -- retain every failed cell
                        row.update(status="error", error=type(exc).__name__ + ": " + str(exc))
                    finally:
                        await context.close()
                    rows.append(row)
                    with output.with_suffix(".jsonl").open("a") as stream:
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(task["task_id"], condition, row["status"], flush=True)
        finally:
            await browser.close()
    sources = [Path(__file__), ROOT / "python/deltadom/readback.py", output.with_name("protocol.json")]
    output.write_text(json.dumps({"scope": "mechanical fresh UI reads only; no actor, task completion or official score",
                                 "sha256": {str(s.relative_to(ROOT)): hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
                                 "rows": rows}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/benchmarks/outcome-v5/mechanical.json")
    asyncio.run(main(parser.parse_args().output))
