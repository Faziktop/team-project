"""Отчётность и аналитика. ТЗ п.4.2.7: загрузка, выручка, конверсия, эффективность."""
import csv
import io
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, case

from app.extensions import db
from app.models.slot import Slot
from app.models.booking import Booking
from app.models.quest import Quest
from app.models.room import Room
from app.models.user import User
from app.constants import (
    SLOT_BOOKED, SLOT_COMPLETED, BOOKING_CANCELED, BOOKING_COMPLETED,
    BOOKING_CONFIRMED,
)


def _date_range_filter(query, model_datetime_col, date_from: date, date_to: date):
    return query.filter(
        model_datetime_col >= datetime.combine(date_from, time.min),
        model_datetime_col <= datetime.combine(date_to, time.max),
    )


def occupancy_report(date_from: date, date_to: date, branch_id: int | None = None):
    """Загрузка локаций/комнат: доля занятых сеансов от общего числа."""
    q = (
        db.session.query(
            Room.name.label("room"),
            func.count(Slot.id).label("total_slots"),
            func.sum(case((Slot.status.in_([SLOT_BOOKED, SLOT_COMPLETED]), 1), else_=0)).label("booked_slots"),
        )
        .join(Room, Room.id == Slot.room_id)
    )
    if branch_id:
        from app.models.location import Location
        q = q.join(Location, Location.id == Room.location_id).filter(Location.branch_id == branch_id)
    q = _date_range_filter(q, Slot.start_time, date_from, date_to).group_by(Room.id)

    rows = []
    for room, total, booked in q.all():
        booked = booked or 0
        rate = round((booked / total) * 100, 1) if total else 0.0
        rows.append({"room": room, "total_slots": total, "booked_slots": booked, "occupancy_pct": rate})
    return rows


def revenue_report(date_from: date, date_to: date, branch_id: int | None = None):
    """Выручка, средний чек и конверсия за период."""
    bookings_q = Booking.query.join(Slot, Slot.id == Booking.slot_id)
    if branch_id:
        from app.models.room import Room as RoomModel
        from app.models.location import Location
        bookings_q = (
            bookings_q.join(RoomModel, RoomModel.id == Slot.room_id)
            .join(Location, Location.id == RoomModel.location_id)
            .filter(Location.branch_id == branch_id)
        )
    bookings_q = _date_range_filter(bookings_q, Booking.created_at, date_from, date_to)
    # Aggregate in SQLite rather than loading every Booking ORM object into Python.
    # This reduces memory and Python overhead for large historical datasets.
    summary = bookings_q.with_entities(
        func.count(Booking.id),
        func.sum(case((Booking.status == BOOKING_CANCELED, 1), else_=0)),
        func.sum(case((Booking.status.in_([BOOKING_CONFIRMED, BOOKING_COMPLETED]), 1), else_=0)),
        func.sum(case(
            (Booking.status.in_([BOOKING_CONFIRMED, BOOKING_COMPLETED]), Booking.final_price),
            else_=0,
        )),
    ).one()
    total_bookings = int(summary[0] or 0)
    canceled = int(summary[1] or 0)
    confirmed_count = int(summary[2] or 0)
    revenue = float(summary[3] or 0)
    avg_check = round(revenue / confirmed_count, 2) if confirmed_count else 0.0
    conversion = round(confirmed_count / total_bookings * 100, 1) if total_bookings else 0.0

    return {
        "total_bookings": total_bookings,
        "canceled_bookings": canceled,
        "confirmed_bookings": confirmed_count,
        "revenue": round(revenue, 2),
        "avg_check": avg_check,
        "conversion_pct": conversion,
    }


def revenue_by_day(date_from: date, date_to: date, branch_id: int | None = None):
    """Выручка по дням за период (для графика тренда), без учёта отменённых броней."""
    day_expr = func.date(Booking.created_at)
    q = (
        db.session.query(
            day_expr.label("day"),
            func.sum(Booking.final_price).label("revenue"),
            func.count(Booking.id).label("bookings_count"),
        )
        .join(Slot, Slot.id == Booking.slot_id)
        .filter(Booking.status != BOOKING_CANCELED)
    )
    if branch_id:
        from app.models.location import Location
        q = (
            q.join(Room, Room.id == Slot.room_id)
            .join(Location, Location.id == Room.location_id)
            .filter(Location.branch_id == branch_id)
        )
    q = _date_range_filter(q, Booking.created_at, date_from, date_to).group_by(day_expr).order_by(day_expr)
    by_day = {row.day: {"revenue": float(row.revenue or 0), "bookings_count": row.bookings_count} for row in q.all()}

    result = []
    current = date_from
    while current <= date_to:
        info = by_day.get(current.isoformat(), {"revenue": 0.0, "bookings_count": 0})
        result.append({"date": current, "revenue": round(info["revenue"], 2), "bookings_count": info["bookings_count"]})
        current += timedelta(days=1)
    return result


def quest_effectiveness_report(date_from: date, date_to: date, branch_id: int | None = None):
    q = (
        db.session.query(
            Quest.title,
            func.count(Booking.id).label("bookings_count"),
        )
        .join(Slot, Slot.quest_id == Quest.id)
        .join(Booking, Booking.slot_id == Slot.id)
        .filter(Booking.status != BOOKING_CANCELED)
    )
    if branch_id:
        from app.models.location import Location
        q = q.join(Room, Room.id == Slot.room_id).join(Location, Location.id == Room.location_id).filter(
            Location.branch_id == branch_id
        )
    q = _date_range_filter(q, Booking.created_at, date_from, date_to).group_by(Quest.id)
    return [{"quest": title, "bookings_count": cnt} for title, cnt in q.order_by(func.count(Booking.id).desc()).all()]


def host_effectiveness_report(date_from: date, date_to: date, branch_id: int | None = None):
    """Эффективность администраторов, оформивших бронирования (created_by)."""
    q = (
        db.session.query(User.full_name, func.count(Booking.id))
        .join(Booking, Booking.created_by_id == User.id)
        .filter(Booking.status != BOOKING_CANCELED)
    )
    if branch_id:
        from app.models.location import Location
        q = (
            q.join(Slot, Slot.id == Booking.slot_id)
            .join(Room, Room.id == Slot.room_id)
            .join(Location, Location.id == Room.location_id)
            .filter(Location.branch_id == branch_id)
        )
    q = _date_range_filter(q, Booking.created_at, date_from, date_to).group_by(User.id)
    return [{"host": name, "bookings_count": cnt} for name, cnt in q.all()]


def kpi_dashboard(branch_id: int | None = None):
    """Ключевые показатели в реальном времени для дашборда руководителя (ТЗ п.4.2.7)."""
    today = date.today()
    month_start = today.replace(day=1)
    rev = revenue_report(month_start, today, branch_id)
    occ = occupancy_report(month_start, today, branch_id)
    avg_occupancy = round(sum(r["occupancy_pct"] for r in occ) / len(occ), 1) if occ else 0.0
    return {
        "period": f"{month_start:%d.%m.%Y} — {today:%d.%m.%Y}",
        **rev,
        "avg_occupancy_pct": avg_occupancy,
    }


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    """Защита от CSV/Excel formula injection (OWASP): текст, начинающийся с = + - @ (или
    табуляции/CR), Excel и LibreOffice исполнили бы как формулу. Такие значения экранируются
    ведущим апострофом; числа, даты и None остаются как есть."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def export_rows_to_csv(rows: list[dict]) -> io.BytesIO:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows({k: _safe_cell(v) for k, v in row.items()} for row in rows)
    buf = io.BytesIO(output.getvalue().encode("utf-8-sig"))  # BOM для корректного Excel
    buf.seek(0)
    return buf


def export_rows_to_xlsx(rows: list[dict], sheet_title: str = "Отчёт") -> io.BytesIO:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([_safe_cell(row[h]) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
