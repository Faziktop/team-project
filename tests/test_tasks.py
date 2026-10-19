"""Регламентные задачи: напоминания, завершение игр, запрос отзыва."""
from datetime import datetime, timedelta

from app import create_app
from app.constants import BOOKING_COMPLETED, BOOKING_CONFIRMED
from app.models import Booking, Notification, Slot
from app.services import booking_service
from app.tasks.reminders import send_due_reminders


def _shift(booking, db, start_in_hours, duration_h=1):
    now = datetime.now()
    booking.slot.start_time = now + timedelta(hours=start_in_hours)
    booking.slot.end_time = now + timedelta(hours=start_in_hours + duration_h)
    db.session.commit()


def _count(kind):
    return Notification.query.filter(Notification.notif_type == kind).count()


def test_24h_reminder_sent_once(app, db, demo_data):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    _shift(b, db, start_in_hours=20)
    send_due_reminders(app)
    send_due_reminders(app)  # идемпотентность: повторный запуск не дублирует
    assert _count("reminder_24h") == 1 and _count("reminder_2h") == 0
    assert db.session.get(Booking, b.id).reminder_24h_sent


def test_late_booking_gets_only_2h_reminder(app, db, demo_data):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    _shift(b, db, start_in_hours=1)
    send_due_reminders(app)
    assert _count("reminder_2h") == 1 and _count("reminder_24h") == 0


def test_game_completed_only_after_it_ends(app, db, demo_data):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    _shift(b, db, start_in_hours=-0.5, duration_h=1)  # игра идёт прямо сейчас
    send_due_reminders(app)
    assert db.session.get(Booking, b.id).status == BOOKING_CONFIRMED
    _shift(b, db, start_in_hours=-2, duration_h=1)    # игра закончилась
    send_due_reminders(app)
    assert db.session.get(Booking, b.id).status == BOOKING_COMPLETED


def test_review_request_after_delay(app, db, demo_data):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    _shift(b, db, start_in_hours=-10, duration_h=1)
    demo_data["client_user"].email = "c@example.com"
    db.session.commit()
    send_due_reminders(app)  # завершает
    send_due_reminders(app)  # шлёт запрос отзыва
    assert _count("review_request") == 1
    send_due_reminders(app)
    assert _count("review_request") == 1


def test_canceled_booking_gets_no_reminders(app, db, demo_data):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    booking_service.cancel_booking(b, "тест")
    _shift(b, db, start_in_hours=1)
    send_due_reminders(app)
    assert _count("reminder_2h") == 0 and _count("reminder_24h") == 0


def test_one_failing_booking_does_not_stop_others(app, db, demo_data, monkeypatch):
    from app.services import notification_service
    b1 = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    b2 = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][1].id, 2)
    _shift(b1, db, start_in_hours=1)
    _shift(b2, db, start_in_hours=1)
    real = notification_service.notify_reminder
    calls = {"n": 0}

    def flaky(booking, hours):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("сбой почтового сервера")
        return real(booking, hours)

    monkeypatch.setattr(notification_service, "notify_reminder", flaky)
    send_due_reminders(app)
    assert calls["n"] == 2  # вторая бронь обработана, несмотря на сбой первой


def test_notification_failure_does_not_undo_booking(app, db, demo_data, monkeypatch):
    from app.services import notification_service

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notification_service, "notify_booking_confirmed", boom)
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    assert db.session.get(Booking, b.id).status == BOOKING_CONFIRMED


def test_log_injection_is_neutralized(app, db, demo_data, caplog):
    import logging
    demo_data["client_user"].full_name = "Иван\nERROR фальшивая запись журнала"
    demo_data["client_user"].email = "x@example.com"
    db.session.commit()
    with caplog.at_level(logging.INFO, logger="questevent.notifications"):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    assert caplog.records and all("\n" not in r.getMessage() for r in caplog.records)


def test_scheduler_not_started_twice_under_reloader(monkeypatch):
    from app import _should_start_scheduler
    app = create_app("testing")
    app.debug = True
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert _should_start_scheduler(app) is False          # родительский процесс reloader'а
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    assert _should_start_scheduler(app) is True           # рабочий процесс
    app.debug = False
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert _should_start_scheduler(app) is True           # production/gunicorn
    monkeypatch.setenv("QE_DISABLE_SCHEDULER", "1")
    assert _should_start_scheduler(app) is False          # flask db / seed
