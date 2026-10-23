import base64
import json
import random
import struct
from types import SimpleNamespace

import pytest
from deltadom.demo import fixture_server
from deltadom.recording import BrowserUseRecorder, inspect_tape, record_page
from deltadom.tape import HEADER, MAGIC, MAX_BYTES, TapeError, TapeWriter, read_tape


def test_tape_roundtrip_checkpoints_and_full_fallback(tmp_path):
    rng = random.Random(42)
    text = "商品列表\n" + "\n".join(f"{i}: item {i} [{i * 7}]" for i in range(200))
    snapshots = [text, text, text.replace("item 83", "updated 83")]
    snapshots += ["".join(chr(rng.randint(32, 126)) for _ in range(1000)) for _ in range(3)]
    snapshots += ["", "", text]
    path = tmp_path / "run.ddt"
    with TapeWriter(path, checkpoint_interval=4) as w:
        rows = [w.add(s) for s in snapshots]
    assert [r.text for r in read_tape(path)] == snapshots
    assert rows[1].kind == "R"
    assert rows[2].kind == "D"
    assert rows[4].kind == rows[8].kind == "F"
    assert rows[3].kind == "F"  # unrelated content must fall back to full
    assert inspect_tape(path)["snapshots"] == 9
    with pytest.raises(FileExistsError):
        TapeWriter(path)
    target = tmp_path / "step.txt"
    inspect_tape(path, step=3, output=target)
    assert target.read_text() == snapshots[2]
    with pytest.raises(FileExistsError):
        inspect_tape(path, step=3, output=target)


def test_tape_damage_truncation_reordering_and_bounded_decode(tmp_path):
    path = tmp_path / "run.ddt"
    with TapeWriter(path) as w:
        w.add("hello " * 1000)
        w.add("hello " * 999 + "world ")
    data = path.read_bytes()
    # Every truncation, including a complete-record boundary, lacks a valid seal.
    for i in range(len(data)):
        broken = tmp_path / "broken.ddt"
        broken.write_bytes(data[:i])
        with pytest.raises(TapeError):
            list(read_tape(broken))
    for position in [0, len(MAGIC), len(MAGIC) + HEADER.size, len(data) - 1]:
        changed = bytearray(data)
        changed[position] ^= 1
        broken.write_bytes(changed)
        with pytest.raises(TapeError):
            list(read_tape(broken))
    # Lie about decoded length: decoder must not expand all input before checking.
    changed = bytearray(data)
    struct.pack_into(">I", changed, len(MAGIC) + 9, 1)
    broken.write_bytes(changed)
    with pytest.raises(TapeError):
        list(read_tape(broken))
    broken.write_bytes(data + b"extra")
    with pytest.raises(TapeError):
        inspect_tape(broken, step=1, output=tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


def test_failed_recording_is_not_sealed(tmp_path):
    path = tmp_path / "failed.ddt"
    with pytest.raises(RuntimeError), TapeWriter(path) as writer:
        writer.add("record before failure")
        raise RuntimeError("failed run")
    with pytest.raises(TapeError, match="incomplete"):
        list(read_tape(path))


@pytest.mark.asyncio
async def test_record_real_browser_and_replay_offline(tmp_path):
    path = tmp_path / "page.ddt"
    with fixture_server() as url:
        await record_page(url, path, count=3, interval=0.1, headless=True)
    rows = list(read_tape(path))
    assert len(rows) == 3
    assert all(json.loads(row.text)["nodes"] for row in rows)
    assert inspect_tape(path)["verified"]


@pytest.mark.asyncio
async def test_browser_use_callback_copies_complete_inputs_without_mutating(tmp_path):
    # Contract test only. No model trial or success claim.
    class Message:
        def __init__(self, data):
            self.data = data

        def model_dump(self, mode):
            assert mode == "json"
            return self.data

    content = {"role": "user", "content": "full current state with [42] button"}
    messages = [Message({"role": "system", "content": "instructions"}), Message(content)]
    agent = SimpleNamespace(
        _message_manager=SimpleNamespace(last_input_messages=messages),
        state=SimpleNamespace(n_steps=1, last_model_output=None, last_result=[]),
    )
    path = tmp_path / "native.ddt"
    with BrowserUseRecorder(path) as recorder:
        await recorder.on_step_end(agent)
    entry = json.loads(next(read_tape(path)).text)
    assert entry["messages"] == [m.data for m in messages]
    assert agent._message_manager.last_input_messages is messages
    assert messages[1].data is content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "steps,screenshot_kib,omitted", [(40, 200, False), (10, 800, False), (20, 800, True)]
)
async def test_browser_use_screenshot_history_does_not_abort_agent(
    tmp_path, steps, screenshot_kib, omitted
):
    # Exercise the awaited callback with full base64 image messages, not a model trial.
    class Message:
        def __init__(self, content):
            self.content = content

        def model_dump(self, mode):
            return {"role": "user", "content": self.content}

    image = base64.b64encode(b"x" * (screenshot_kib * 1024)).decode("ascii")
    content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}]
    messages = [Message(content) for _ in range(steps)]
    agent = SimpleNamespace(
        _message_manager=SimpleNamespace(last_input_messages=messages),
        state=SimpleNamespace(n_steps=steps, last_model_output=None, last_result=[]),
    )
    path = tmp_path / "history.ddt"
    with BrowserUseRecorder(path) as recorder:
        await recorder.on_step_end(agent)
        assert agent._message_manager.last_input_messages is messages
        assert all(m.content is content for m in messages)
        # Repeated oversize steps must also return, then ordinary recording must resume.
        agent.state.n_steps += 1
        await recorder.on_step_end(agent)
        agent.state.n_steps += 1
        agent._message_manager.last_input_messages = [Message("next step still executes")]
        await recorder.on_step_end(agent)
    rows = [json.loads(row.text) for row in read_tape(path)]
    assert [row["step"] for row in rows] == [steps, steps + 1, steps + 2]
    if omitted:
        for row in rows[:2]:
            assert row["status"] == "omitted"
            assert row["reason"] == "snapshot_too_large"
            assert row["message_count"] == steps
            assert row["raw_bytes"] > row["limit_bytes"] == MAX_BYTES
            assert not {"messages", "model_output", "action_results"} & row.keys()
    else:
        assert rows[0]["messages"] == [m.model_dump(mode="json") for m in messages]
    assert rows[2]["messages"][0]["content"] == "next step still executes"
    report = inspect_tape(path)
    assert report["verified"] and report["complete"]
    assert report["omitted_snapshots"] == (2 if omitted else 0)
    # An unrelated agent failure still leaves an explicitly incomplete, recoverable prefix.
    path.write_bytes(path.read_bytes()[: -HEADER.size])
    recovered = inspect_tape(path, recover=True)
    assert not recovered["complete"] and recovered["recovered_prefix"]
    assert recovered["omitted_snapshots"] == report["omitted_snapshots"]


def test_tape_size_limit_uses_utf8_bytes_and_preserves_writer(tmp_path):
    path = tmp_path / "limit.ddt"
    with TapeWriter(path) as writer:
        writer.add("x" * MAX_BYTES)  # The exact boundary is valid.
        with pytest.raises(ValueError, match="snapshot exceeds 16 MiB"):
            writer.add("界" * (MAX_BYTES // 3 + 1))
        writer.add("after rejected record")
    rows = list(read_tape(path))
    assert len(rows) == 2 and rows[1].text == "after rejected record"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("unrelated writer error"), OSError("disk full")])
async def test_callback_does_not_mislabel_other_errors_as_size_omissions(tmp_path, monkeypatch, error):
    agent = SimpleNamespace(
        _message_manager=SimpleNamespace(last_input_messages=[]),
        state=SimpleNamespace(n_steps=1, last_model_output=None, last_result=[]),
    )
    path = tmp_path / "failed-callback.ddt"

    def fail(_):
        raise error

    with pytest.raises(type(error), match=str(error)), BrowserUseRecorder(path) as recorder:
        await recorder.on_step_end(agent)
        monkeypatch.setattr(recorder.tape, "add", fail)
        await recorder.on_step_end(agent)
    report = inspect_tape(path, recover=True)
    assert report["snapshots"] == 1 and report["omitted_snapshots"] == 0
    assert not report["complete"] and report["recovered_prefix"]


def test_recover_only_verified_prefix_and_diff(tmp_path):
    from deltadom.recording import diff_tape

    path = tmp_path / "run.ddt"
    with TapeWriter(path) as w:
        w.add(json.dumps({"nodes": [{"id": 1, "text": "old"}]}))
        w.add(json.dumps({"nodes": [{"id": 1, "text": "new"}, {"id": 2, "text": "added"}]}))
    diff = diff_tape(path, 1, 2)
    assert diff["added"] == [2]
    assert diff["changed"] == [{"id": 1, "fields": {"text": {"before": "old", "after": "new"}}}]
    path.write_bytes(path.read_bytes()[: -HEADER.size])
    report = inspect_tape(path, recover=True, step=2, output=tmp_path / "recovered.json")
    assert report["snapshots"] == 2
    assert not report["verified"] and report["recovered_prefix"]
    corrupt = bytearray(path.read_bytes())
    corrupt[len(MAGIC) + HEADER.size] ^= 1
    path.write_bytes(corrupt)
    with pytest.raises(TapeError):
        inspect_tape(path, recover=True)


def test_diff_does_not_reuse_ids_across_documents_and_keeps_context(tmp_path):
    from deltadom.recording import diff_tape

    path = tmp_path / "navigation.ddt"
    with TapeWriter(path) as w:
        w.add(json.dumps({"document": "old", "nodes": [{"id": 1, "text": "same"}], "warnings": []}))
        w.add(
            json.dumps(
                {"document": "new", "nodes": [{"id": 1, "text": "same"}], "warnings": ["timeout"]}
            )
        )
    delta = diff_tape(path, 1, 2)
    assert delta["document_changed"]
    assert delta["added"] == delta["removed"] == [1]
    assert delta["changed"] == []
    assert delta["context"]["warnings"]["after"] == ["timeout"]
