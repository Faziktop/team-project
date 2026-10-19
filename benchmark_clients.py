#!/usr/bin/env python3
"""QuestEvent: построчный benchmark клиентов + безопасная оптимизация SQLite.

Оптимизация относится к статистике планировщика всей БД, не к отдельным ID.
Сохраняет резервную копию до изменений и сравнивает повторные измерения.
"""
import argparse
import csv
import math
import sqlite3
import statistics
import time
from datetime import datetime
from pathlib import Path

SQL = "SELECT * FROM users WHERE id = ? AND role = 'client'"


def percentile(values, p):
    v = sorted(values)
    pos = (len(v) - 1) * p / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def measure(conn, client_id, repeats):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        row = conn.execute(SQL, (client_id,)).fetchone()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
        if row is None:
            raise RuntimeError(f'Клиент ID={client_id} не найден')
    return {'client_id': client_id, 'avg_ms': statistics.mean(samples),
            'median_ms': statistics.median(samples), 'min_ms': min(samples),
            'max_ms': max(samples)}


def benchmark(conn, ids, repeats, verbose=True):
    if ids:
        for _ in range(5):
            conn.execute(SQL, (ids[0],)).fetchone()
    records = []
    for cid in ids:
        r = measure(conn, cid, repeats)
        records.append(r)
        if verbose:
            print(f'{cid:>9} {r["avg_ms"]:>14.6f} {r["min_ms"]:>12.6f} {r["max_ms"]:>12.6f}')
    return records


def save_csv(path, records):
    with Path(path).open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['client_id', 'avg_ms', 'median_ms', 'min_ms', 'max_ms'])
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description='Benchmark клиентов QuestEvent с PRAGMA optimize')
    parser.add_argument('--db', default='instance/questevent.db')
    parser.add_argument('--repeats', type=int, default=30)
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--csv', default='client_benchmark.csv')
    parser.add_argument('--no-optimize', action='store_true', help='Только измерить, без изменений БД')
    parser.add_argument('--backup', default='', help='Путь резервной копии (по умолчанию автоматически)')
    parser.add_argument('--full-optimize', action='store_true', help='Дополнительно выполнить VACUUM (только при остановленном Flask)')
    args = parser.parse_args()
    if args.repeats < 1 or args.top < 0:
        parser.error('--repeats >= 1, --top >= 0')
    db = Path(args.db).expanduser().resolve()
    if not db.is_file():
        parser.error(f'БД не найдена: {db}')

    # Первый проход только для чтения.
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=10) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'users' not in tables:
            parser.error('Таблица users не найдена')
        cols = {r[1] for r in conn.execute('PRAGMA table_info("users")')}
        if not {'id', 'role'}.issubset(cols):
            parser.error('Нет столбцов users.id / users.role')
        ids = [r[0] for r in conn.execute("SELECT id FROM users WHERE role='client' ORDER BY id")]
        if not ids:
            print('Клиенты не найдены.')
            return
        print(f'Клиентов: {len(ids)}; повторов на ID: {args.repeats}')
        print(f'{"ID":>9} {"Среднее ms":>14} {"Мин. ms":>12} {"Макс. ms":>12}')
        print('-' * 53)
        started = time.perf_counter()
        before = benchmark(conn, ids, args.repeats)
        elapsed = time.perf_counter() - started
        plan = conn.execute('EXPLAIN QUERY PLAN ' + SQL, (ids[0],)).fetchall()

    averages = [r['avg_ms'] for r in before]
    print(f'\nПроверено {len(before)} строк за {elapsed:.2f} сек.')
    print(f'Среднее: {statistics.mean(averages):.6f} ms; '
          f'медиана: {statistics.median(averages):.6f} ms; '
          f'P95: {percentile(averages,95):.6f} ms; P99: {percentile(averages,99):.6f} ms')
    slow = sorted(before, key=lambda r: r['avg_ms'], reverse=True)[:args.top]
    print('\nСамые медленные ID:', ', '.join(str(r['client_id']) for r in slow) or 'нет')
    print('План SQL:', '; '.join(str(r[-1]) for r in plan))
    if args.csv:
        save_csv(args.csv, before)
        print('Исходные измерения:', args.csv)
    if args.no_optimize:
        print('Оптимизация отключена.')
        return

    if args.full_optimize:
        print('ВНИМАНИЕ: остановите Flask, фоновые задачи и другие подключения к БД перед VACUUM.')
    # sqlite backup API создаёт согласованную копию даже при WAL.
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = Path(args.backup).expanduser().resolve() if args.backup else db.with_name(f'{db.stem}.backup_{timestamp}.db')
    if backup.exists():
        parser.error(f'Резервная копия уже существует: {backup}')
    backup.parent.mkdir(parents=True, exist_ok=True)
    print(f'\nСоздание резервной копии: {backup}')
    try:
        with sqlite3.connect(db, timeout=30) as source, sqlite3.connect(backup) as dest:
            source.backup(dest)
        print('Оптимизация: PRAGMA optimize (статистика планировщика)...')
        with sqlite3.connect(db, timeout=30) as conn:
            conn.execute('PRAGMA busy_timeout = 30000')
            # Для SQLite 3.46+ рекомендуемый способ обновить статистику.
            # На старых версиях SQLite команда безопасна, но может быть менее эффективна.
            conn.execute('PRAGMA optimize')
            conn.commit()
            if args.full_optimize:
                print('Проверка целостности SQLite...')
                check = conn.execute('PRAGMA integrity_check').fetchone()[0]
                if check != 'ok':
                    raise sqlite3.DatabaseError(f'Integrity check: {check}')
                print('VACUUM: перестройка файла БД (требуется свободное место на диске)...')
                conn.execute('VACUUM')
                conn.execute('PRAGMA optimize')
                conn.commit()
                print('Проверка целостности после VACUUM...')
                check = conn.execute('PRAGMA integrity_check').fetchone()[0]
                if check != 'ok':
                    raise sqlite3.DatabaseError(f'Integrity check: {check}')
    except (sqlite3.Error, OSError) as exc:
        print(f'ОШИБКА: {exc}')
        print('Резервная копия сохранена, если успела создаться.')
        raise SystemExit(1)

    # Сравниваем именно выделенные медленные ID.
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=10) as conn:
        after = benchmark(conn, [r['client_id'] for r in slow], args.repeats, verbose=False)
    after_map = {r['client_id']: r for r in after}
    print('\nСРАВНЕНИЕ МЕДЛЕННЫХ ID')
    print(f'{"ID":>9} {"До, ms":>12} {"После, ms":>12} {"Изменение":>13}')
    print('-' * 50)
    comparison = []
    for b in slow:
        a = after_map[b['client_id']]
        change = (b['avg_ms'] - a['avg_ms']) / b['avg_ms'] * 100 if b['avg_ms'] else 0
        print(f'{b["client_id"]:>9} {b["avg_ms"]:>12.6f} {a["avg_ms"]:>12.6f} {change:>+12.1f}%')
        comparison.append({'client_id': b['client_id'], 'before_ms': b['avg_ms'],
                           'after_ms': a['avg_ms'], 'change_percent': change})
    if args.csv:
        output = Path(args.csv)
        compare_path = output.with_name(output.stem + '_comparison.csv')
        with compare_path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['client_id','before_ms','after_ms','change_percent'])
            writer.writeheader()
            writer.writerows(comparison)
        print('Сравнение:', compare_path)
    print('\nГотово. +% означает ускорение, -% замедление.')
    print('VACUUM и PRAGMA optimize не гарантируют ускорение SELECT по первичному ключу.')
    print('Для точных выводов повторите тест без фоновой нагрузки.')
    print('Резервная копия:', backup)


if __name__ == '__main__':
    main()