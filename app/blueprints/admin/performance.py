"""Reproducible, read-only SQLite benchmark for the QuestEvent admin UI."""
import math
import sqlite3
import statistics
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Lock, local
import re

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.admin import bp
from app.blueprints.rbac import roles_required
from app.constants import ROLE_SUPERADMIN
from app.services.sql_profiler import snapshot as sql_snapshot

_lock = Lock()
_last_result = None


def _pct(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _stats(values):
    return {
        "avg": round(statistics.mean(values), 3),
        "p50": round(statistics.median(values), 3),
        "p95": round(_pct(values, .95), 3),
        "p99": round(_pct(values, .99), 3),
        "max": round(max(values), 3),
    }


def _workload(db_path):
    # Build the SAME query set for both copies. Restrict identifiers to discovered tables.
    with closing(sqlite3.connect(db_path)) as conn:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        queries = []
        for table in tables:
            identifier = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in conn.execute("PRAGMA table_info(" + identifier + ")")]
            if not columns:
                continue
            queries.append((table + " / COUNT", "SELECT COUNT(*) FROM " + identifier))
            queries.append((table + " / выборка", "SELECT * FROM " + identifier + " LIMIT 100"))
            # Ordering by a real column also works for WITHOUT ROWID tables.
            column = '"' + columns[0].replace('"', '""') + '"'
            queries.append((table + " / сортировка", "SELECT * FROM " + identifier +
                            " ORDER BY " + column + " DESC LIMIT 100"))
        # Include realistic filtered lookups: these can benefit from indexes.
        for table in tables:
            identifier = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in conn.execute("PRAGMA table_info(" + identifier + ")")]
            for column in ("client_id", "slot_id", "status", "branch_id", "quest_id", "room_id", "start_time", "email"):
                if column not in columns:
                    continue
                quoted = '"' + column + '"'
                sample = conn.execute(
                    "SELECT " + quoted + " FROM " + identifier + " WHERE " + quoted +
                    " IS NOT NULL LIMIT 1"
                ).fetchone()
                if sample:
                    queries.append((table + " / поиск " + column,
                                    "SELECT * FROM " + identifier + " WHERE " + quoted +
                                    " = " + ("'" + str(sample[0]).replace("'", "''") + "'"
                                              if isinstance(sample[0], str) else
                                              str(sample[0])) + " LIMIT 100"))
        if not queries:
            raise ValueError("Нет таблиц для тестирования")
        return queries


def _run_once(db_path, queries, workers, operations, warmup):
    # One persistent read-only connection per worker. Connection creation is not timed.
    worker_local = local()

    def initialize():
        worker_local.conn = sqlite3.connect(
            Path(db_path).as_uri() + "?mode=ro", uri=True, timeout=10
        )
        worker_local.conn.execute("PRAGMA query_only=ON")

    def execute(index):
        conn = worker_local.conn
        label, sql = queries[index % len(queries)]
        start = time.perf_counter_ns()
        conn.execute(sql).fetchall()
        return label, (time.perf_counter_ns() - start) / 1_000_000

    # Explicitly create/close one connection in each worker, including on exceptions.
    def worker(worker_index):
        initialize()
        try:
            indices = range(worker_index, operations, workers)
            # Warm up each query on each connection; not included in timings.
            for _ in range(warmup):
                for _, sql in queries:
                    worker_local.conn.execute(sql).fetchall()
            return [execute(i) for i in indices]
        finally:
            worker_local.conn.close()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        chunks = list(executor.map(worker, range(workers)))
    elapsed = time.perf_counter() - started
    # Wall time includes warmup; throughput should not. Measure throughput separately
    # from query-only latency to avoid misleading RPS figures.
    measurements = [entry for chunk in chunks for entry in chunk]
    values = [ms for _, ms in measurements]
    grouped = defaultdict(list)
    for label, ms in measurements:
        grouped[label].append(ms)
    return {
        **_stats(values),
        "wall_seconds": round(elapsed, 3),
        "details": {label: _stats(samples) for label, samples in sorted(grouped.items())},
    }


def _copy_database(source, destination):
    with closing(sqlite3.connect(str(source))) as src:
        with closing(sqlite3.connect(str(destination))) as dst:
            src.backup(dst)



def _index_candidates(path, queries):
    """Suggest bounded, single-column indexes only for actual filtered lookups.

    Never change production DB here. Ignore existing equivalent indexes.
    """
    candidates = []
    with closing(sqlite3.connect(str(path))) as conn:
        for table, in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", table):
                continue
            existing = set()
            for index in conn.execute('PRAGMA index_list("' + table + '")'):
                for info in conn.execute('PRAGMA index_info("' + index[1].replace('"', '""') + '")'):
                    if info[2]:
                        existing.add(info[2])
            columns = {row[1] for row in conn.execute('PRAGMA table_info("' + table + '")')}
            count = conn.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
            if count < 100:
                continue
            for column in ("client_id", "slot_id", "status", "branch_id", "quest_id",
                           "room_id", "start_time", "email"):
                if column not in columns or column in existing:
                    continue
                if not any(label == table + " / поиск " + column for label, _ in queries):
                    continue
                distinct = conn.execute(
                    'SELECT COUNT(DISTINCT "' + column + '") FROM "' + table + '"'
                ).fetchone()[0]
                if distinct < 2 or (column == "status" and distinct < 4):
                    continue
                name = "idx_qe_perf_" + table + "_" + column
                candidates.append({
                    "table": table, "column": column, "name": name,
                    "sql": 'CREATE INDEX IF NOT EXISTS "' + name + '" ON "' +
                           table + '" ("' + column + '")'
                })
    return candidates[:24]



def _select_indexes(path, queries, candidates):
    """Greedy candidate validation, with rollback on failed latency checks.

    Conservative: 5 paired runs per candidate, one connection, warm caches.
    No index is accepted if any measured query regresses > 10% or if the
    targeted query does not improve at least 8% and 0.01 ms.
    """
    decisions = []
    accepted = []
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute("PRAGMA optimize")
        conn.commit()
        def measure():
            # Interleave all workload statements to avoid one-query-only cache bias.
            for _ in range(2):
                for _, sql in queries:
                    conn.execute(sql).fetchall()
            values = defaultdict(list)
            for _ in range(5):
                for label, sql in queries:
                    start = time.perf_counter_ns()
                    conn.execute(sql).fetchall()
                    values[label].append((time.perf_counter_ns() - start) / 1_000_000)
            return {key: statistics.median(v) for key, v in values.items()}
        for candidate in candidates:
            target = candidate["table"] + " / поиск " + candidate["column"]
            baseline = measure()
            conn.execute(candidate["sql"])
            conn.execute("PRAGMA optimize")
            conn.commit()
            improved = measure()
            base = baseline.get(target, 0)
            newer = improved.get(target, 0)
            improvement = base - newer
            regressions = [
                label for label, old in baseline.items()
                if old >= .1 and improved[label] > old * 1.10
                and improved[label] - old > .02
            ]
            approved = (
                base > 0 and improvement >= .01 and
                improvement / base >= .08 and not regressions
            )
            if approved:
                accepted.append(candidate)
            else:
                conn.execute('DROP INDEX IF EXISTS "' + candidate["name"] + '"')
                conn.commit()
            decisions.append({
                "name": candidate["name"], "table": candidate["table"],
                "column": candidate["column"], "accepted": approved,
                "before_ms": round(base, 4), "after_ms": round(newer, 4),
                "regressions": len(regressions),
            })
        conn.execute("PRAGMA optimize")
        conn.commit()
    return accepted, decisions


def _benchmark(workers, operations, rounds, warmup):
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        raise ValueError("Поддерживается только SQLite")
    source = Path(uri[len("sqlite:///"):]).resolve()
    if not source.is_file():
        raise ValueError("Файл базы не найден")

    with tempfile.TemporaryDirectory(prefix="qe_benchmark_") as directory:
        before_path = Path(directory) / "before.sqlite"
        after_path = Path(directory) / "after.sqlite"
        _copy_database(source, before_path)
        _copy_database(before_path, after_path)
        queries = _workload(str(before_path))
        candidates = _index_candidates(after_path, queries)
        accepted, decisions = _select_indexes(after_path, queries, candidates)

        with closing(sqlite3.connect(str(after_path))) as conn:
            conn.execute("PRAGMA optimize")
            conn.execute("VACUUM")
            conn.execute("PRAGMA optimize")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Проверка оптимизированной копии не пройдена")

        plans = []
        with closing(sqlite3.connect(str(before_path))) as before_conn:
            with closing(sqlite3.connect(str(after_path))) as after_conn:
                for label, sql in queries:
                    old_plan = [row[3] for row in before_conn.execute("EXPLAIN QUERY PLAN " + sql)]
                    new_plan = [row[3] for row in after_conn.execute("EXPLAIN QUERY PLAN " + sql)]
                    if old_plan != new_plan:
                        plans.append({"query": label, "before": " | ".join(old_plan), "after": " | ".join(new_plan)})
        samples = {"before": [], "after": []}
        for round_number in range(rounds):
            # Alternate run order to reduce cache / thermal / system load bias.
            order = ("before", "after") if round_number % 2 == 0 else ("after", "before")
            for variant in order:
                db_path = before_path if variant == "before" else after_path
                samples[variant].append(
                    _run_once(str(db_path), queries, workers, operations, warmup)
                )

    def aggregate(variant):
        runs = samples[variant]
        metrics = {key: round(statistics.median(run[key] for run in runs), 3)
                   for key in ("avg", "p50", "p95", "p99", "max", "wall_seconds")}
        details = {}
        for label, _ in queries:
            if label in details:
                continue
            details[label] = {
                key: round(statistics.median(run["details"][label][key] for run in runs), 3)
                for key in ("avg", "p50", "p95", "p99", "max")
            }
        metrics["details"] = details
        return metrics

    return {
        "before": aggregate("before"), "after": aggregate("after"),
        "workers": workers, "operations": operations, "rounds": rounds,
        "candidates": accepted, "decisions": decisions, "plans": plans,
        "warmup": warmup, "query_types": len(queries),
        "note": "Задержка измеряет только execute + fetchall. Время создания соединения и прогрев исключены. "
                "Показатели — медианы по чередующимся прогонам. VACUUM/optimize не гарантируют ускорения.",
    }


@bp.route("/performance", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN)
def performance():
    global _last_result
    if request.method == "POST":
        if not _lock.acquire(blocking=False):
            flash("Тест уже выполняется", "warning")
            return redirect(url_for("admin.performance"))
        try:
            workers = max(1, min(16, int(request.form.get("workers", 4))))
            operations = max(100, min(20000, int(request.form.get("operations", 1000))))
            rounds = max(2, min(8, int(request.form.get("rounds", 4))))
            warmup = max(1, min(5, int(request.form.get("warmup", 2))))
            _last_result = _benchmark(workers, operations, rounds, warmup)
            flash("Тест завершён. Рабочая база не изменялась.", "success")
        except (ValueError, sqlite3.Error, OSError) as exc:
            current_app.logger.exception("Ошибка тестирования SQLite")
            flash(f"Ошибка тестирования: {exc}", "danger")
        finally:
            _lock.release()
        return redirect(url_for("admin.performance"))
    return render_template("admin/performance.html", result=_last_result, sql_profile=sql_snapshot())
