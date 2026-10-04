"""Taskboard API: a small kanban backend.

Tasks have a title and one of three statuses. Data lives in PostgreSQL; the
tests use an in-memory store with the same methods.
"""

import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

STATUSES = ("todo", "doing", "done")
MAX_TITLE = 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id         SERIAL PRIMARY KEY,
    title      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'todo',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class PgStore:
    """Stores tasks in PostgreSQL. Opens a short-lived connection per call."""

    def __init__(self, dsn):
        self.dsn = dsn
        self.schema_ready = False

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=3)

    def ready(self):
        """Check the database answers, and create the table the first time it does."""
        with self._connect() as conn:
            if not self.schema_ready:
                conn.execute(SCHEMA)
                self.schema_ready = True
            conn.execute("SELECT 1")

    def _run(self, query, params=()):
        if not self.schema_ready:
            self.ready()
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def list(self):
        return [self._to_api(row) for row in self._run("SELECT * FROM tasks ORDER BY id")]

    def add(self, title):
        rows = self._run("INSERT INTO tasks (title) VALUES (%s) RETURNING *", (title,))
        return self._to_api(rows[0])

    def update(self, task_id, title=None, status=None):
        rows = self._run(
            "UPDATE tasks SET title = COALESCE(%s, title), status = COALESCE(%s, status) "
            "WHERE id = %s RETURNING *",
            (title, status, task_id),
        )
        return self._to_api(rows[0]) if rows else None

    def delete(self, task_id):
        return bool(self._run("DELETE FROM tasks WHERE id = %s RETURNING id", (task_id,)))

    @staticmethod
    def _to_api(row):
        return {"id": row["id"], "title": row["title"], "status": row["status"],
                "created_at": row["created_at"].isoformat()}


class MemoryStore:
    """Same methods as PgStore, backed by a dict. Used by the tests."""

    def __init__(self):
        self.tasks = {}
        self.next_id = 1

    def ready(self):
        pass

    def list(self):
        return [dict(task) for task in self.tasks.values()]

    def add(self, title):
        task = {"id": self.next_id, "title": title, "status": "todo", "created_at": "2026-01-01T00:00:00+00:00"}
        self.tasks[self.next_id] = task
        self.next_id += 1
        return dict(task)

    def update(self, task_id, title=None, status=None):
        task = self.tasks.get(task_id)
        if task is None:
            return None
        if title is not None:
            task["title"] = title
        if status is not None:
            task["status"] = status
        return dict(task)

    def delete(self, task_id):
        return self.tasks.pop(task_id, None) is not None


def clean_title(value):
    title = str(value or "").strip()
    return title if 0 < len(title) <= MAX_TITLE else None


def create_app(store=None):
    store = store or PgStore(os.environ["DATABASE_URL"])
    app = Flask(__name__)

    # Liveness: the process is running. Does not touch the database, so a
    # database outage does not make Kubernetes restart healthy API pods.
    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    # Readiness: the pod can serve requests, which needs the database.
    @app.get("/readyz")
    def readyz():
        try:
            store.ready()
        except Exception as error:
            return jsonify(status="unavailable", reason=type(error).__name__), 503
        return jsonify(status="ready")

    # A database outage should give clients a clear 503, not a stack trace
    @app.errorhandler(Exception)
    def storage_error(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.error("request failed: %s", error)
        return jsonify(error="service temporarily unavailable"), 503

    @app.get("/api/tasks")
    def list_tasks():
        return jsonify(store.list())

    @app.post("/api/tasks")
    def add_task():
        title = clean_title((request.get_json(silent=True) or {}).get("title"))
        if title is None:
            return jsonify(error=f"title is required ({MAX_TITLE} characters at most)"), 400
        return jsonify(store.add(title)), 201

    @app.patch("/api/tasks/<int:task_id>")
    def update_task(task_id):
        data = request.get_json(silent=True) or {}
        title = status = None

        if "title" in data:
            title = clean_title(data["title"])
            if title is None:
                return jsonify(error=f"title must be 1-{MAX_TITLE} characters"), 400
        if "status" in data:
            status = data["status"]
            if status not in STATUSES:
                return jsonify(error="status must be one of: " + ", ".join(STATUSES)), 400
        if title is None and status is None:
            return jsonify(error="nothing to update"), 400

        task = store.update(task_id, title=title, status=status)
        if task is None:
            return jsonify(error="task not found"), 404
        return jsonify(task)

    @app.delete("/api/tasks/<int:task_id>")
    def delete_task(task_id):
        if not store.delete(task_id):
            return jsonify(error="task not found"), 404
        return "", 204

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8000)
