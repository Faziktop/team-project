"""Фоновые регламентные задачи. ТЗ п.4.2.4: планировщик для отправки уведомлений
по расписанию, формирования отчётов и прочих регламентных операций.

Каждая задача идемпотентна (использует флаги reminder_*_sent / review_request_sent),
поэтому безопасна при повторном запуске / нескольких воркерах с общей БД.
"""
import logging
from datetime import datetime

logger = logging.getLogger("questevent.tasks")


def send_due_reminders(app):
    """Отправляет напоминания за 24ч и за 2ч, а также запросы отзыва после игры.

    Slot.start_time/end_time хранятся как наивные datetime в местном времени
    площадки (как их вводит администратор при генерации расписания — «с 10:00
    до 22:00»), а не в UTC. Поэтому сравнение ведётся с наивным местным
    `datetime.now()`, а не с UTC — иначе на сервере в часовом поясе, отличном
    от UTC, напоминания уходили бы со сдвигом на разницу поясов.
    """
    with app.app_context():
        from app.models import Booking
        from app.constants import BOOKING_CONFIRMED, BOOKING_COMPLETED
        from app.services import notification_service, booking_service
        from app.extensions import db

        now = datetime.now()
        hours_24 = app.config["REMINDER_24H_HOURS_BEFORE"]
        hours_2 = app.config["REMINDER_2H_HOURS_BEFORE"]
        review_delay = app.config["REVIEW_REQUEST_DELAY"]

        confirmed = Booking.query.filter_by(status=BOOKING_CONFIRMED).all()
        for booking in confirmed:
            # Сбой на одной брони (например, в уведомлении) не должен останавливать обработку остальных
            try:
                slot = booking.slot
                hours_left = (slot.start_time - now).total_seconds() / 3600.0

                if hours_left > 0:
                    if not booking.reminder_2h_sent and hours_left <= hours_2:
                        notification_service.notify_reminder(booking, hours_2)
                        # Если бронь оформлена уже «впритык», напоминание за 24 ч теряет смысл —
                        # не шлём клиенту два почти одинаковых сообщения подряд.
                        booking.reminder_2h_sent = True
                        booking.reminder_24h_sent = True
                        db.session.commit()
                    elif not booking.reminder_24h_sent and hours_left <= hours_24:
                        notification_service.notify_reminder(booking, hours_24)
                        booking.reminder_24h_sent = True
                        db.session.commit()

                # Игра считается проведённой после ОКОНЧАНИЯ сеанса (а не в момент начала)
                if slot.end_time <= now:
                    booking_service.mark_completed(booking)
            except Exception:  # noqa: BLE001
                db.session.rollback()
                logger.exception("Ошибка обработки брони id=%s в регламентной задаче", booking.id)

        completed = Booking.query.filter_by(status=BOOKING_COMPLETED, review_request_sent=False).all()
        for booking in completed:
            try:
                if now - booking.slot.end_time >= review_delay:
                    notification_service.notify_review_request(booking)
                    booking.review_request_sent = True
                    db.session.commit()
            except Exception:  # noqa: BLE001
                db.session.rollback()
                logger.exception("Ошибка запроса отзыва по брони id=%s", booking.id)
