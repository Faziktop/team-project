"""Оркестрация создания/отмены/завершения бронирований.

Ключевое требование ТЗ п.2.2.2 и п.4.2.1: «автоматический контроль конфликтов
и блокировка двойного бронирования одного слота». Реализовано двумя рубежами
защиты:
  1) проверка статуса Slot.status == available перед созданием брони;
  2) частичный уникальный индекс (slot_id) WHERE status != 'canceled' на Booking
     и уникальность (room_id, start_time) на Slot на уровне БД — при гонке запросов
     вторая транзакция получит IntegrityError, который превращается в понятную ошибку.

Счётчики промокодов и баланс сертификатов изменяются атомарными UPDATE ... WHERE
(а не «прочитал → изменил → записал в Python»), поэтому два параллельных запроса не
смогут вместе превысить лимит промокода или потратить один рубль сертификата дважды.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import case, or_, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.slot import Slot
from app.models.booking import Booking
from app.models.certificate import Certificate
from app.models.promocode import PromoCode
from app.models.room import ROOM_STATUS_MAINTENANCE
from app.constants import (
    SLOT_AVAILABLE, SLOT_BOOKED, SLOT_COMPLETED,
    BOOKING_CONFIRMED, BOOKING_CANCELED, BOOKING_COMPLETED, BOOKING_NO_SHOW,
    ROLE_CLIENT, MAX_TEXT_FIELD_LENGTH,
)
from app.services import pricing_service, notification_service
from app.services.exceptions import SlotConflictError, ValidationError
from app.services.audit_service import log_action

logger = logging.getLogger("questevent.booking")


# ---------------------------------------------------------------------------
# Вспомогательные проверки
# ---------------------------------------------------------------------------
def _ensure_slot_bookable(slot: Slot, by_staff: bool, allow_past: bool = False) -> None:
    """Сеанс должен быть доступен для продажи: квест/комната/локация активны, комната не на
    обслуживании и время сеанса ещё не прошло. Слоты «на будущее» могли быть созданы до
    того, как комнату вывели на обслуживание, поэтому одной проверки статуса слота мало."""
    quest, room = slot.quest, slot.room
    if not quest.is_active:
        raise ValidationError("Этот квест сейчас недоступен для бронирования")
    if not room.is_active or room.status == ROOM_STATUS_MAINTENANCE:
        raise ValidationError("Комната временно недоступна (обслуживание)")
    if not room.location.is_active:
        raise ValidationError("Локация временно закрыта для бронирования")
    if quest.room_id != slot.room_id:
        # Защита от рассинхронизации данных: сеанс, где квест не относится к комнате
        raise ValidationError("Сеанс настроен некорректно, обратитесь к администратору")

    if allow_past:
        return  # только для загрузки исторических данных (seed/импорт), см. create_booking

    now = datetime.now()  # Slot.start_time хранится как naive местное время площадки
    # Персонал может оформить «живую» очередь до окончания сеанса, клиент — только до начала
    deadline = slot.end_time if by_staff else slot.start_time
    if deadline <= now:
        raise ValidationError("Этот сеанс уже начался или прошёл — выберите другое время")


def _reserve_promo_use(promo: PromoCode) -> None:
    """Атомарно занимает одно использование промокода (или падает, если лимит исчерпан)."""
    result = db.session.execute(
        update(PromoCode)
        .where(
            PromoCode.id == promo.id,
            or_(PromoCode.usage_limit.is_(None), PromoCode.usage_limit == 0,
                PromoCode.used_count < PromoCode.usage_limit),
        )
        .values(used_count=PromoCode.used_count + 1)
    )
    if result.rowcount != 1:
        raise ValidationError("Промокод недействителен или исчерпан")


def _release_promo_use(promo_id: int) -> None:
    db.session.execute(
        update(PromoCode)
        .where(PromoCode.id == promo_id, PromoCode.used_count > 0)
        .values(used_count=PromoCode.used_count - 1)
    )


def _spend_certificate(certificate: Certificate, amount: Decimal) -> None:
    """Атомарно списывает сумму с сертификата: баланс не может уйти в минус."""
    result = db.session.execute(
        update(Certificate)
        .where(Certificate.id == certificate.id, Certificate.is_active.is_(True),
               Certificate.balance >= amount)
        .values(balance=Certificate.balance - amount)
    )
    if result.rowcount != 1:
        raise ValidationError("Сертификат недействителен или на нём недостаточно средств")


def _refund_certificate(certificate_id: int, amount: Decimal) -> None:
    """Возвращает сумму на сертификат, но не выше его номинала."""
    new_balance = Certificate.balance + amount
    db.session.execute(
        update(Certificate)
        .where(Certificate.id == certificate_id)
        .values(balance=case((new_balance > Certificate.initial_balance, Certificate.initial_balance),
                             else_=new_balance))
    )


def _notify_safely(func, *args) -> None:
    """Уведомления не должны ронять уже выполненную операцию (бронь уже сохранена)."""
    try:
        func(*args)
    except Exception:  # noqa: BLE001 - сбой уведомления не должен отменять бронь
        db.session.rollback()
        logger.exception("Не удалось отправить уведомление (%s)", getattr(func, "__name__", func))


# ---------------------------------------------------------------------------
# Публичный API сервиса
# ---------------------------------------------------------------------------
def create_booking(client, slot_id: int, players_count: int, promo_code: str | None = None,
                    certificate_code: str | None = None, source: str = "widget", created_by=None,
                    comment: str | None = None, allow_past: bool = False) -> Booking:
    """Создаёт бронь на свободный сеанс.

    allow_past=True отключает проверку «сеанс ещё не начался» — предназначено ТОЛЬКО для
    загрузки исторических данных (seed.py, импорт); в веб-слое не используется.
    """
    if not client.is_active:
        raise ValidationError("Учётная запись клиента заблокирована — бронирование недоступно")

    slot = db.session.get(Slot, slot_id)
    if slot is None:
        raise ValidationError("Слот не найден")
    if slot.status != SLOT_AVAILABLE:
        raise SlotConflictError("Выбранное время уже занято либо недоступно")
    _ensure_slot_bookable(slot, by_staff=created_by is not None, allow_past=allow_past)

    promo = None
    if promo_code:
        promo = PromoCode.query.filter_by(code=promo_code.strip().upper()).first()
        if not promo or not promo.is_valid(slot.start_time.date()):
            raise ValidationError("Промокод недействителен")

    pricing = pricing_service.calculate_price(
        slot.quest, slot.start_time.date(), slot.start_time.strftime("%H:%M"),
        players_count, promo,
    )

    certificate = None
    cert_used = Decimal("0")
    if certificate_code:
        certificate = Certificate.query.filter_by(code=certificate_code.strip().upper()).first()
        if not certificate or not certificate.is_valid(slot.start_time.date()):
            raise ValidationError("Сертификат недействителен или исчерпан")
        cert_used, _ = pricing_service.apply_certificate(pricing["final_price"], certificate)

    # Рубеж защиты №1: помечаем слот занятым до создания брони
    slot.status = SLOT_BOOKED

    booking = Booking(
        slot_id=slot.id,
        client_id=client.id,
        created_by_id=created_by.id if created_by else None,
        players_count=players_count,
        status=BOOKING_CONFIRMED,
        base_price=pricing["base_price"],
        discount_amount=pricing["discount_amount"],
        final_price=pricing["final_price"],
        promocode_id=promo.id if promo else None,
        certificate_id=certificate.id if certificate else None,
        certificate_amount_used=cert_used,
        source=source,
        comment=(comment or "").strip()[:500] or None,
    )
    db.session.add(booking)

    try:
        db.session.flush()  # рубеж защиты №2 — сработает уникальный индекс при гонке
    except IntegrityError:
        db.session.rollback()
        raise SlotConflictError("Слот только что был забронирован другим клиентом")

    try:
        if promo:
            _reserve_promo_use(promo)
        if certificate and cert_used > 0:
            _spend_certificate(certificate, cert_used)
    except ValidationError:
        # Лимит промокода/баланс сертификата исчерпали параллельные запросы: откатываем всё
        # (включая слот и запись брони), чтобы не оставить «полузавершённую» бронь.
        db.session.rollback()
        raise

    log_action("booking_created", "Booking", booking.id, f"slot={slot.id} players={players_count}")
    db.session.commit()
    _notify_safely(notification_service.notify_booking_confirmed, booking)

    return booking


def cancel_booking(booking: Booking, reason: str = "", initiated_by=None) -> Booking:
    """Отменяет бронь, освобождает слот, возвращает использование промокода и деньги сертификата.

    Отмена невозможна для уже проведённой игры и неявки (иначе слот прошедшего времени
    снова стал бы «свободным»), а клиент не может отменить игру, которая уже началась.
    """
    if booking.status == BOOKING_CANCELED:
        return booking
    if booking.status in (BOOKING_COMPLETED, BOOKING_NO_SHOW):
        raise ValidationError("Нельзя отменить бронь: игра уже проведена")

    by_client = initiated_by is None or initiated_by.role == ROLE_CLIENT
    if by_client and booking.slot.start_time <= datetime.now():
        raise ValidationError("Игра уже началась — отмена невозможна, обратитесь к администратору")

    reason = (reason or "").strip()[:MAX_TEXT_FIELD_LENGTH]
    booking.status = BOOKING_CANCELED
    booking.canceled_at = datetime.now(timezone.utc)
    booking.cancel_reason = reason
    booking.slot.status = SLOT_AVAILABLE

    if booking.promocode_id:
        _release_promo_use(booking.promocode_id)
    if booking.certificate_id and booking.certificate_amount_used:
        _refund_certificate(booking.certificate_id, Decimal(booking.certificate_amount_used))

    log_action("booking_canceled", "Booking", booking.id,
               f"reason={reason} by={initiated_by.id if initiated_by else 'client'}")
    db.session.commit()
    _notify_safely(notification_service.notify_booking_canceled, booking, reason)
    return booking


def mark_completed(booking: Booking) -> Booking:
    """Отмечает игру проведённой. Допустимо только для подтверждённой брони: иначе можно было бы
    «провести» отменённую бронь и перевести освободившийся слот в статус «проведён»."""
    if booking.status != BOOKING_CONFIRMED:
        raise ValidationError("Отметить проведённой можно только подтверждённую бронь")
    booking.status = BOOKING_COMPLETED
    booking.slot.status = SLOT_COMPLETED
    log_action("booking_completed", "Booking", booking.id)
    db.session.commit()
    return booking


def mark_no_show(booking: Booking) -> Booking:
    """Клиент не пришёл. Допустимо только для подтверждённой брони после начала сеанса."""
    if booking.status != BOOKING_CONFIRMED:
        raise ValidationError("Неявку можно отметить только для подтверждённой брони")
    if booking.slot.start_time > datetime.now():
        raise ValidationError("Сеанс ещё не начался — неявку отметить нельзя")
    booking.status = BOOKING_NO_SHOW
    booking.slot.status = SLOT_COMPLETED
    log_action("booking_no_show", "Booking", booking.id)
    db.session.commit()
    return booking
