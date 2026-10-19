"""Правила бронирования: отмена, промокоды, сертификаты, доступность сеансов."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.constants import (
    BOOKING_CANCELED, BOOKING_COMPLETED, BOOKING_NO_SHOW, SLOT_AVAILABLE, ROLE_MANAGER,
)
from app.models import PromoCode, Certificate, Slot, User
from app.models.room import ROOM_STATUS_MAINTENANCE
from app.services import booking_service, schedule_service
from app.services.exceptions import ValidationError, SlotConflictError


def _promo(db, limit=1, percent=10):
    p = PromoCode(code="TESTPROMO", discount_percent=percent, usage_limit=limit)
    db.session.add(p)
    db.session.commit()
    return p


def _cert(db, balance=1500):
    c = Certificate(code="TESTCERT", initial_balance=balance, balance=balance,
                    expires_at=date.today() + timedelta(days=30))
    db.session.add(c)
    db.session.commit()
    return c


def test_cancel_returns_promo_use(demo_data, db):
    promo = _promo(db, limit=1)
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2, promo_code="testpromo")
    assert db.session.get(PromoCode, promo.id).used_count == 1
    booking_service.cancel_booking(b, "тест")
    assert db.session.get(PromoCode, promo.id).used_count == 0


def test_promo_limit_cannot_be_exceeded(demo_data, db):
    _promo(db, limit=1)
    booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2, promo_code="TESTPROMO")
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][1].id, 2, promo_code="TESTPROMO")


def test_promo_atomic_guard_rejects_when_limit_reached_concurrently(demo_data, db):
    """Имитация гонки: is_valid() пройден, но другой запрос уже занял последнее использование."""
    promo = _promo(db, limit=1)
    slot_id = demo_data["slots"][0].id
    real_is_valid = PromoCode.is_valid
    PromoCode.is_valid = lambda self, on_date=None: True  # «устаревшая» проверка в Python
    try:
        promo.used_count = 1  # параллельный запрос уже списал единственное использование
        db.session.commit()
        with pytest.raises(ValidationError):
            booking_service.create_booking(demo_data["client_user"], slot_id, 2, promo_code="TESTPROMO")
    finally:
        PromoCode.is_valid = real_is_valid
    # слот не должен остаться «занятым» после неудачной попытки
    assert db.session.get(Slot, slot_id).status == SLOT_AVAILABLE


def test_certificate_spent_and_refunded_not_above_nominal(demo_data, db):
    cert = _cert(db, balance=1500)
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2, certificate_code="TESTCERT")
    assert Decimal(db.session.get(Certificate, cert.id).balance) == Decimal("500")
    booking_service.cancel_booking(b, "тест")
    assert Decimal(db.session.get(Certificate, cert.id).balance) == Decimal("1500")


def test_certificate_refund_is_capped_at_initial_balance(demo_data, db):
    cert = _cert(db, balance=1500)
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2, certificate_code="TESTCERT")
    cert = db.session.get(Certificate, cert.id)
    cert.balance = Decimal("1400")  # «лишние» деньги на балансе, например после ручной правки
    db.session.commit()
    booking_service.cancel_booking(b, "тест")
    assert Decimal(db.session.get(Certificate, cert.id).balance) == Decimal("1500")


@pytest.mark.parametrize("final_status", [BOOKING_COMPLETED, BOOKING_NO_SHOW])
def test_cannot_cancel_finished_booking(demo_data, db, final_status):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    b.status = final_status
    db.session.commit()
    with pytest.raises(ValidationError):
        booking_service.cancel_booking(b, "поздно")
    assert b.status == final_status


def test_cannot_complete_canceled_booking(demo_data, db):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    booking_service.cancel_booking(b, "тест")
    with pytest.raises(ValidationError):
        booking_service.mark_completed(b)
    assert b.slot.status == SLOT_AVAILABLE


def test_cancel_is_idempotent(demo_data, db):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    booking_service.cancel_booking(b, "1")
    assert booking_service.cancel_booking(b, "2").cancel_reason == "1"


def test_cannot_book_past_slot(demo_data, db):
    past = Slot(room_id=demo_data["room"].id, quest_id=demo_data["quest"].id,
                start_time=datetime.now() - timedelta(hours=5), end_time=datetime.now() - timedelta(hours=4))
    db.session.add(past)
    db.session.commit()
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], past.id, 2)


def test_client_cannot_cancel_started_game_but_staff_can(demo_data, db):
    now = datetime.now()
    slot = Slot(room_id=demo_data["room"].id, quest_id=demo_data["quest"].id,
                start_time=now + timedelta(minutes=5), end_time=now + timedelta(minutes=65))
    db.session.add(slot)
    db.session.commit()
    b = booking_service.create_booking(demo_data["client_user"], slot.id, 2)
    slot.start_time = now - timedelta(minutes=10)  # игра началась
    db.session.commit()
    with pytest.raises(ValidationError):
        booking_service.cancel_booking(b, "клиент", initiated_by=demo_data["client_user"])
    staff = User(role=ROLE_MANAGER, full_name="М", email="m@example.com", branch_id=demo_data["branch"].id)
    db.session.add(staff)
    db.session.commit()
    booking_service.cancel_booking(b, "сотрудник", initiated_by=staff)
    assert b.status == BOOKING_CANCELED


def test_cannot_book_when_room_in_maintenance(demo_data, db):
    demo_data["room"].status = ROOM_STATUS_MAINTENANCE
    db.session.commit()
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)


def test_cannot_book_inactive_quest(demo_data, db):
    demo_data["quest"].is_active = False
    db.session.commit()
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)


def test_blocked_client_cannot_book(demo_data, db):
    demo_data["client_user"].is_active_flag = False
    db.session.commit()
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)


@pytest.mark.parametrize("players", [1, 7, 0, -3])
def test_players_out_of_range_rejected(demo_data, players):
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, players)


def test_double_booking_after_failed_attempt_is_still_possible_for_others(demo_data, db):
    with pytest.raises(ValidationError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 99)
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    assert b.status != BOOKING_CANCELED
    with pytest.raises(SlotConflictError):
        booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)


def test_no_show_only_after_start(demo_data, db):
    b = booking_service.create_booking(demo_data["client_user"], demo_data["slots"][0].id, 2)
    with pytest.raises(ValidationError):  # сеанс завтра
        booking_service.mark_no_show(b)


# ------------------------------------------------------------------ расписание
def test_slot_generation_rejects_foreign_quest(two_branches):
    a, b = two_branches["a"], two_branches["b"]
    with pytest.raises(ValidationError):
        schedule_service.generate_slots_for_room(
            a["room"], b["quest"], date.today() + timedelta(days=3), date.today() + timedelta(days=3),
            time(10, 0), time(12, 0))


def test_slot_generation_limits_and_validation(demo_data):
    room, quest = demo_data["room"], demo_data["quest"]
    d = date.today() + timedelta(days=5)
    with pytest.raises(ValidationError):
        schedule_service.generate_slots_for_room(room, quest, d, d + timedelta(days=400), time(10), time(12))
    with pytest.raises(ValidationError):
        schedule_service.generate_slots_for_room(room, quest, d, d, time(12), time(10))
    with pytest.raises(ValidationError):
        schedule_service.generate_slots_for_room(room, quest, d + timedelta(days=1), d, time(10), time(12))


def test_slot_generation_is_idempotent(demo_data, db):
    room, quest = demo_data["room"], demo_data["quest"]
    d = date.today() + timedelta(days=1)
    again = schedule_service.generate_slots_for_room(room, quest, d, d, time(10), time(18))
    assert again == []  # все слоты уже существуют


def test_available_slots_hide_maintenance_and_past(demo_data, db):
    d = date.today() + timedelta(days=1)
    before = schedule_service.get_available_slots(demo_data["quest"].id, d, d)
    assert len(before) == len(demo_data["slots"]) > 0
    demo_data["room"].status = ROOM_STATUS_MAINTENANCE
    db.session.commit()
    assert schedule_service.get_available_slots(demo_data["quest"].id, d, d) == []
