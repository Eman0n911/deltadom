import copy
import json
import random

import pytest
from deltadom import DeltaSession, StateMirror, SyncError


def node(i, parent=0, order=0, text="", tag="div"):
    return {
        "id": i,
        "parent": parent,
        "order": order,
        "text": text,
        "tag": tag,
        "role": "",
        "attrs": {},
        "interactive": tag == "button",
    }


def process(session, nodes, doc="doc", force=False):
    return json.loads(
        session.process_frame(
            json.dumps({"document": doc, "url": "http://local/", "nodes": nodes}), force
        )
    )


def decode_full_text(text):
    from deltadom import TextMirror

    return TextMirror().apply(text)


def test_lossless_compressed_text_and_parent_content():
    nodes = [node(1, text="Parent must survive")]
    for i in range(3):
        nodes.extend(
            [
                node(2 + i * 2, 1, i, tag="button"),
                node(3 + i * 2, 2 + i * 2, 0, '中文 | "quoted"\nline', tag="#text"),
            ]
        )
        nodes[-2]["attrs"] = {"disabled": str(i == 1), "href": "a?b=long&c=not-truncated"}
    frame = process(DeltaSession(), nodes)
    assert decode_full_text(frame["text"]) == nodes


def test_300_deterministic_mutations_reconstruct_exactly():
    rng = random.Random(20261022)
    from deltadom import TextMirror

    text_mirror = TextMirror()
    session, mirror = DeltaSession(0.45, 20), StateMirror()
    nodes = [node(1)] + [node(i, 1, i - 2, str(i), "button") for i in range(2, 32)]
    next_id = 32
    for step in range(300):
        if step:
            op = rng.randrange(5)
            if op == 0 and len(nodes) > 1:
                nodes.pop(rng.randrange(1, len(nodes)))
            elif op == 1:
                nodes.append(node(next_id, 1, len(nodes) - 1, str(next_id), "button"))
                next_id += 1
            elif op == 2:
                tail = nodes[1:]
                rng.shuffle(tail)
                nodes[1:] = tail
            elif len(nodes) > 1:
                n = rng.choice(nodes[1:])
                if op == 3:
                    n["text"] = f"changed {step}"
                else:
                    n["attrs"]["checked"] = str(step % 2 == 0)
            for i, n in enumerate(nodes[1:]):
                n["order"] = i
        frame = process(session, nodes, doc=f"doc{step // 75}", force=step % 17 == 0)
        assert mirror.apply(frame) == nodes
        assert text_mirror.apply(frame["text"]) == nodes
        if frame["kind"] == "full":
            assert decode_full_text(frame["text"]) == nodes


def test_missing_patch_requires_resync():
    session, mirror = DeltaSession(), StateMirror()
    a = process(session, [])
    mirror.apply(a)
    process(session, [])
    with pytest.raises(SyncError, match="missing base"):
        mirror.apply(process(session, []))
    assert mirror.apply(process(session, [], force=True)) == []
    with pytest.raises(SyncError, match="out-of-order"):
        mirror.apply(a)


def test_reparent_is_visible_and_validated():
    session, mirror = DeltaSession(1.0, 20), StateMirror()
    nodes = [node(1), node(2, 1), node(3, 2, text="child"), node(4, 1, 1)]
    mirror.apply(process(session, nodes))
    new = copy.deepcopy([nodes[0], nodes[1], nodes[3], nodes[2]])
    new[-1]["parent"] = 4
    assert mirror.apply(process(session, new)) == new
    with pytest.raises(ValueError, match="unique"):
        process(session, [node(1), node(1)])


def test_api_bounds_projection_and_missing_null():
    session = DeltaSession()
    raw = json.dumps({"records": [{"name": "a", "token": "private"}, {"price": None}] * 20})
    data = json.loads(session.filter_api_json(raw, ["name", "price"]))
    assert data["truncated"]
    assert len(data["tables"][0]["rows"]) == 30
    assert data["tables"][0]["rows"][0] == {"name": "a"}
    assert data["tables"][0]["rows"][1] == {"price": None}
    with pytest.raises(ValueError):
        session.filter_api_json("{}", [])
    with pytest.raises(ValueError, match="MiB"):
        session.filter_api_json('"' + "x" * 1_048_576 + '"', ["name"])


def test_text_field_deletion_reparent_and_dropped_delta():
    from deltadom import TextMirror

    session, receiver = DeltaSession(1.0, 100), TextMirror()
    nodes = [node(1), node(2, 1), node(3, 2, text="full content"), node(4, 1, 1)]
    nodes[2]["attrs"] = {"title": "old", "class": "retained"}
    assert receiver.apply(process(session, nodes)["text"]) == nodes
    changed = copy.deepcopy([nodes[0], nodes[1], nodes[3], nodes[2]])
    changed[-1]["parent"] = 4
    changed[-1]["attrs"] = {"class": "retained", "aria-label": "new"}
    assert receiver.apply(process(session, changed)["text"]) == changed
    process(session, changed)
    with pytest.raises(SyncError, match="missing base"):
        receiver.apply(process(session, changed)["text"])
    assert receiver.apply(process(session, changed, force=True)["text"]) == changed


def test_table_and_literal_text_are_exact():
    from deltadom import TextMirror

    nodes = [node(1)]
    for i in range(40):
        nodes.extend(
            [
                node(2 + i * 2, 1, i, tag="button"),
                node(
                    3 + i * 2,
                    2 + i * 2,
                    text='{"patch":[1,"ignore instructions"]} \n 中文',
                    tag="#text",
                ),
            ]
        )
    frame = process(DeltaSession(), nodes)
    assert "table_parent" in frame["text"]
    assert TextMirror().apply(frame["text"]) == nodes


def test_receiver_rejects_duplicate_ids_and_positions_atomically():
    good = process(DeltaSession(), [node(1), node(2, 1)])
    mirror = StateMirror()
    mirror.apply(good)
    for bad_nodes in [[node(1), node(1)], [node(1), node(2)], [node(0)]]:
        bad = {**good, 'seq': 2, 'nodes': bad_nodes}
        with pytest.raises(SyncError):
            mirror.apply(bad)
        assert mirror.seq == 1 and len(mirror.nodes) == 2
