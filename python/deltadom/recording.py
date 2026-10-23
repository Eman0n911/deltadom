"""Opt-in local recording; no uploads and no model/action changes."""

import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from .hook import DeltaBrowser
from .runtime import launch_browser
from .tape import SnapshotTooLarge, TapeError, TapeWriter, read_tape


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class BrowserUseRecorder:
    """Browser Use 0.13.11 callback; oversized steps become explicit omission records.

    Opt in on synthetic/public test data first. Messages can contain screenshots,
    passwords or page content. This is a diagnostic copy, not provider wire usage.
    """

    def __init__(self, path):
        self.tape = TapeWriter(path)

    async def on_step_end(self, agent):
        manager = agent._message_manager
        messages = manager.last_input_messages
        if messages is None:
            raise ValueError("Browser Use has no recorded model input for this step")
        # Copy only: preserve the actual model/action instances and their identities.
        snapshot = dump(
            {
                "source": "browser-use-model-boundary",
                "step": agent.state.n_steps,
                "messages": [m.model_dump(mode="json") for m in messages],
                "model_output": (
                    agent.state.last_model_output.model_dump(mode="json")
                    if agent.state.last_model_output
                    else None
                ),
                "action_results": [
                    r.model_dump(mode="json") for r in (agent.state.last_result or [])
                ],
            }
        )
        try:
            self.tape.add(snapshot)
        except SnapshotTooLarge as exc:
            # Size rejection is atomic. Preserve the step without changing the agent's
            # messages, raising into its awaited callback, or pretending we saved them.
            self.tape.add(
                dump(
                    {
                        "source": "browser-use-model-boundary",
                        "step": agent.state.n_steps,
                        "status": "omitted",
                        "reason": "snapshot_too_large",
                        "message_count": len(messages),
                        "raw_bytes": exc.raw_bytes,
                        "limit_bytes": exc.limit_bytes,
                    }
                )
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        self.tape.close(complete=exc_type is None)


async def record_page(url, output, *, count=20, interval=1.0, channel="auto", headless=False):
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("record URL must start with http:// or https://")
    if not 1 <= count <= 10000 or not 0.1 <= interval <= 60:
        raise ValueError("count must be 1..10000; interval must be 0.1..60 seconds")
    with TapeWriter(output) as tape:
        async with async_playwright() as p:
            browser, _ = await launch_browser(p, channel, headless=headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                async with DeltaBrowser(page) as delta:
                    for i in range(count):
                        obs = await delta.observe()
                        entry = tape.add(
                            dump(
                                {
                                    "source": "deltadom",
                                    "document": obs.frame["document"],
                                    "url": obs.frame["url"],
                                    "nodes": obs.nodes,
                                    "settle": obs.settle,
                                    "warnings": obs.warnings,
                                }
                            )
                        )
                        print(
                            f"{entry.seq:>4} | {len(obs.nodes):>5} nodes | {entry.stored_bytes:>6} bytes | {entry.kind}",
                            flush=True,
                        )
                        if i + 1 < count:
                            await asyncio.sleep(interval)
            finally:
                await browser.close()
    print(f"Saved {count} snapshots: {output}")


def inspect_tape(path, *, step=None, output=None, recover=False):
    count, raw_bytes, selected = 0, 0, None
    omitted_snapshots = 0
    kinds = {"F": 0, "D": 0, "R": 0}
    complete, error = True, None
    try:
        for entry in read_tape(path):
            count += 1
            raw_bytes += len(entry.text.encode("utf-8"))
            kinds[entry.kind] += 1
            try:
                record = json.loads(entry.text)
            except (ValueError, RecursionError):
                record = None  # TapeWriter also accepts arbitrary text.
            if (
                isinstance(record, dict)
                and record.get("source") == "browser-use-model-boundary"
                and record.get("status") == "omitted"
            ):
                omitted_snapshots += 1
            if entry.seq == step:
                selected = entry.text
    except TapeError as exc:
        if not recover or not exc.incomplete:
            raise
        complete, error = False, str(exc)
    # Do not export a verified-looking snapshot until the entire tape is checked.
    if step is not None and selected is None:
        raise ValueError(f"step {step} does not exist (recording has {count} steps)")
    if output is not None:
        if selected is None:
            raise ValueError("--output requires --step")
        with Path(output).open("x", encoding="utf-8", newline="") as f:
            f.write(selected)
    return {
        "verified": complete,
        "complete": complete,
        "recovered_prefix": not complete,
        "error": error,
        "snapshots": count,
        "omitted_snapshots": omitted_snapshots,
        "raw_bytes": raw_bytes,
        "file_bytes": Path(path).stat().st_size,
        "encodings": kinds,
        "exported_step": step if output is not None else None,
    }


def diff_tape(path, before, after):
    if before < 1 or after <= before:
        raise ValueError("require 1 <= before < after")
    snapshots = {}
    for entry in read_tape(path):
        if entry.seq in {before, after}:
            snapshots[entry.seq] = entry.text
    if len(snapshots) != 2:
        raise ValueError("requested steps do not exist")
    from difflib import unified_diff

    left, right = snapshots[before], snapshots[after]
    try:
        a, b = json.loads(left), json.loads(right)
        if isinstance(a, dict) and isinstance(b, dict) and "nodes" in a and "nodes" in b:
            old = {n["id"]: n for n in a["nodes"]}
            new = {n["id"]: n for n in b["nodes"]}
            context = {
                k: {"before": a.get(k), "after": b.get(k)}
                for k in sorted((a.keys() | b.keys()) - {"nodes"})
                if a.get(k) != b.get(k)
            }
            if a.get("document") != b.get("document"):
                return {
                    "before": before,
                    "after": after,
                    "document_changed": True,
                    "added": sorted(new),
                    "removed": sorted(old),
                    "changed": [],
                    "context": context,
                }
            changed = [
                {
                    "id": i,
                    "fields": {
                        k: {"before": old[i].get(k), "after": new[i].get(k)}
                        for k in old[i].keys() | new[i].keys()
                        if old[i].get(k) != new[i].get(k)
                    },
                }
                for i in sorted(old.keys() & new.keys())
                if old[i] != new[i]
            ]
            return {
                "before": before,
                "after": after,
                "added": sorted(new.keys() - old.keys()),
                "removed": sorted(old.keys() - new.keys()),
                "changed": changed,
                "context": context,
            }
        left, right = (
            json.dumps(a, ensure_ascii=False, indent=2),
            json.dumps(b, ensure_ascii=False, indent=2),
        )
    except (ValueError, TypeError, KeyError):
        pass
    return {
        "before": before,
        "after": after,
        "lines": list(
            unified_diff(
                left.splitlines(),
                right.splitlines(),
                fromfile=f"step {before}",
                tofile=f"step {after}",
            )
        ),
    }
