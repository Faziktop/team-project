"""Сценарии администрирования и клиентского кабинета (счастливые пути + отказы)."""
from datetime import datetime, timedelta

from app.constants import ROLE_SUPERADMIN, ROLE_MANAGER, BOOKING_COMPLETED
from app.models import Branch, Location, Room, Quest, Tariff, Review, User, Booking, AuditLog
from app.services import booking_service
from tests.conftest import login


def _superadmin(db):
    sa = User(role=ROLE_SUPERADMIN, full_name="Root", email="root_crud@example.com")
    sa.set_password("Root-pass-2026")
    db.session.add(sa)
    db.session.commit()
    return sa


def test_superadmin_full_setup_flow_and_audit(client, db):
    _superadmin(db)
    login(client, "root_crud@example.com", "Root-pass-2026")
    assert client.post("/admin/branches/new", data={"name": "Новый", "city": "Казань"}).status_code == 302
    branch = Branch.query.filter_by(name="Новый").first()
    assert client.post("/admin/locations/new", data={"branch_id": branch.id, "name": "Л1", "address": "ул. 1"}).status_code == 302
    loc = Location.query.filter_by(name="Л1").first()
    assert client.post("/admin/rooms/new", data={"location_id": loc.id, "name": "К1", "status": "ok"}).status_code == 302
    room = Room.query.filter_by(name="К1").first()
    r = client.post("/admin/quests/new", data={"room_id": room.id, "title": "Q", "difficulty": "средний", "duration_minutes": "60",
                                              "min_players": "2", "max_players": "6", "is_horror": "y"})
    assert r.status_code == 302 and Quest.query.filter_by(title="Q").first().is_horror
    quest = Quest.query.filter_by(title="Q").first()
    r = client.post("/admin/tariffs/new", data={"quest_id": quest.id, "name": "Будни", "price_per_slot": "900",
                                                "time_from": "10:00", "time_to": "20:00", "weekday": ["0", "1", "9", "x"]})
    assert r.status_code == 302
    assert Tariff.query.filter_by(name="Будни").first().weekdays() == {0, 1}   # мусорные дни отброшены
    actions = {a.action for a in AuditLog.query.all()}
    assert {"branch_created", "location_created", "room_created", "quest_created", "tariff_created"} <= actions


def test_quest_min_players_cannot_exceed_max(client, db):
    _superadmin(db)
    b = Branch(name="B"); db.session.add(b); db.session.flush()
    loc = Location(branch_id=b.id, name="L", address="a"); db.session.add(loc); db.session.flush()
    room = Room(location_id=loc.id, name="R"); db.session.add(room); db.session.commit()
    login(client, "root_crud@example.com", "Root-pass-2026")
    r = client.post("/admin/quests/new", data={"room_id": room.id, "title": "Bad", "difficulty": "средний", "duration_minutes": "60",
                                              "min_players": "8", "max_players": "3"})
    assert r.status_code == 200 and Quest.query.filter_by(title="Bad").first() is None


def test_maintenance_toggle_warns_about_future_bookings(client, db, two_branches):
    a = two_branches["a"]
    booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, a["admin"].email, a["admin_pw"])
    r = client.post(f"/admin/rooms/{a['room'].id}/maintenance", data={"note": "Ремонт"}, follow_redirects=True)
    assert "подтверждённые будущие брони" in r.get_data(as_text=True)
    assert db.session.get(Room, a["room"].id).status == "maintenance"
    client.post(f"/admin/rooms/{a['room'].id}/maintenance")
    assert db.session.get(Room, a["room"].id).status == "ok"


def test_client_cabinet_review_flow(client, db, two_branches):
    a = two_branches["a"]
    a["client"].email = "cab@example.com"
    a["client"].set_password("Cabinet-pass-1")
    db.session.commit()
    b = booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, "cab@example.com", "Cabinet-pass-1")
    assert client.get("/my-bookings").status_code == 200
    # отзыв до проведения игры — нельзя
    assert Review.query.count() == 0
    client.post(f"/my-bookings/{b.id}/review", data={"rating": "5", "text": "супер"})
    assert Review.query.count() == 0
    b.status = BOOKING_COMPLETED
    db.session.commit()
    assert client.post(f"/my-bookings/{b.id}/review", data={"rating": "5", "text": "<b>супер</b>"}).status_code == 302
    assert Review.query.count() == 1
    client.post(f"/my-bookings/{b.id}/review", data={"rating": "1", "text": "дубль"})
    assert Review.query.count() == 1                                        # повторный отзыв не создаётся
    page = client.get(f"/quest/{a['quest'].id}").get_data(as_text=True)
    assert "<b>супер</b>" not in page and "&lt;b&gt;" in page               # HTML в отзыве экранируется


def test_review_rating_out_of_range_rejected(client, db, two_branches):
    a = two_branches["a"]
    a["client"].email = "cab2@example.com"
    a["client"].set_password("Cabinet-pass-1")
    b = booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    b.status = BOOKING_COMPLETED
    db.session.commit()
    login(client, "cab2@example.com", "Cabinet-pass-1")
    client.post(f"/my-bookings/{b.id}/review", data={"rating": "99", "text": "x"})
    assert Review.query.count() == 0


def test_client_cancel_own_booking_via_cabinet(client, db, two_branches):
    a = two_branches["a"]
    a["client"].email = "cab3@example.com"
    a["client"].set_password("Cabinet-pass-1")
    b = booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, "cab3@example.com", "Cabinet-pass-1")
    assert client.post(f"/my-bookings/{b.id}/cancel").status_code == 302
    assert db.session.get(Booking, b.id).status == "canceled"


def test_staff_booking_creation_and_client_edit(client, db, two_branches):
    a = two_branches["a"]
    login(client, a["admin"].email, a["admin_pw"])
    slot = a["slots"][1]
    r = client.post("/schedule/booking/new", data={"slot_id": slot.id, "client_name": "Пётр", "client_phone": "+79007770001",
                                                   "players_count": "3", "comment": "день рождения"})
    assert r.status_code == 302
    booking = Booking.query.filter_by(slot_id=slot.id).first()
    assert booking.source == "admin" and booking.created_by_id == a["admin"].id and booking.comment == "день рождения"
    guest = booking.client
    r = client.post(f"/crm/clients/{guest.id}/edit", data={"full_name": "Пётр П.", "phone": "+79007770001",
                                                           "loyalty_points": "10", "loyalty_status": "VIP"})
    assert r.status_code == 302 and db.session.get(User, guest.id).loyalty_status == "VIP"
    r = client.post(f"/crm/clients/{guest.id}/edit", data={"full_name": "X", "phone": a["client"].phone,
                                                           "loyalty_points": "0", "loyalty_status": "VIP"})
    assert r.status_code == 200                                              # телефон занят другим
    assert client.post(f"/crm/clients/{guest.id}/toggle-active").status_code == 302
    assert not db.session.get(User, guest.id).is_active
