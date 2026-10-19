#!/usr/bin/env python3
"""Heavy, reproducible SQLite load test for QuestEvent. Only works on database COPIES.
Python 3.10+, standard library only. Does not stress Flask HTTP endpoints.
"""
import argparse
import concurrent.futures
import csv
import json
import math
import os
import random
import sqlite3
import statistics
import tempfile
import time
from collections import defaultdict
from pathlib import Path


def connect(path):
    c = sqlite3.connect(str(path), timeout=15)
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('PRAGMA query_only=ON')
    return c


def copy_db(source, dest):
    with sqlite3.connect(str(source), timeout=30) as src, sqlite3.connect(str(dest)) as dst:
        src.backup(dst)


def get_schema(db):
    with connect(db) as c:
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        columns = {t: {r[1] for r in c.execute(f'PRAGMA table_info("{t}")')} for t in tables}
        counts = {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        ids = {}
        for t in tables:
            if 'id' in columns[t] and counts[t]:
                ids[t] = [r[0] for r in c.execute(f'SELECT id FROM "{t}"')]
    return columns, counts, ids


def build_workload(columns, counts, ids):
    work = []
    for table, cols in columns.items():
        if not counts[table]:
            continue
        # Covers every populated table, including audit and notifications.
        work.append((f'{table}:count', f'SELECT COUNT(*) FROM "{table}"', None))
        work.append((f'{table}:scan', f'SELECT * FROM "{table}" LIMIT 500', None))
        if table in ids:
            work.append((f'{table}:lookup', f'SELECT * FROM "{table}" WHERE id=?', table))
    def add(name, sql, required):
        if all(t in columns and set(cs) <= columns[t] and counts[t] for t, cs in required.items()):
            work.append((name, sql, None))
    add('crm:client_bookings', '''SELECT u.id, u.full_name, COUNT(b.id) n, COALESCE(SUM(b.final_price),0) total
        FROM users u LEFT JOIN bookings b ON b.client_id=u.id
        WHERE u.role='client' GROUP BY u.id ORDER BY total DESC LIMIT 100''',
        {'users':['id','full_name','role'], 'bookings':['id','client_id','final_price']})
    add('booking:full_join', '''SELECT b.id, b.status, u.full_name, s.start_time, q.title
        FROM bookings b JOIN users u ON b.client_id=u.id
        JOIN slots s ON b.slot_id=s.id JOIN quests q ON s.quest_id=q.id
        ORDER BY b.id DESC LIMIT 300''',
        {'bookings':['id','status','client_id','slot_id'], 'users':['id','full_name'],
         'slots':['id','start_time','quest_id'], 'quests':['id','title']})
    add('schedule:available', '''SELECT s.id,s.start_time,q.title FROM slots s
        JOIN quests q ON s.quest_id=q.id WHERE s.status='available'
        ORDER BY s.start_time LIMIT 200''',
        {'slots':['id','start_time','status','quest_id'], 'quests':['id','title']})
    add('reports:revenue', '''SELECT status, substr(created_at,1,7) month,
        COUNT(*) bookings, SUM(final_price) revenue FROM bookings
        GROUP BY status, substr(created_at,1,7) ORDER BY month DESC''',
        {'bookings':['status','created_at','final_price']})
    add('reviews:rating', '''SELECT q.title,COUNT(r.id),AVG(r.rating) FROM reviews r
        JOIN bookings b ON r.booking_id=b.id JOIN slots s ON b.slot_id=s.id
        JOIN quests q ON s.quest_id=q.id GROUP BY q.id ORDER BY AVG(r.rating) DESC''',
        {'reviews':['id','rating','booking_id'], 'bookings':['id','slot_id'],
         'slots':['id','quest_id'], 'quests':['id','title']})
    return work


def percentile(values, p):
    if not values:
        return 0.0
    a = sorted(values)
    pos = (len(a)-1)*p/100
    lo, hi = math.floor(pos), math.ceil(pos)
    return a[lo] + (a[hi]-a[lo])*(pos-lo)


def worker(db, workload, ids, iterations, seed):
    rng = random.Random(seed)
    results = defaultdict(list)
    errors = []
    with connect(db) as c:
        for _ in range(iterations):
            name, sql, table = workload[rng.randrange(len(workload))]
            args = (rng.choice(ids[table]),) if table else ()
            start = time.perf_counter_ns()
            try:
                # Includes reading rows, not rendering HTML or network transport.
                c.execute(sql, args).fetchall()
                results[name].append((time.perf_counter_ns()-start)/1e6)
            except sqlite3.Error as exc:
                errors.append(f'{name}: {exc}')
    return results, errors


def run(db, workload, ids, workers, operations, seed):
    # Fixed number of operations per worker ensures comparable workloads.
    distribution = [operations // workers + (1 if i < operations % workers else 0) for i in range(workers)]
    start = time.perf_counter()
    combined = defaultdict(list)
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, db, workload, ids, n, seed+i) for i,n in enumerate(distribution) if n]
        for f in concurrent.futures.as_completed(futures):
            data, failures = f.result()
            errors.extend(failures)
            for name, vals in data.items():
                combined[name].extend(vals)
    elapsed = time.perf_counter()-start
    flat = [v for vals in combined.values() for v in vals]
    return {'elapsed_s':elapsed,'ops':len(flat),'qps':len(flat)/elapsed if elapsed else 0,
            'mean_ms':statistics.mean(flat) if flat else 0,'p50_ms':percentile(flat,50),
            'p95_ms':percentile(flat,95),'p99_ms':percentile(flat,99),
            'max_ms':max(flat,default=0), 'by_query':combined,'errors':errors}


def optimize(db, vacuum):
    # Work on disposable copy, never original. No arbitrary index changes.
    with sqlite3.connect(str(db), timeout=30) as c:
        integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise RuntimeError('Integrity check failed: '+str(integrity))
        c.execute('PRAGMA optimize')
        c.commit()
        if vacuum:
            c.execute('VACUUM')
        c.execute('PRAGMA optimize')
        c.commit()


def report(name, result):
    print(f'\n{name}: {result["ops"]:,} запросов за {result["elapsed_s"]:.2f} с; '
          f'{result["qps"]:,.1f} req/s')
    print(f'  mean {result["mean_ms"]:.3f} ms | p50 {result["p50_ms"]:.3f} ms | '
          f'p95 {result["p95_ms"]:.3f} ms | p99 {result["p99_ms"]:.3f} ms | '
          f'max {result["max_ms"]:.3f} ms')
    if result['errors']:
        print('  ОШИБКИ:', *result['errors'][:5], sep='\n    ')


def main():
    p = argparse.ArgumentParser(description='QuestEvent: стресс-тест ВСЕХ таблиц SQLite до и после оптимизации')
    p.add_argument('--db', default='instance/questevent.db')
    p.add_argument('--workers', type=int, default=12)
    p.add_argument('--operations', type=int, default=30000, help='Количество SQL-запросов на каждый этап')
    p.add_argument('--out', default='questevent_stress_report.csv')
    p.add_argument('--vacuum', action='store_true', help='Дополнительно выполнить VACUUM на копии БД')
    p.add_argument('--seed', type=int, default=2026)
    args = p.parse_args()
    if args.workers < 1 or args.operations < 1 or args.workers > 128:
        p.error('workers: 1..128; operations: >=1')
    source = Path(args.db).resolve()
    if not source.is_file():
        p.error(f'БД не найдена: {source}')
    with tempfile.TemporaryDirectory(prefix='questevent_stress_') as temp:
        before_db, after_db = Path(temp)/'before.db', Path(temp)/'after.db'
        copy_db(source, before_db)
        copy_db(source, after_db)
        columns, counts, ids = get_schema(before_db)
        workload = build_workload(columns, counts, ids)
        if not workload:
            p.error('Нет таблиц с данными')
        print('Исходная БД:', source)
        print('Таблиц:',len(columns),'| Заполнено:',sum(bool(x) for x in counts.values()),
              '| Сценариев:',len(workload),'| Потоков:',args.workers)
        print('Исходная база НЕ изменяется. Тестируются две временные копии.')
        # One warmup on both databases; exclude from statistics.
        run(before_db, workload, ids, min(args.workers,4), min(200,len(workload)*5), args.seed+100)
        run(after_db, workload, ids, min(args.workers,4), min(200,len(workload)*5), args.seed+100)
        baseline = run(before_db, workload, ids, args.workers, args.operations, args.seed)
        report('ДО оптимизации',baseline)
        print('\nОптимизация второй копии (PRAGMA optimize'+(' + VACUUM' if args.vacuum else '')+')...')
        optimize(after_db,args.vacuum)
        improved = run(after_db, workload, ids, args.workers, args.operations, args.seed)
        report('ПОСЛЕ оптимизации',improved)
        output = Path(args.out).resolve()
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f)
            writer.writerow(['scenario','queries_before','mean_before_ms','p95_before_ms',
                             'p99_before_ms','queries_after','mean_after_ms','p95_after_ms',
                             'p99_after_ms','mean_change_percent'])
            for name in sorted(set(baseline['by_query']) | set(improved['by_query'])):
                a=baseline['by_query'].get(name,[]); b=improved['by_query'].get(name,[])
                ma=statistics.mean(a) if a else 0; mb=statistics.mean(b) if b else 0
                writer.writerow([name,len(a),round(ma,6),round(percentile(a,95),6),round(percentile(a,99),6),
                                 len(b),round(mb,6),round(percentile(b,95),6),round(percentile(b,99),6),
                                 round((ma-mb)/ma*100,2) if ma else ''])
        print('\nСравнение throughput: {:+.1f}%'.format((improved['qps']/baseline['qps']-1)*100 if baseline['qps'] else 0))
        print('Отчёт по каждому типу запроса:',output)
        if baseline['errors'] or improved['errors']:
            raise SystemExit('Во время тестирования были SQL-ошибки; см. вывод выше.')
        print('Примечание: это стресс-тест SQLite, а не HTTP/Flask. Время зависит от кэша и нагрузки ОС.')

if __name__ == '__main__':
    main()
