"""Уведомления клиентам и сотрудникам. ТЗ п.4.2.5.

Работает полностью локально: уведомление записывается в лог приложения и в
таблицу Notification (видна в БД/UI), без обращения к какому-либо внешнему
почтовому/SMS-серверу. Вся логика "когда и кому отправлять" (подтверждение
брони, напоминания, запрос отзыва) уже реализована и покрыта тестами —
при необходимости позже строку с логированием можно заменить вызовом
конкретного почтового/SMS-сервиса.
"""
import logging

from app.extensions import db
from app.models.notification import Notification
from app.constants import (
    CHANNEL_EMAIL, CHANNEL_SMS,
    NOTIF_BOOKING_CONFIRMED, NOTIF_NEW_BOOKING_FOR_ADMIN, NOTIF_BOOKING_CANCELED,
    NOTIF_REVIEW_REQUEST, ROLE_LOCATION_ADMIN, ROLE_SUPERADMIN,
)
from app.security import sanitize_for_log

logger = logging.getLogger("questevent.notifications")


def send_notification(channel: str, recipient: str, subject: str, body: str,
                       notif_type: str, booking_id: int | None = None, user_id: int | None = None):
    """Фиксирует уведомление в логе приложения и в таблице Notification."""
    ok = bool(recipient)
    if ok:
        # Тема/текст содержат имя клиента (вводится пользователем): вычищаем переводы строк,
        # чтобы нельзя было подделать строки журнала (log injection)
        logger.info("[%s -> %s] %s :: %s", channel.upper(), sanitize_for_log(recipient, 150),
                    sanitize_for_log(subject, 200), sanitize_for_log(body, 1000))

    entry = Notification(
        booking_id=booking_id,
        user_id=user_id,
        channel=channel,
        notif_type=notif_type,
        recipient=recipient or "",
        subject=subject,
        body=body,
        status="sent" if ok else "failed",
    )
    db.session.add(entry)
    db.session.commit()
    return ok


def notify_booking_confirmed(booking):
    client = booking.client
    slot = booking.slot
    subject = f"Бронирование подтверждено — {booking.confirmation_code}"
    body = (
        f"Здравствуйте, {client.full_name}! Ваше бронирование квеста "
        f"«{slot.quest.title}» на {slot.start_time:%d.%m.%Y %H:%M} подтверждено. "
        f"Код бронирования: {booking.confirmation_code}."
    )
    if client.email:
        send_notification(CHANNEL_EMAIL, client.email, subject, body, NOTIF_BOOKING_CONFIRMED, booking.id, client.id)
    if client.phone:
        send_notification(CHANNEL_SMS, client.phone, subject, body, NOTIF_BOOKING_CONFIRMED, booking.id, client.id)

    # Уведомление администраторам локации
    admins = [u for u in slot.room.location.branch.users
              if u.role in (ROLE_LOCATION_ADMIN, ROLE_SUPERADMIN) and u.is_active
              and (u.branch_id == slot.room.location.branch_id or u.role == ROLE_SUPERADMIN)]
    for admin in admins:
        if admin.email:
            send_notification(
                CHANNEL_EMAIL, admin.email,
                f"Новая бронь: {slot.quest.title} {slot.start_time:%d.%m %H:%M}",
                f"Клиент {client.full_name} забронировал «{slot.quest.title}» на {slot.start_time:%d.%m.%Y %H:%M}.",
                NOTIF_NEW_BOOKING_FOR_ADMIN, booking.id, admin.id,
            )


def notify_booking_canceled(booking, reason: str = ""):
    client = booking.client
    subject = f"Бронирование отменено — {booking.confirmation_code}"
    body = f"Ваше бронирование {booking.confirmation_code} отменено. Причина: {reason or 'не указана'}."
    if client.email:
        send_notification(CHANNEL_EMAIL, client.email, subject, body, NOTIF_BOOKING_CANCELED, booking.id, client.id)


def notify_reminder(booking, hours_before: int):
    client = booking.client
    slot = booking.slot
    subject = f"Напоминание: игра через {hours_before} ч."
    body = (
        f"Напоминаем: «{slot.quest.title}» состоится {slot.start_time:%d.%m.%Y %H:%M} "
        f"(через {hours_before} ч.). Код брони: {booking.confirmation_code}."
    )
    if client.email:
        send_notification(CHANNEL_EMAIL, client.email, subject, body, f"reminder_{hours_before}h", booking.id, client.id)
    if client.phone:
        send_notification(CHANNEL_SMS, client.phone, subject, body, f"reminder_{hours_before}h", booking.id, client.id)


def notify_review_request(booking):
    client = booking.client
    subject = "Как прошла игра? Оставьте отзыв"
    body = f"Спасибо за игру «{booking.slot.quest.title}»! Будем рады вашему отзыву."
    if client.email:
        send_notification(CHANNEL_EMAIL, client.email, subject, body, NOTIF_REVIEW_REQUEST, booking.id, client.id)
