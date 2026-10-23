"""Fixed no-model fault matrix; component diagnostics, NOT BreakingWeb scores."""
import argparse
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

from deltadom.recovery import RecoveryLedger, WriteIntent
from recovery_controls import FreshCheck, Journal

ROOT = Path(__file__).resolve().parents[1]
CASES = ["normal", "loss_before_dispatch", "loss_after_remote_commit", "commit_hidden",
         "same_id_concurrent", "new_id_concurrent", "unrelated_object", "payload_conflict",
         "delayed_old_verification", "read_error", "negative_after_unknown", "cancellation"]
ARMS = ["fresh_exact_check", "request_journal", "resource_journal", "candidate"]


async def run_case(case, arm, directory):
    effects, events = [], []
    visible = {"record-A": False, "record-B": False}
    reads = 0
    path = directory / (case + arm + ".sqlite")
    original = WriteIntent("op-1", "record-A", {"starred": True})
    replanned = WriteIntent("op-2", "record-A", {"starred": True})

    async def read_goal(intent):
        nonlocal reads
        reads += 1
        return visible[intent.resource] == intent.effect["starred"]

    def build():
        if arm == "fresh_exact_check":
            return FreshCheck(read_goal)
        if arm == "candidate":
            return RecoveryLedger(path)
        return Journal(path, resources=arm == "resource_journal")

    runner = build()
    callback_calls = []

    async def effect(intent=original, *, hide=False):
        callback_calls.append(intent.operation_id)
        effects.append(intent.resource)
        if not hide:
            visible[intent.resource] = intent.effect["starred"]
        events.append({"event": "effect", "resource": intent.resource, "hidden_from_UI": hide})

    async def uncertain():
        await effect(hide=case in {"commit_hidden", "unrelated_object"})
        raise ConnectionError("caller lost response")

    async def attempt(intent, callback):
        nonlocal runner
        try:
            result = await runner.execute(intent, callback)
        except (ConnectionError, ValueError) as exc:
            result = {"status": type(exc).__name__}
        events.append({"event": "attempt_result", "id": intent.operation_id,
                       "status": result["status"]})
        return result

    confirmation = None
    if case in {"normal", "loss_before_dispatch"}:
        if case == "loss_before_dispatch":
            runner.prepare(original)
            runner = build()
        await attempt(original, effect)
        await attempt(original, effect)
    elif case in {"loss_after_remote_commit", "commit_hidden", "unrelated_object"}:
        await attempt(original, uncertain)
        runner = build()
        if case == "unrelated_object":
            other = WriteIntent("op-2", "record-B", {"starred": True})
            await attempt(other, lambda: effect(other))
        else:
            await attempt(replanned, effect)
    elif case in {"same_id_concurrent", "new_id_concurrent"}:
        release, started, second_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def blocked_effect():
            callback_calls.append("concurrent")
            events.append({"event": "callback_entered"})
            started.set()
            await release.wait()
            effects.append("record-A")
            visible["record-A"] = True

        first = asyncio.create_task(attempt(original, blocked_effect))
        await started.wait()

        async def second():
            second_entered.set()
            return await attempt(original if case == "same_id_concurrent" else replanned,
                                 blocked_effect)

        two = asyncio.create_task(second())
        await second_entered.wait()
        release.set()
        await asyncio.gather(first, two)
    elif case == "payload_conflict":
        await attempt(original, lambda: effect(hide=True))
        changed = WriteIntent("op-1", "record-A", {"starred": False})
        # The fresh exact checker sees the requested false state and skips safely.
        # Force a valid different unsatisfied goal on a different resource instead.
        changed = WriteIntent("op-1", "record-B", {"starred": True})
        await attempt(changed, lambda: effect(changed))
    elif case == "delayed_old_verification":
        await attempt(original, effect)
        ticket = runner.begin_read(original)
        runner.settle(original, reason="fixture confirms prior operation terminal")
        changed = WriteIntent("op-2", "record-A", {"starred": False})
        await attempt(changed, lambda: effect(changed))
        confirmation = runner.finish_read(ticket, goal_observed=True,
                                           evidence={"captured_before_second_intent": True})
        events.append({"event": "old_read_completion", "result": confirmation})
    elif case == "read_error":
        await attempt(original, effect)

        async def broken():
            raise TimeoutError()

        confirmation = await runner.reconcile(original, broken)
        events.append({"event": "read_error_result", "result": confirmation})
    elif case == "negative_after_unknown":
        async def never_committed():
            callback_calls.append("failed_before_remote_effect")
            raise ConnectionError("indistinguishable to caller from lost acknowledgement")

        await attempt(original, never_committed)
        runner = build()
        await attempt(replanned, effect)
    elif case == "cancellation":
        started = asyncio.Event()

        async def submitted():
            callback_calls.append("submitted")
            effects.append("record-A")  # server committed, UI remains behind
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(runner.execute(original, submitted))
        await started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            events.append({"event": "caller_cancelled_after_submit"})
        runner = build()
        await attempt(replanned, effect)

    duplicates = max(0, effects.count("record-A") - (2 if case == "delayed_old_verification" else 1))
    invalid_binding = case == "payload_conflict" and "record-B" in effects
    false_confirmation = bool(confirmation and confirmation.get("goal_observed") is True
                              and case == "delayed_old_verification")
    expected_effects = 2 if case in {"unrelated_object", "delayed_old_verification"} else 1
    complete = len(effects) == expected_effects and not duplicates and not invalid_binding
    row = {"case": case, "arm": arm, "callback_calls": len(callback_calls),
           "effects": effects, "duplicate_effects": duplicates,
           "invalid_binding_admitted": invalid_binding, "false_confirmation": false_confirmation,
           "desired_effect_count_reached": complete, "pre_action_UI_reads": reads,
           "events": events}
    if arm == "candidate":
        row["ledger_events"] = runner.events()
    return row


async def main(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), ROOT / "benchmarks/recovery_controls.py",
               ROOT / "python/deltadom/recovery.py"]
    for source in sources:
        (output / source.name).write_bytes(source.read_bytes())
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in CASES:
            for arm in ARMS:
                row = await run_case(case, arm, Path(tmp))
                rows.append(row)
                with (output / "rows.jsonl").open("a") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {}
    for arm in ARMS:
        group = [r for r in rows if r["arm"] == arm]
        summary[arm] = {"cells": len(group),
                        "duplicate_effects": sum(r["duplicate_effects"] for r in group),
                        "invalid_binding_admissions": sum(r["invalid_binding_admitted"] for r in group),
                        "false_confirmations": sum(r["false_confirmation"] for r in group),
                        "desired_effect_count_reached": sum(r["desired_effect_count_reached"] for r in group)}
    result = {"scope": "12 constructed deterministic fault cases x 4 arms, no model; not task scores",
              "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "summary": summary, "rows": rows}
    (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args().output))
