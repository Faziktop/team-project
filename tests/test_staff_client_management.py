"""Тесты управления сотрудниками и клиентами (админ/суперадмин)."""
from app.models import User
from app.constants import ROLE_MANAGER
from app.extensions import db

from tests.test_security import _make_branch, _login


def test_admin_can_edit_staff_of_own_branch(app, db, client):
    a = _make_branch(db, "A")
    host = User(role="host", full_name="Ведущий A", email="hosta@example.com", branch_id=a["branch"].id)
    host.set_password("hostpass1")
    db.session.add(host)
    db.session.commit()

    _login(client, "admina@example.com", "adminpass1")
    resp = client.post(
        f"/admin/users/{host.id}/edit",
        data={
            "full_name": "Ведущий A (обновлён)", "email": "hosta@example.com",
            "phone": "", "password": "", "role": "host", "branch_id": str(a["branch"].id),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert db.session.get(User, host.id).full_name == "Ведущий A (обновлён)"


def test_admin_cannot_edit_staff_of_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")

    _login(client, "admina@example.com", "adminpass1")
    resp = client.get(f"/admin/users/{b['admin'].id}/edit")
    assert resp.status_code == 404


def test_admin_cannot_block_own_account(app, db, client):
    a = _make_branch(db, "A")
    _login(client, "admina@example.com", "adminpass1")
    resp = client.post(f"/admin/users/{a['admin'].id}/toggle-active", follow_redirects=True)
    assert resp.status_code == 200
    assert db.session.get(User, a["admin"].id).is_active is True


def test_blocked_staff_is_logged_out_on_next_request(app, db, client):
    a = _make_branch(db, "A")
    host = User(role="host", full_name="Ведущий A", email="hosta@example.com", branch_id=a["branch"].id)
    host.set_password("hostpass1")
    db.session.add(host)
    db.session.commit()

    _login(client, "hosta@example.com", "hostpass1")
    resp = client.get("/schedule/")
    assert resp.status_code == 200  # сессия активна

    # Блокировка происходит "извне" (администратором) — эмулируем прямым изменением БД
    db.session.get(User, host.id).is_active_flag = False
    db.session.commit()

    resp = client.get("/schedule/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_admin_can_edit_client_loyalty_and_notes(app, db, client, demo_data):
    _login(client, "admin@example.com", "test1234")
    c = demo_data["client_user"]
    resp = client.post(
        f"/crm/clients/{c.id}/edit",
        data={
            "full_name": c.full_name, "phone": c.phone, "email": "",
            "loyalty_points": "250", "loyalty_status": "VIP", "notes": "Постоянный клиент, скидка 10%",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = db.session.get(User, c.id)
    assert updated.loyalty_points == 250
    assert updated.loyalty_status == "VIP"
    assert updated.notes == "Постоянный клиент, скидка 10%"


def test_manager_cannot_edit_client(app, db, client):
    a = _make_branch(db, "A")
    manager = User(role=ROLE_MANAGER, full_name="Менеджер A", email="managera@example.com", branch_id=a["branch"].id)
    manager.set_password("managerpass1")
    db.session.add(manager)
    db.session.commit()

    _login(client, "managera@example.com", "managerpass1")
    resp = client.get(f"/crm/clients/{a['client_user'].id}/edit")
    assert resp.status_code == 403


def test_admin_cannot_edit_client_of_another_branch(app, db, client):
    a = _make_branch(db, "A")
    b = _make_branch(db, "B")
    from app.services import booking_service

    booking_service.create_booking(
        client=b["client_user"], slot_id=b["slots"][0].id, players_count=2,
        source="admin", created_by=b["admin"],
    )

    _login(client, "admina@example.com", "adminpass1")
    resp = client.get(f"/crm/clients/{b['client_user'].id}/edit")
    assert resp.status_code == 403
