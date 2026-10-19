import pytest

from app.services import booking_service
from app.services.exceptions import SlotConflictError, ValidationError
from app.models import Slot
from app.constants import SLOT_AVAILABLE, SLOT_BOOKED, BOOKING_CONFIRMED, BOOKING_CANCELED


def test_create_booking_success(demo_data, db):
    slot = demo_data["slots"][0]
    client = demo_data["client_user"]

    booking = booking_service.create_booking(client, slot.id, players_count=2)

    assert booking.status == BOOKING_CONFIRMED
    assert float(booking.final_price) == 1000
    assert db.session.get(Slot, slot.id).status == SLOT_BOOKED


def test_double_booking_is_rejected(demo_data):
    slot = demo_data["slots"][0]
    client = demo_data["client_user"]
    booking_service.create_booking(client, slot.id, players_count=2)

    with pytest.raises(SlotConflictError):
        booking_service.create_booking(client, slot.id, players_count=2)


def test_cancel_frees_the_slot(demo_data, db):
    slot = demo_data["slots"][0]
    client = demo_data["client_user"]
    booking = booking_service.create_booking(client, slot.id, players_count=2)

    booking_service.cancel_booking(booking, reason="test")

    assert booking.status == BOOKING_CANCELED
    assert db.session.get(Slot, slot.id).status == SLOT_AVAILABLE


def test_rebooking_after_cancellation_succeeds(demo_data):
    slot = demo_data["slots"][0]
    client = demo_data["client_user"]
    b1 = booking_service.create_booking(client, slot.id, players_count=2)
    booking_service.cancel_booking(b1, reason="test")

    b2 = booking_service.create_booking(client, slot.id, players_count=3)
    assert b2.status == BOOKING_CONFIRMED
    assert b2.id != b1.id


def test_invalid_players_count_raises(demo_data):
    slot = demo_data["slots"][0]
    client = demo_data["client_user"]
    with pytest.raises(ValidationError):
        booking_service.create_booking(client, slot.id, players_count=50)


def test_promocode_discount_applied(demo_data, db):
    from app.models import PromoCode
    promo = PromoCode(code="TEST10", discount_percent=10)
    db.session.add(promo)
    db.session.commit()

    slot = demo_data["slots"][0]
    client = demo_data["client_user"]
    booking = booking_service.create_booking(client, slot.id, players_count=2, promo_code="TEST10")

    assert float(booking.discount_amount) == 100  # 10% of 1000
    assert float(booking.final_price) == 900


def test_certificate_partial_redemption(demo_data, db):
    from app.models import Certificate
    cert = Certificate(code="CERT500", initial_balance=500, balance=500)
    db.session.add(cert)
    db.session.commit()

    slot = demo_data["slots"][0]
    client = demo_data["client_user"]
    booking = booking_service.create_booking(client, slot.id, players_count=2, certificate_code="CERT500")

    assert booking.status == BOOKING_CONFIRMED
    assert float(booking.certificate_amount_used) == 500
    assert float(db.session.get(Certificate, cert.id).balance) == 0
