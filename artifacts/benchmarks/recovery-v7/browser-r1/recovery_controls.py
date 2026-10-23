"""Independent simple controls. No import of DeltaDOM's implementation.

RequestJournal adds only durable request-ID admission. ResourceJournal adds a
resource mutex and a read-generation CAS: the strongest simple control. Keep it
in the comparison even when it ties the candidate.
"""

import asyncio
import json
import sqlite3
from contextlib import closing


class Journal:
    def __init__(self, path, *, resources=False, read_goal=None):
        self.path, self.resources = str(path), resources
        self.read_goal = read_goal
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, resource TEXT, payload TEXT, state TEXT,
                    generation INTEGER DEFAULT 0, observation TEXT
                );
            ''')
            db.commit()

    @staticmethod
    def binding(intent):
        return json.dumps([intent.resource, intent.effect], sort_keys=True)

    def prepare(self, intent):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT payload,state FROM jobs WHERE id=?',
                             (intent.operation_id,)).fetchone()
            if job:
                if job[0] != self.binding(intent):
                    raise ValueError('changed payload')
                return {"status": job[1]}
            if self.resources and db.execute(
                "SELECT 1 FROM jobs WHERE resource=? AND state!='settled'", (intent.resource,)
            ).fetchone():
                return {"status": "blocked"}
            db.execute('INSERT INTO jobs(id,resource,payload,state) VALUES(?,?,?,?)',
                       (intent.operation_id, intent.resource, self.binding(intent), 'prepared'))
            db.commit()
            return {"status": "prepared"}

    async def execute(self, intent, action):
        if self.prepare(intent)['status'] != 'prepared':
            return {"status": "not_dispatched"}
        if self.read_goal is not None and await self.read_goal(intent):
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("UPDATE jobs SET state='already_observed' WHERE id=? AND state='prepared'",
                           (intent.operation_id,))
                db.commit()
            return {"status": "goal_already_visible"}
        with closing(sqlite3.connect(self.path)) as db:
            changed = db.execute("UPDATE jobs SET state='dispatched',generation=generation+1 "
                                 "WHERE id=? AND state='prepared'", (intent.operation_id,)).rowcount
            db.commit()
        if not changed:
            return {"status": "not_dispatched"}
        try:
            value = await action()
        except (Exception, asyncio.CancelledError):
            self.finish(intent, 'uncertain')
            raise
        self.finish(intent, 'returned')
        return {"status": "dispatched_once", "value": value}

    def finish(self, intent, state):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE jobs SET state=?,generation=generation+1,observation=NULL "
                       "WHERE id=? AND state='dispatched'", (state, intent.operation_id))
            db.commit()

    def begin_read(self, intent):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE jobs SET generation=generation+1,observation=NULL WHERE id=?',
                       (intent.operation_id,))
            generation = db.execute('SELECT generation FROM jobs WHERE id=?',
                                    (intent.operation_id,)).fetchone()[0]
            db.commit()
            return (intent.operation_id, generation)

    def finish_read(self, ticket, *, goal_observed, evidence):
        with closing(sqlite3.connect(self.path)) as db:
            clause = " AND generation=? AND state!='settled'" if self.resources else ''
            args = (json.dumps(goal_observed), ticket[0]) + ((ticket[1],) if self.resources else ())
            changed = db.execute('UPDATE jobs SET observation=?,generation=generation+1 '
                                 'WHERE id=?' + clause, args).rowcount
            db.commit()
            return {"status": "observed" if changed else "stale",
                    "goal_observed": goal_observed if changed else None}

    async def reconcile(self, intent, read):
        ticket = self.begin_read(intent)
        try:
            observed, evidence = await read()
        except Exception:  # noqa: BLE001 -- conservative read failure
            observed, evidence = None, {}
        return self.finish_read(ticket, goal_observed=observed, evidence=evidence)

    def settle(self, intent, *, reason):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE jobs SET state='settled',generation=generation+1,observation=NULL "
                       "WHERE id=?", (intent.operation_id,))
            db.commit()


class FreshCheck:
    """A strong exact visible-goal check before each invocation; no durable state."""
    def __init__(self, read_goal):
        self.read_goal = read_goal

    def prepare(self, intent):
        return {"status": "prepared"}

    async def execute(self, intent, action):
        if await self.read_goal(intent):
            return {"status": "goal_already_visible"}
        return {"status": "dispatched_once", "value": await action()}

    def begin_read(self, intent):
        return intent.operation_id

    def finish_read(self, ticket, *, goal_observed, evidence):
        return {"status": "observed", "goal_observed": goal_observed}

    async def reconcile(self, intent, read):
        try:
            observed, evidence = await read()
        except Exception:  # noqa: BLE001 -- same conservative failure policy
            observed, evidence = None, {}
        return self.finish_read(None, goal_observed=observed, evidence=evidence)

    def settle(self, intent, *, reason):
        pass
