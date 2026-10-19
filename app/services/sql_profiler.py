"""Bounded, privacy-aware SQL latency profiler for SQLAlchemy/SQLite.

Collects statement shape and timing, NEVER bound parameters or returned rows.
The profiler is observational and does not modify SQL or transactions.
"""
import hashlib
import re
import statistics
import threading
import time
from collections import deque
from sqlalchemy import event
from sqlalchemy.engine import Engine

_LOCK = threading.Lock()
_SAMPLES = {}
_MAX_SHAPES = 300
_MAX_SAMPLES = 128
_ENABLED = True
_SQL_SPACE = re.compile(r"\\s+")


def _fingerprint(statement):
    # Never retain SQL text: even compiled SQL can contain sensitive literals.
    shape = _SQL_SPACE.sub(" ", statement.strip())
    return hashlib.sha256(shape.encode("utf-8")).hexdigest()[:16], "<SQL fingerprint only>"


def install():
    """Idempotently install once per Python process."""
    if getattr(install, "_installed", False):
        return
    install._installed = True

    @event.listens_for(Engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):
        if conn.dialect.name == "sqlite":
            context._qe_sql_started = time.perf_counter_ns()

    @event.listens_for(Engine, "after_cursor_execute")
    def _finish(conn, cursor, statement, parameters, context, executemany):
        started = getattr(context, "_qe_sql_started", None)
        if started is None or statement.lstrip().upper().startswith(("PRAGMA", "EXPLAIN")):
            return
        ms = (time.perf_counter_ns() - started) / 1_000_000
        key, shape = _fingerprint(statement)
        with _LOCK:
            if key not in _SAMPLES:
                if len(_SAMPLES) >= _MAX_SHAPES:
                    return
                _SAMPLES[key] = {"sql": shape, "times": deque(maxlen=_MAX_SAMPLES), "count": 0}
            item = _SAMPLES[key]
            item["count"] += 1
            item["times"].append(ms)


def snapshot():
    with _LOCK:
        data = [
            {"id": key, "sql": item["sql"], "count": item["count"],
             "avg_ms": round(statistics.mean(item["times"]), 3),
             "p95_ms": round(sorted(item["times"])[int((len(item["times"])-1)*.95)], 3)}
            for key, item in _SAMPLES.items() if item["times"]
        ]
    return sorted(data, key=lambda row: row["p95_ms"], reverse=True)
