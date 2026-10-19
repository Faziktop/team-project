import sqlite3
import time
import statistics

DB_PATH = "instance/questevent.db"

queries = {
    "Получение всех клиентов":
        "SELECT * FROM users",

    "Поиск клиента по ID":
        "SELECT * FROM users WHERE id = 1",

    "Получение бронирований":
        "SELECT * FROM bookings",

    "Бронирования по статусу":
        "SELECT * FROM bookings WHERE status = 'confirmed'",

    "Подсчёт бронирований":
        "SELECT COUNT(*) FROM bookings",

    "Связь бронирований с клиентами": """
        SELECT b.id, u.email
        FROM bookings b
        JOIN users u ON b.client_id = u.id
    """
}

REPEATS = 100

with sqlite3.connect(DB_PATH) as conn:
    for name, sql in queries.items():
        times = []
        rows_count = 0

        # Прогрев кэша
        for _ in range(5):
            conn.execute(sql).fetchall()

        for _ in range(REPEATS):
            start = time.perf_counter_ns()

            rows = conn.execute(sql).fetchall()

            elapsed_ms = (
                time.perf_counter_ns() - start
            ) / 1_000_000

            times.append(elapsed_ms)
            rows_count = len(rows)

        print(f"\n{name}")
        print(f"  Строк: {rows_count}")
        print(f"  Среднее: {statistics.mean(times):.3f} ms")
        print(f"  Медиана: {statistics.median(times):.3f} ms")
        print(f"  Минимум: {min(times):.3f} ms")
        print(f"  Максимум: {max(times):.3f} ms")
