"""Durable admission of non-idempotent browser writes and versioned UI evidence.

An admission is NOT a remote transaction. Unknown writes never expire or become
retryable because a UI read is negative. Resource keys are supplied by the caller;
this module cannot discover business identity or stop writes that bypass it.
"""

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import time_ns


class IntentConflict(ValueError):
    """An operation ID was reused for a different semantic operation."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class WriteIntent:
    operation_id: str
    resource: str
    effect: dict

    def binding(self):
        if not self.operation_id.strip() or not self.resource.strip() or not self.effect:
            raise ValueError("nonempty operation ID, semantic resource and effect required")
        return _json({"resource": self.resource, "effect": self.effect})


class RecoveryLedger:
    """One local SQLite database per workflow/account namespace.

    Keep the database (including WAL) on a local durable filesystem. Every writer
    of the protected resource must share it. Copying/resetting it breaks fencing.
    Resource ownership is retained even when a fresh read sees the goal: there
    could still be a delayed write. Releasing it requires an explicit settlement
    decision from the integrator; ordinary reads cannot release it.
    """

    def __init__(self, path):
        self.path = str(Path(path).resolve())
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS resources (
                    resource TEXT PRIMARY KEY, revision INTEGER NOT NULL, holder TEXT
                );
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY, binding TEXT NOT NULL, resource TEXT NOT NULL,
                    revision INTEGER NOT NULL, phase TEXT NOT NULL,
                    observation TEXT, read_serial INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, at_ns INTEGER NOT NULL, intent TEXT NOT NULL,
                    kind TEXT NOT NULL, detail TEXT NOT NULL
                );
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _event(db, intent, kind, detail):
        db.execute("INSERT INTO events(at_ns,intent,kind,detail) VALUES(?,?,?,?)",
                   (time_ns(), intent, kind, _json(detail)))

    @staticmethod
    def _record(db, intent):
        row = db.execute("SELECT * FROM intents WHERE id=?", (intent.operation_id,)).fetchone()
        if row and row["binding"] != intent.binding():
            raise IntentConflict("operation ID already bound to a different resource/effect")
        return row

    def prepare(self, intent):
        binding = intent.binding()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._record(db, intent)
            if row:
                db.commit()
                return {"status": row["phase"], "revision": row["revision"]}
            resource = db.execute("SELECT * FROM resources WHERE resource=?",
                                  (intent.resource,)).fetchone()
            if resource and resource["holder"] is not None:
                result = {"status": "blocked", "reason": "resource_has_unsettled_intent",
                          "holder": resource["holder"], "revision": resource["revision"]}
                self._event(db, intent.operation_id, "blocked", result)
                db.commit()
                return result
            revision = resource["revision"] + 1 if resource else 1
            db.execute("INSERT INTO resources VALUES(?,?,?) ON CONFLICT(resource) DO UPDATE "
                       "SET revision=excluded.revision,holder=excluded.holder",
                       (intent.resource, revision, intent.operation_id))
            db.execute("INSERT INTO intents(id,binding,resource,revision,phase) VALUES(?,?,?,?,?)",
                       (intent.operation_id, binding, intent.resource, revision, "prepared"))
            self._event(db, intent.operation_id, "prepared", {"revision": revision})
            db.commit()
            return {"status": "prepared", "revision": revision}

    def dispatch(self, intent):
        """Persist the one-use permit BEFORE invoking any external callback."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._record(db, intent)
            if not row or row["phase"] != "prepared":
                db.commit()
                return False
            changed = db.execute("UPDATE intents SET phase='dispatched',read_serial=read_serial+1,"
                                 "observation=NULL WHERE id=? AND phase='prepared'",
                                 (intent.operation_id,)).rowcount
            self._event(db, intent.operation_id, "dispatched", {})
            db.commit()
            return changed == 1

    def _returned(self, intent, phase):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._record(db, intent)
            # A late callback cannot resurrect a settled or superseded record.
            db.execute("UPDATE intents SET phase=?,read_serial=read_serial+1,observation=NULL "
                       "WHERE id=? AND phase='dispatched'", (phase, intent.operation_id))
            self._event(db, intent.operation_id, phase, {})
            db.commit()

    async def execute(self, intent, action):
        """Call action at most once for this ID, including concurrent/restarted callers.

        Callback exceptions/cancellation remain ambiguous; they are never reset to
        prepared. A callback itself must not contain retries or multiple writes.
        """
        admission = self.prepare(intent)
        if admission["status"] != "prepared" or not self.dispatch(intent):
            return {"status": "not_dispatched", "admission": admission,
                    "record": self.inspect(intent.operation_id)}
        try:
            value = await action()
        except (Exception, asyncio.CancelledError):
            self._returned(intent, "uncertain")
            raise
        self._returned(intent, "returned")
        return {"status": "dispatched_once", "value": value,
                "record": self.inspect(intent.operation_id)}

    def begin_read(self, intent):
        """Fence a read against action completion, newer reads and explicit release."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._record(db, intent)
            if not row or row["phase"] not in {"dispatched", "returned", "uncertain"}:
                raise ValueError("read requires an unsettled dispatched intent")
            serial = row["read_serial"] + 1
            db.execute("UPDATE intents SET read_serial=?,observation=NULL WHERE id=?",
                       (serial, intent.operation_id))
            db.commit()
            return {"id": intent.operation_id, "resource": row["resource"],
                    "revision": row["revision"], "serial": serial}

    def finish_read(self, ticket, *, goal_observed, evidence):
        if goal_observed is not None and type(goal_observed) is not bool:
            raise ValueError("goal_observed must be bool or None")
        observation = {"goal_observed": goal_observed, "evidence": evidence,
                       "scope": "UI evidence at read time, not causality or safe-retry proof"}
        encoded = _json(observation)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT i.*,r.holder,r.revision AS current_revision FROM intents i "
                             "JOIN resources r ON i.resource=r.resource WHERE i.id=?",
                             (ticket["id"],)).fetchone()
            valid = (row is not None and row["resource"] == ticket["resource"]
                     and row["holder"] == ticket["id"]
                     and row["revision"] == row["current_revision"] == ticket["revision"]
                     and row["read_serial"] == ticket["serial"]
                     and row["phase"] in {"dispatched", "returned", "uncertain"})
            if valid:
                # Consume the ticket so a second completion cannot overwrite the first.
                db.execute("UPDATE intents SET observation=?,read_serial=read_serial+1 WHERE id=?",
                           (encoded, ticket["id"]))
            self._event(db, ticket["id"], "read_accepted" if valid else "stale_read_rejected",
                        observation)
            db.commit()
            return {"status": "observed" if valid else "stale",
                    "goal_observed": goal_observed if valid else None,
                    "evidence": evidence if valid else None,
                    "scope": observation["scope"],
                    "safe_to_retry": False, "resource_released": False}

    async def reconcile(self, intent, read):
        """read returns (bool | None, JSON evidence). Never invokes an action."""
        ticket = self.begin_read(intent)
        try:
            observed, evidence = await read()
        except Exception as exc:  # noqa: BLE001 -- failed evidence stays unknown
            observed, evidence = None, {"error": type(exc).__name__}
        return self.finish_read(ticket, goal_observed=observed, evidence=evidence)

    def settle(self, intent, *, reason):
        """Explicit integrator decision that all prior effects have settled.

        This is a trust boundary, NOT an inference from a UI read. Only call with
        application-specific evidence or an operator decision. A wrong decision
        permits conflicting writes. Settled IDs remain permanently non-replayable.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a settlement reason is required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._record(db, intent)
            if not row:
                raise ValueError("unknown intent")
            db.execute("UPDATE intents SET phase='settled',read_serial=read_serial+1,"
                       "observation=NULL WHERE id=?", (intent.operation_id,))
            db.execute("UPDATE resources SET holder=NULL,revision=revision+1 "
                       "WHERE resource=? AND holder=?", (intent.resource, intent.operation_id))
            self._event(db, intent.operation_id, "explicit_settlement", {"reason": reason})
            db.commit()

    def inspect(self, operation_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM intents WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["binding"] = json.loads(result["binding"])
            result["observation"] = json.loads(result["observation"]) if result["observation"] else None
            return result

    def events(self):
        with self._db() as db:
            return [{**dict(row), "detail": json.loads(row["detail"])}
                    for row in db.execute("SELECT * FROM events ORDER BY seq")]
