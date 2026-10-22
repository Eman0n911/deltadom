"""Receiver-side protocol guard: lost / reordered deltas require a full frame."""

from copy import deepcopy


class SyncError(ValueError):
    pass


class StateMirror:
    def __init__(self):
        self.document = None
        self.seq = 0
        self.nodes = {}

    def apply(self, frame: dict) -> list[dict]:
        if frame.get("version") != 1:
            raise SyncError("unsupported protocol version")
        if frame["seq"] <= self.seq:
            raise SyncError("duplicate or out-of-order observation")
        if frame["kind"] == "full":
            nodes = {n["id"]: deepcopy(n) for n in frame["nodes"]}
            if len(nodes) != len(frame["nodes"]):
                raise SyncError("duplicate node ID")
        elif frame["kind"] == "delta":
            if frame["document"] != self.document or frame["base_seq"] != self.seq:
                raise SyncError("missing base observation; request observe(force_full=True)")
            nodes = deepcopy(self.nodes)
            for node_id in frame["removed"]:
                nodes.pop(node_id, None)
            if len({n["id"] for n in frame["upsert"]}) != len(frame["upsert"]):
                raise SyncError("duplicate upsert ID")
            for node in frame["upsert"]:
                nodes[node["id"]] = deepcopy(node)
        else:
            raise SyncError("unknown observation kind")
        # Validate before committing. Reparenting is applied atomically with removals.
        children, positions = {}, set()
        for node in nodes.values():
            if (
                type(node["id"]) is not int
                or node["id"] <= 0
                or type(node["parent"]) is not int
                or node["parent"] < 0
                or type(node["order"]) is not int
                or node["order"] < 0
            ):
                raise SyncError("invalid node ID, parent or order")
            position = (node["parent"], node["order"])
            if position in positions:
                raise SyncError("duplicate sibling order")
            positions.add(position)
            if node["parent"] and node["parent"] not in nodes:
                raise SyncError("orphan node")
            children.setdefault(node["parent"], []).append(node)
        ordered, visited = [], set()

        def visit(parent):
            for node in sorted(children.get(parent, []), key=lambda n: n["order"]):
                if node["id"] in visited:
                    raise SyncError("cyclic tree")
                visited.add(node["id"])
                ordered.append(node)
                visit(node["id"])

        visit(0)
        if len(visited) != len(nodes):
            raise SyncError("unreachable nodes")
        self.nodes, self.document, self.seq = nodes, frame["document"], frame["seq"]
        return deepcopy(ordered)
