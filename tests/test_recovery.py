import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from deltadom.recovery import IntentConflict, RecoveryLedger, WriteIntent


def intent(key="op", resource="account/workflow/message-17/star", **effect):
    return WriteIntent(key, resource, effect or {"starred": True})


async def test_crash_unknown_and_new_ids_cannot_bypass_fence(tmp_path):
    path = tmp_path / "journal.sqlite"
    store = RecoveryLedger(path)
    calls = []

    async def commit_then_disconnect():
        calls.append("committed")
        raise ConnectionError()

    with pytest.raises(ConnectionError):
        await store.execute(intent(), commit_then_disconnect)
    recovered = RecoveryLedger(path)
    assert (await recovered.execute(intent("replan"), commit_then_disconnect))["status"] == "not_dispatched"
    assert (await recovered.execute(intent(), commit_then_disconnect))["status"] == "not_dispatched"
    assert calls == ["committed"]
    ticket = recovered.begin_read(intent())
    negative = recovered.finish_read(ticket, goal_observed=False, evidence={"UI": "not starred"})
    assert not negative["safe_to_retry"] and not negative["resource_released"]
    assert (await recovered.execute(intent("third"), commit_then_disconnect))["status"] == "not_dispatched"


async def test_prepared_recovery_and_independent_work(tmp_path):
    path = tmp_path / "journal.sqlite"
    store = RecoveryLedger(path)
    store.prepare(intent())
    calls = []

    async def action():
        calls.append(1)

    recovered = RecoveryLedger(path)
    assert (await recovered.execute(intent(), action))["status"] == "dispatched_once"
    assert (await recovered.execute(intent("other", "other-record"), action))["status"] == "dispatched_once"
    assert calls == [1, 1]
    with pytest.raises(IntentConflict):
        await recovered.execute(intent(starred=False), action)
    with pytest.raises(IntentConflict):
        await recovered.execute(intent(resource="other"), action)


def test_sqlite_arbitrates_concurrent_process_style_connections(tmp_path):
    path = tmp_path / "journal.sqlite"
    store = RecoveryLedger(path)
    store.prepare(intent())
    with ThreadPoolExecutor(max_workers=8) as pool:
        permits = list(pool.map(lambda _: RecoveryLedger(path).dispatch(intent()), range(16)))
    assert sum(permits) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        decisions = list(pool.map(lambda i: RecoveryLedger(path).prepare(intent(str(i))), range(16)))
    assert all(d["status"] == "blocked" for d in decisions)


async def test_cancel_does_not_reset_admission(tmp_path):
    store = RecoveryLedger(tmp_path / "journal.sqlite")
    started = asyncio.Event()

    async def pending():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(store.execute(intent(), pending))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.inspect("op")["phase"] == "uncertain"
    assert (await store.execute(intent(), pending))["status"] == "not_dispatched"


async def test_evidence_revisions_and_explicit_settlement(tmp_path):
    store = RecoveryLedger(tmp_path / "journal.sqlite")

    async def action():
        pass

    await store.execute(intent(), action)
    old = store.begin_read(intent())
    new = store.begin_read(intent())
    assert store.finish_read(new, goal_observed=False, evidence={})["status"] == "observed"
    assert store.finish_read(old, goal_observed=True, evidence={})["status"] == "stale"
    assert store.finish_read(new, goal_observed=True, evidence={})["status"] == "stale"
    assert store.inspect("op")["observation"]["goal_observed"] is False
    pending = store.begin_read(intent())
    store.settle(intent(), reason="operator has independently established no pending effects")
    assert store.finish_read(pending, goal_observed=True, evidence={})["status"] == "stale"
    assert (await store.execute(intent(), action))["status"] == "not_dispatched"
    assert (await store.execute(intent("next", starred=False), action))["status"] == "dispatched_once"
    # Settling the old record again must not release the new owner's fence.
    store.settle(intent(), reason="repeat operator decision")
    assert (await store.execute(intent("third"), action))["status"] == "not_dispatched"


async def test_read_error_and_callback_completion_invalidate_stale_evidence(tmp_path):
    store = RecoveryLedger(tmp_path / "journal.sqlite")
    started, release = asyncio.Event(), asyncio.Event()

    async def action():
        started.set()
        await release.wait()

    task = asyncio.create_task(store.execute(intent(), action))
    await started.wait()
    ticket = store.begin_read(intent())
    release.set()
    await task
    assert store.finish_read(ticket, goal_observed=True, evidence={})["status"] == "stale"

    async def broken_read():
        raise TimeoutError()

    result = await store.reconcile(intent(), broken_read)
    assert result["goal_observed"] is None and not result["safe_to_retry"]


@pytest.mark.parametrize("phase", ["prepared", "dispatched", "effect"])
async def test_real_process_death_preserves_one_use_permit(tmp_path, phase):
    import os
    import subprocess
    import sys

    path, effect_path = tmp_path / "journal.sqlite", tmp_path / "effect.txt"
    script = '''
import os, sys
from pathlib import Path
from deltadom.recovery import RecoveryLedger, WriteIntent
store = RecoveryLedger(sys.argv[1])
i = WriteIntent("op", "record", {"starred": True})
store.prepare(i)
if sys.argv[3] != "prepared":
    assert store.dispatch(i)
if sys.argv[3] == "effect":
    Path(sys.argv[2]).write_text("remote side effect")
os._exit(19)
'''
    child = await asyncio.to_thread(
        subprocess.run, [sys.executable, "-c", script, str(path), str(effect_path), phase],
        env=os.environ.copy(), check=False
    )
    assert child.returncode == 19
    store = RecoveryLedger(path)
    calls = []

    async def action():
        calls.append(1)

    result = await store.execute(WriteIntent("op", "record", {"starred": True}), action)
    assert bool(calls) == (phase == "prepared")
    assert effect_path.exists() == (phase == "effect")
    if phase == "dispatched":
        # The unavoidable local/remote atomicity gap: blocked even though no effect.
        assert result["status"] == "not_dispatched" and not effect_path.exists()


def test_network_admission_is_durable_bound_and_one_use(tmp_path):
    from deltadom.network_fence import request_signature

    path = tmp_path / "ledger.sqlite"
    store = RecoveryLedger(path)
    write = intent()
    signature = request_signature("POST", "http://local/write", b'{"amount":1}')
    store.prepare(write)
    assert not store.admit_forward(write, signature)  # No callback permit yet.
    assert store.dispatch(write)
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(lambda _: RecoveryLedger(path).admit_forward(write, signature),
                                range(16)))
    assert sum(allowed) == 1
    assert not RecoveryLedger(path).admit_forward(write, signature)
    with pytest.raises(IntentConflict):
        store.admit_forward(intent(starred=False), signature)
    store.settle(write, reason="application-specific terminal confirmation")
    other = request_signature("POST", "http://local/write", b'{"amount":2}')
    assert not store.admit_forward(write, other)


def test_request_identity_preserves_byte_differences():
    from deltadom.network_fence import request_signature

    original = request_signature("POST", "http://local/write", b'{"item":"A"}')
    assert original != request_signature("POST", "http://local/write", b'{ "item":"A" }')
    assert original != request_signature("PUT", "http://local/write", b'{"item":"A"}')
    assert original != request_signature("POST", "http://local/other", b'{"item":"A"}')
    assert original == request_signature("post", "http://local/write", b'{"item":"A"}')


async def test_storage_failure_aborts_route_without_forwarding():
    from deltadom.network_fence import NetworkFence

    class BrokenLedger:
        def admit_forward(self, *_):
            raise OSError("disk unavailable")

    class Request:
        method, url, post_data_buffer = "POST", "http://local/write", b"payload"

    class Route:
        request = Request()
        forwarded, aborted = False, False

        async def continue_(self):
            self.forwarded = True

        async def abort(self, reason):
            self.aborted = reason

    route = Route()
    fence = NetworkFence(None, BrokenLedger(), intent(), origin="http://local")
    await fence._route(route)
    assert route.aborted == "blockedbyclient" and not route.forwarded
    assert fence.decisions == [{"admitted": False, "error": "OSError"}]


async def test_forward_permit_survives_actual_process_exit(tmp_path):
    import os
    import subprocess
    import sys

    from deltadom.network_fence import request_signature

    path = tmp_path / "ledger.sqlite"
    script = '''
import os, sys
from deltadom import RecoveryLedger, WriteIntent
from deltadom.network_fence import request_signature
s=RecoveryLedger(sys.argv[1]); i=WriteIntent("op", "record", {"submit": True})
s.prepare(i); assert s.dispatch(i)
assert s.admit_forward(i, request_signature("POST", "http://local/write", b"body"))
os._exit(19)
'''
    child = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", script, str(path)],
                                    env=os.environ.copy(), check=False)
    assert child.returncode == 19
    store = RecoveryLedger(path)
    assert not store.admit_forward(WriteIntent("op", "record", {"submit": True}),
                                   request_signature("POST", "http://local/write", b"body"))
