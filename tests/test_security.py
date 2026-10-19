"""Регрессионные тесты на находки security-review (см. SECURITY_REVIEW.txt):
изоляция между филиалами (multi-tenant) и open redirect при логине.
"""
from datetime import date, time, timedelta

from app.models import Branch, Location, Room, Quest, Tariff, User
from app.constants import ROLE_LOCATION_ADMIN, ROLE_CLIENT
from app.services import schedule_service, booking_service


def _login(client, email, password):
    return client.post(
        "/auth/login", data={"email": email, "password": password, "remember": ""},
        follow_redirects=True,
    )


def _make_branch(db, suffix, admin_password="adminpass1"):
    branch = Branch(name=f"Филиал {suffix}")
    db.session.add(branch)
    db.session.flush()

    location = Location(branch_id=branch.id, name=f"Локация {suffix}", address="ул. Тестовая")
    db.session.add(location)
    db.session.flush()

    room = Room(location_id=location.id, name=f"Комната {suffix}")
    db.session.add(room)
    db.session.flush()

    quest = Quest(room_id=room.id, title=f"Квест {suffix}", duration_minutes=60, min_players=2, max_players=6)
    db.session.add(quest)
    db.session.flush()

    tariff = Tariff(quest_id=quest.id, name="Базовый", weekday_mask="0,1,2,3,4,5,6",
                     time_from="00:00", time_to="23:59", price_per_slot=1000, price_per_extra_player=100)
    db.session.add(tariff)

    admin = User(role=ROLE_LOCATION_ADMIN, full_name=f"Админ {suffix}",
                 email=f"admin{suffix.lower()}@example.com", branch_id=branch.id)
    admin.set_password(admin_password)
    db.session.add(admin)

    client_user = User(role=ROLE_CLIENT, full_name=f"Клиент {suffix}", phone=f"+7900000{suffix}00")
    db.session.add(client_user)
    db.session.commit()

    slots = schedule_service.generate_slots_for_room(
        room, quest, date.today() + timedelta(days=1), date.today() + timedelta(days=1),
        time(10, 0), time(14, 0),
    )

    return {
        "branch": branch, "location": location, "room": room, "quest": quest,
        "admin": admin, "client_user": client_user, "slots": slots,
    }


def test_staff_cannot_cancel_booking_of_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    booking = booking_service.create_booking(
        client=b["client_user"], slot_id=b["slots"][0].id, players_count=2,
        source="admin", created_by=b["admin"],
    )

    _login(client, "admina@example.com", "adminpass1")
    resp = client.post(f"/schedule/booking/{booking.id}/cancel", data={}, follow_redirects=False)
    assert resp.status_code == 404


def test_staff_cannot_complete_booking_of_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    booking = booking_service.create_booking(
        client=b["client_user"], slot_id=b["slots"][0].id, players_count=2,
        source="admin", created_by=b["admin"],
    )

    _login(client, "admina@example.com", "adminpass1")
    resp = client.post(f"/schedule/booking/{booking.id}/complete", data={}, follow_redirects=False)
    assert resp.status_code == 404


def test_booking_new_slot_choices_scoped_to_own_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    _login(client, "admina@example.com", "adminpass1")
    resp = client.get("/schedule/booking/new")
    assert resp.status_code == 200
    assert a["quest"].title.encode("utf-8") in resp.data
    assert b["quest"].title.encode("utf-8") not in resp.data


def test_admin_cannot_toggle_maintenance_for_room_in_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    _login(client, "admina@example.com", "adminpass1")
    resp = client.post(f"/admin/rooms/{b['room'].id}/maintenance", data={}, follow_redirects=False)
    assert resp.status_code == 404


def test_admin_cannot_view_client_card_of_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    booking_service.create_booking(
        client=b["client_user"], slot_id=b["slots"][0].id, players_count=2,
        source="admin", created_by=b["admin"],
    )

    _login(client, "admina@example.com", "adminpass1")
    resp = client.get(f"/crm/clients/{b['client_user'].id}")
    assert resp.status_code == 403


def test_client_list_excludes_clients_of_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    booking_service.create_booking(
        client=a["client_user"], slot_id=a["slots"][0].id, players_count=2,
        source="admin", created_by=a["admin"],
    )
    booking_service.create_booking(
        client=b["client_user"], slot_id=b["slots"][0].id, players_count=2,
        source="admin", created_by=b["admin"],
    )

    _login(client, "admina@example.com", "adminpass1")
    resp = client.get("/crm/clients")
    assert a["client_user"].full_name.encode("utf-8") in resp.data
    assert b["client_user"].full_name.encode("utf-8") not in resp.data


def test_login_next_param_blocks_open_redirect(client, demo_data):
    resp = client.post(
        "/auth/login?next=https://evil.example/phish",
        data={"email": "admin@example.com", "password": "test1234", "remember": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "evil.example" not in resp.headers["Location"]


def test_login_next_param_allows_local_path(client, demo_data):
    resp = client.post(
        "/auth/login?next=/admin/tariffs",
        data={"email": "admin@example.com", "password": "test1234", "remember": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/admin/tariffs"


def test_weak_password_rejected_on_registration(client, demo_data):
    resp = client.post(
        "/auth/register",
        data={"full_name": "Слабый Пароль", "phone": "+79991112233", "password": "123"},
        follow_redirects=True,
    )
    from app.models import User
    assert User.query.filter_by(phone="+79991112233").first() is None


def test_audit_log_entry_persists_after_request(app, db, client, demo_data):
    """Регрессия: log_action() вызывался ПОСЛЕ db.session.commit(), поэтому запись
    никогда не сохранялась и терялась при закрытии сессии в конце запроса."""
    from app.models.audit import AuditLog

    _login(client, "admin@example.com", "test1234")

    entries = AuditLog.query.filter_by(action="login").all()
    assert len(entries) == 1
    assert entries[0].user_id == demo_data["superadmin"].id


def test_audit_log_scoped_to_own_branch(app, db, client):
    """Регрессия: /admin/audit-log показывал действия сотрудников всех
    филиалов администратору локации, а не только его собственного филиала."""
    from app.models.audit import AuditLog

    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    # user_id — кто совершил действие (это и есть поле, по которому скоупится журнал)
    db.session.add(AuditLog(user_id=a["admin"].id, action="staff_action", entity_type="Room", entity_id=101))
    db.session.add(AuditLog(user_id=b["admin"].id, action="staff_action", entity_type="Room", entity_id=202))
    db.session.commit()

    _login(client, "admina@example.com", "adminpass1")
    resp = client.get("/admin/audit-log")
    assert resp.status_code == 200
    assert b"Room#101" in resp.data
    assert b"Room#202" not in resp.data
