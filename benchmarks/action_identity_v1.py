"""Controlled local action-identity falsifier, without model calls."""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import time
from importlib.metadata import version
from pathlib import Path

from deltadom import DeltaBrowser, StaleObservationError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = """<!doctype html><title>Identity diagnostic</title>
<p id="outside">0</p><main>
<article id="row"><span class="entity">Invoice A</span>
<span class="amount">100</span><span class="updated">Updated 0</span>
<button>Approve</button></article>
<article id="other"><span class="entity">Invoice C</span>
<span class="amount">100</span><span class="updated">Updated 0</span>
<button>Approve</button></article></main>
<script>
window.actions = []; window.hiddenOverride = null;
document.addEventListener('click', event => {
  if (event.target.tagName !== 'BUTTON') return;
  const row = event.target.closest('article');
  window.actions.push({entity: window.hiddenOverride || row.querySelector('.entity').textContent,
    amount: row.querySelector('.amount').textContent});
});
</script>"""

# Fixed before execution; every branch receives the same mutation and task.
CASES = {
    "unchanged": ("() => {}", True),
    "entity_swap": ("() => document.querySelector('#row .entity').textContent='Invoice B'", False),
    "amount_change": ("() => document.querySelector('#row .amount').textContent='900'", False),
    "outside_ticker": ("() => document.querySelector('#outside').textContent='1'", True),
    "inside_ticker": ("() => document.querySelector('#row .updated').textContent='Updated 1'", True),
    "row_remount": ("() => {const r=document.querySelector('#row');r.replaceWith(r.cloneNode(true));}", True),
    "row_reorder": ("() => document.querySelector('main').prepend(document.querySelector('#other'))", True),
    "invisible_meaning_change": ("() => window.hiddenOverride='Invoice B'", False),
}
ARMS = ("deltadom_target", "whole_page_guard", "row_guard", "semantic_locator")


def subtree(nodes, root):
    included, result = {root}, []
    for node in nodes:
        if node["id"] == root or node["parent"] in included:
            included.add(node["id"])
            result.append(node)
    return result


async def trial(browser, case, arm):
    page = await browser.new_page()
    try:
        await page.set_content(HTML)
        async with DeltaBrowser(page, timeout_ms=300) as delta:
            observed = await delta.observe()
            row_id = observed.find(attr=("id", "row"))[0]["id"]
            button = next(n for n in subtree(observed.nodes, row_id) if n["tag"] == "button")
            # Bind the task using visible exact text, with no hidden evaluator data.
            locator = page.get_by_role("article").filter(
                has=page.get_by_text("Invoice A", exact=True)
            ).filter(has=page.get_by_text("100", exact=True)).get_by_role(
                "button", name="Approve", exact=True
            )
            await page.evaluate(CASES[case][0])
            after = await delta._capture()
            error = None
            started = time.perf_counter()
            try:
                if arm == "semantic_locator":
                    await locator.click(timeout=300)
                else:
                    if arm == "whole_page_guard" and list(observed.nodes) != after["nodes"]:
                        raise StaleObservationError("experimental whole-page guard")
                    if arm == "row_guard" and subtree(observed.nodes, row_id) != subtree(after["nodes"], row_id):
                        raise StaleObservationError("experimental row guard")
                    await delta.act(observed, button["id"], "click")
            except (StaleObservationError, PlaywrightError) as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
            elapsed_ms = (time.perf_counter() - started) * 1000
            actions = await page.evaluate("window.actions")
            if actions:
                outcome = "correct_action" if actions == [{"entity": "Invoice A", "amount": "100"}] else "wrong_action"
            else:
                outcome = "blocked_valid" if CASES[case][1] else "blocked_invalid"
            return {
                "case": case, "arm": arm, "valid_target_available": CASES[case][1],
                "outcome": outcome, "actions": actions, "error": error,
                "action_elapsed_ms_diagnostic_only": round(elapsed_ms, 3),
                "observed_nodes": observed.nodes, "after_nodes": after["nodes"],
            }
    finally:
        await page.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "fixture.html").write_text(HTML)
    rows = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel=os.environ.get("DELTADOM_CHANNEL"))
        browser_version = browser.version
        try:
            for case in CASES:
                for arm in ARMS:
                    row = await trial(browser, case, arm)
                    (args.output / f"{case}-{arm}.json").write_text(json.dumps(row, indent=2) + "\n")
                    rows.append({k: v for k, v in row.items() if k not in {"observed_nodes", "after_nodes"}})
        finally:
            await browser.close()
    outcomes = ("correct_action", "wrong_action", "blocked_valid", "blocked_invalid")
    summary = {arm: {o: sum(r["arm"] == arm and r["outcome"] == o for r in rows) for o in outcomes} for arm in ARMS}
    bound_files = [Path(__file__), ROOT / "benchmarks/IDENTITY-PROTOCOL.md",
                   ROOT / "python/deltadom/hook.py", ROOT / "python/deltadom/snapshot.js"]
    report = {
        "scope": "8 local deterministic diagnostic fixtures, 4 branches, no models; not a mainstream agent benchmark",
        "versions": {"python": platform.python_version(), "playwright": version("playwright"),
                     "deltadom": version("deltadom"), "browser": browser_version},
        "git_base": (await asyncio.to_thread(
            subprocess.check_output, ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        )).strip(),
        "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in bound_files},
        "not_run": ["models", "Browser Use actor", "Stagehand actor", "agent-browser actor",
                    "automatic task constraint generation", "action-time races", "held-out sites"],
        "summary": summary, "rows": rows,
    }
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
