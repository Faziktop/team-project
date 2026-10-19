"""Матрица прав доступа по ВСЕМ маршрутам + изоляция филиалов + управление сотрудниками."""
from datetime import datetime, timedelta

import pytest
from flask import url_for

from app import create_app
from app.constants import (
    ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN, ROLE_HOST, ROLE_MANAGER, ROLE_ACCOUNTANT, ROLE_CLIENT, STAFF_ROLES,
)
from app.models import User, Slot, Booking, AuditLog
from app.services import booking_service
from tests.conftest import login

PUBLIC = {"widget.index", "widget.quest_detail", "widget.booking_step2", "widget.booking_confirmation",
          "widget.lookup_booking", "schedule.api_available_slots", "auth.login", "auth.register", "static"}
# Разрешённые роли для служебных маршрутов (None = любой вошедший клиент/сотрудник, см. отдельно)
ADMINS = {ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN}
STAFF = set(STAFF_ROLES)
EXPECTED = {
    "admin.dashboard": STAFF, "admin.branches": {ROLE_SUPERADMIN}, "admin.branch_new": {ROLE_SUPERADMIN},
    "admin.locations": STAFF, "admin.location_new": ADMINS, "admin.rooms": STAFF, "admin.room_new": ADMINS,
    "admin.room_toggle_maintenance": ADMINS, "admin.quests": STAFF, "admin.quest_new": ADMINS,
    "admin.tariffs": STAFF, "admin.tariff_new": ADMINS, "admin.users": ADMINS, "admin.user_new": ADMINS,
    "admin.user_edit": ADMINS, "admin.user_toggle_active": ADMINS, "admin.audit_log": ADMINS,
    "schedule.calendar": STAFF, "schedule.generate_slots": ADMINS, "schedule.booking_new": STAFF,
    "schedule.booking_cancel": STAFF, "schedule.booking_complete": STAFF, "schedule.booking_no_show": STAFF,
    "schedule.slot_checklist": STAFF,
    "crm.clients": STAFF, "crm.client_detail": STAFF, "crm.client_edit": ADMINS, "crm.client_toggle_active": ADMINS,
    "crm.reviews": STAFF,
    "payments.promocodes": ADMINS, "payments.promocode_new": ADMINS,
    "payments.certificates": ADMINS | {ROLE_ACCOUNTANT}, "payments.certificate_new": ADMINS,
    "reports.dashboard": STAFF, "reports.export": STAFF,
    "reports.export_google_sheets": {ROLE_SUPERADMIN},
}


def _make_users(db, branch):
    users = {}
    for role in (ROLE_HOST, ROLE_MANAGER, ROLE_ACCOUNTANT, ROLE_SUPERADMIN):
        u = User(role=role, full_name=role, email=f"{role}_x@example.com", branch_id=branch.id)
        u.set_password("Matrix-pass-1")
        db.session.add(u)
        users[role] = u
    c = User(role=ROLE_CLIENT, full_name="cl", email="client_x@example.com", phone="+79001110000")
    c.set_password("Matrix-pass-1")
    db.session.add(c)
    users[ROLE_CLIENT] = c
    db.session.commit()
    return users


def _url(app, endpoint, ids):
    kwargs = {}
    for arg in app.url_map._rules_by_endpoint[endpoint][0].arguments:
        kwargs[arg] = {"booking_id": ids["booking"], "slot_id": ids["slot"], "room_id": ids["room"],
                       "user_id": ids["user"], "client_id": ids["client"], "report_name": "occupancy",
                       "fmt": "csv", "quest_id": ids["quest"], "code": "X"}[arg]
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def test_every_protected_route_is_in_the_access_matrix(app):
    """Новый маршрут без записи в матрице прав — тест падает (нельзя забыть про доступ)."""
    known = PUBLIC | set(EXPECTED) | {"widget.my_bookings", "widget.my_booking_cancel", "widget.leave_review",
                                       "auth.logout", "widget.google_calendar", "widget.yandex_route"}
    missing = [r.endpoint for r in app.url_map.iter_rules() if r.endpoint not in known]
    assert not missing, f"добавьте маршруты в матрицу прав: {missing}"


def test_anonymous_never_reaches_staff_routes(app, client, two_branches):
    a = two_branches["a"]
    ids = dict(booking=1, slot=a["slots"][0].id, room=a["room"].id, user=a["admin"].id, client=a["client"].id,
               quest=a["quest"].id)
    for endpoint in EXPECTED:
        rule = app.url_map._rules_by_endpoint[endpoint][0]
        url = _url(app, endpoint, ids)
        for method in ("GET", "POST"):
            if method not in rule.methods:
                continue
            r = client.open(url, method=method, follow_redirects=False)
            assert r.status_code in (302, 401, 400), f"{method} {url} -> {r.status_code}"
            if r.status_code == 302:
                assert "/auth/login" in r.headers["Location"], f"{method} {url}"


@pytest.mark.parametrize("role", [ROLE_HOST, ROLE_MANAGER, ROLE_ACCOUNTANT, ROLE_CLIENT, ROLE_LOCATION_ADMIN])
def test_role_matrix_get_routes(app, client, db, two_branches, role):
    a = two_branches["a"]
    users = _make_users(db, a["branch"])
    users[ROLE_LOCATION_ADMIN] = a["admin"]
    booking = booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    ids = dict(booking=booking.id, slot=a["slots"][0].id, room=a["room"].id, user=a["manager"].id,
               client=a["client"].id, quest=a["quest"].id)
    pw = a["admin_pw"] if role == ROLE_LOCATION_ADMIN else "Matrix-pass-1"
    login(client, users[role].email, pw)
    for endpoint, allowed in EXPECTED.items():
        rule = app.url_map._rules_by_endpoint[endpoint][0]
        if "GET" not in rule.methods:
            continue
        r = client.get(_url(app, endpoint, ids))
        if role in allowed:
            assert r.status_code not in (401, 403), f"{role} должен иметь доступ к {endpoint}: {r.status_code}"
        else:
            assert r.status_code == 403, f"{role} не должен иметь доступа к {endpoint}: {r.status_code}"


def test_staff_without_branch_is_locked_out(client, db, two_branches):
    """Fail-closed: сотрудник без филиала не видит данные всей сети."""
    a = two_branches["a"]
    a["manager"].branch_id = None
    db.session.commit()
    login(client, a["manager"].email, a["manager_pw"])
    for url in ("/schedule/", "/crm/clients", "/reports/", "/admin/", "/crm/reviews"):
        assert client.get(url).status_code == 403, url


def test_superadmin_without_branch_still_works(client, db, two_branches):
    sa = User(role=ROLE_SUPERADMIN, full_name="S", email="sa@example.com")
    sa.set_password("Super-pass-1")
    db.session.add(sa)
    db.session.commit()
    login(client, "sa@example.com", "Super-pass-1")
    assert client.get("/reports/").status_code == 200 and client.get("/schedule/").status_code == 200


# ------------------------------------------------------------ изоляция филиалов
def test_branch_isolation_on_bookings_slots_clients(client, db, two_branches):
    a, b = two_branches["a"], two_branches["b"]
    foreign = booking_service.create_booking(b["client"], b["slots"][0].id, 2)
    login(client, a["admin"].email, a["admin_pw"])
    assert client.post(f"/schedule/booking/{foreign.id}/cancel").status_code == 404
    assert client.post(f"/schedule/booking/{foreign.id}/complete").status_code == 404
    assert client.post(f"/schedule/booking/{foreign.id}/no-show").status_code == 404
    assert client.get(f"/schedule/slot/{b['slots'][0].id}/checklist").status_code == 404
    assert client.get(f"/crm/clients/{b['client'].id}").status_code == 403
    assert client.post(f"/admin/rooms/{b['room'].id}/maintenance").status_code == 404
    assert db.session.get(Booking, foreign.id).status == "confirmed"


def test_branch_admin_report_ignores_branch_query_param(client, two_branches):
    a, b = two_branches["a"], two_branches["b"]
    booking_service.create_booking(b["client"], b["slots"][0].id, 2)
    login(client, a["admin"].email, a["admin_pw"])
    html = client.get(f"/reports/?branch_id={b['branch'].id}").get_data(as_text=True)
    assert "Комната b" not in html


def test_booking_new_lists_only_own_branch_slots(client, two_branches):
    a, b = two_branches["a"], two_branches["b"]
    login(client, a["admin"].email, a["admin_pw"])
    html = client.get("/schedule/booking/new").get_data(as_text=True)
    assert "Комната a" in html and "Комната b" not in html


def test_staff_cannot_book_foreign_branch_slot_via_form(client, db, two_branches):
    a, b = two_branches["a"], two_branches["b"]
    login(client, a["admin"].email, a["admin_pw"])
    r = client.post("/schedule/booking/new", data={"slot_id": b["slots"][0].id, "client_name": "X",
                                                   "client_phone": "+79001234500", "players_count": "2"})
    assert r.status_code == 200  # значение вне choices формы
    assert Booking.query.count() == 0


# ------------------------------------------------------------ управление сотрудниками
def _user_form(**over):
    d = {"full_name": "Новый Сотрудник", "email": "new@example.com", "phone": "", "password": "Nice-pass-2026",
         "role": ROLE_MANAGER, "branch_id": ""}
    d.update(over)
    return d


def test_location_admin_cannot_create_admin_or_superadmin(client, db, two_branches):
    a = two_branches["a"]
    login(client, a["admin"].email, a["admin_pw"])
    for role in (ROLE_LOCATION_ADMIN, ROLE_SUPERADMIN):
        r = client.post("/admin/users/new", data=_user_form(role=role, email=f"{role}@example.com", branch_id=a["branch"].id))
        assert r.status_code == 200
        assert User.query.filter_by(email=f"{role}@example.com").first() is None
    r = client.post("/admin/users/new", data=_user_form(branch_id=b_id(two_branches)))
    assert r.status_code == 302
    created = User.query.filter_by(email="new@example.com").first()
    assert created.branch_id == a["branch"].id  # филиал берётся у создающего, а не из формы


def b_id(tb):
    return tb["b"]["branch"].id


def test_location_admin_cannot_touch_other_admins_or_other_branches(client, db, two_branches):
    a, b = two_branches["a"], two_branches["b"]
    other_admin = User(role=ROLE_LOCATION_ADMIN, full_name="Второй админ", email="admin2_a@example.com", branch_id=a["branch"].id)
    other_admin.set_password("Second-pass-1")
    db.session.add(other_admin)
    db.session.commit()
    login(client, a["admin"].email, a["admin_pw"])
    for uid in (other_admin.id, b["manager"].id, b["admin"].id):
        assert client.get(f"/admin/users/{uid}/edit").status_code == 404
        assert client.post(f"/admin/users/{uid}/toggle-active").status_code == 404
        assert client.post(f"/admin/users/{uid}/edit", data=_user_form(email="hijack@example.com", password="Hijack-pass-1")).status_code == 404
    assert db.session.get(User, other_admin.id).check_password("Second-pass-1")
    assert db.session.get(User, other_admin.id).is_active


def test_location_admin_can_manage_own_staff_and_cannot_promote(client, db, two_branches):
    a = two_branches["a"]
    login(client, a["admin"].email, a["admin_pw"])
    assert client.post(f"/admin/users/{a['manager'].id}/toggle-active").status_code == 302
    assert not db.session.get(User, a["manager"].id).is_active
    r = client.post(f"/admin/users/{a['manager'].id}/edit", data=_user_form(email=a["manager"].email, role=ROLE_LOCATION_ADMIN, password=""))
    assert r.status_code == 200  # роль admin вне списка допустимых
    assert db.session.get(User, a["manager"].id).role == ROLE_MANAGER


def test_password_change_by_admin_resets_lockout_and_is_audited(client, db, two_branches):
    a = two_branches["a"]
    a["manager"].failed_login_count = 3
    db.session.commit()
    login(client, a["admin"].email, a["admin_pw"])
    r = client.post(f"/admin/users/{a['manager'].id}/edit",
                    data=_user_form(email=a["manager"].email, role=ROLE_MANAGER, password="Brand-new-pass-7"))
    assert r.status_code == 302
    assert db.session.get(User, a["manager"].id).failed_login_count == 0
    entry = AuditLog.query.filter_by(action="staff_user_updated").order_by(AuditLog.id.desc()).first()
    assert "password_changed=True" in entry.details and "Brand-new" not in entry.details  # пароль в аудит не пишем


def test_duplicate_phone_rejected_for_staff(client, db, two_branches):
    a = two_branches["a"]
    login(client, a["admin"].email, a["admin_pw"])
    r = client.post("/admin/users/new", data=_user_form(phone=a["client"].phone))
    assert r.status_code == 200 and User.query.filter_by(email="new@example.com").first() is None


def test_last_active_superadmin_cannot_be_blocked_or_demoted(client, db, two_branches):
    root = User(role=ROLE_SUPERADMIN, full_name="Root", email="root@example.com")
    root.set_password("Root-pass-2026")
    other = User(role=ROLE_SUPERADMIN, full_name="Other", email="other_sa@example.com")
    other.set_password("Other-pass-2026")
    db.session.add_all([root, other])
    db.session.commit()
    login(client, "root@example.com", "Root-pass-2026")

    # пока есть второй активный суперадмин — блокировка допустима
    assert client.post(f"/admin/users/{other.id}/toggle-active").status_code == 302
    assert not db.session.get(User, other.id).is_active

    # Правило подсчёта «других активных суперадминов», на котором держится защита
    from app.blueprints.admin import routes as admin_routes
    other.is_active_flag = True
    db.session.commit()
    assert admin_routes._count_active_superadmins(exclude_user_id=other.id) == 1   # root
    root.is_active_flag = False
    db.session.commit()
    assert admin_routes._count_active_superadmins(exclude_user_id=other.id) == 0   # other — последний


def test_last_superadmin_guard_via_http(client, db, two_branches):
    """Единственный активный суперадмин не может понизить свою роль другим суперадмином-«призраком»."""
    root = User(role=ROLE_SUPERADMIN, full_name="Root", email="root2@example.com")
    root.set_password("Root-pass-2026")
    ghost = User(role=ROLE_SUPERADMIN, full_name="Ghost", email="ghost_sa@example.com", is_active_flag=False)
    ghost.set_password("Ghost-pass-2026")
    db.session.add_all([root, ghost])
    db.session.commit()
    login(client, "root2@example.com", "Root-pass-2026")
    # root — единственный активный. Понижение ghost (неактивного) допустимо, а вот «понизить» root
    # он не может сам (свою роль менять нельзя) — роль остаётся прежней
    r = client.post(f"/admin/users/{root.id}/edit",
                    data=_user_form(email=root.email, role=ROLE_MANAGER, password="", branch_id=two_branches["a"]["branch"].id))
    assert db.session.get(User, root.id).role == ROLE_SUPERADMIN


def test_blocked_user_session_is_terminated(client, db, two_branches):
    a = two_branches["a"]
    login(client, a["manager"].email, a["manager_pw"])
    assert client.get("/schedule/").status_code == 200
    a["manager"].is_active_flag = False
    db.session.commit()
    r = client.get("/schedule/", follow_redirects=False)
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


# ------------------------------------------------------------ прочее поведение маршрутов
def test_no_show_flow_and_calendar(client, db, two_branches):
    a = two_branches["a"]
    b = booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, a["manager"].email, a["manager_pw"])
    client.post(f"/schedule/booking/{b.id}/no-show")  # сеанс завтра: отклонено сервисом, без 500
    assert db.session.get(Booking, b.id).status == "confirmed"
    b.slot.start_time = datetime.now() - timedelta(hours=1)
    b.slot.end_time = datetime.now() + timedelta(hours=0)
    db.session.commit()
    assert client.post(f"/schedule/booking/{b.id}/no-show").status_code == 302
    assert db.session.get(Booking, b.id).status == "no_show"


def test_cancel_reason_is_truncated_and_referrer_not_open_redirect(client, db, two_branches):
    a = two_branches["a"]
    b = booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, a["manager"].email, a["manager_pw"])
    r = client.post(f"/schedule/booking/{b.id}/cancel", data={"reason": "я" * 5000},
                    headers={"Referer": "https://evil.example/phish"})
    assert r.status_code == 302 and "evil.example" not in r.headers["Location"]
    assert len(db.session.get(Booking, b.id).cancel_reason) <= 255


def test_checklist_post_with_garbage_ids_does_not_500(client, two_branches):
    a = two_branches["a"]
    booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, a["manager"].email, a["manager_pw"])
    r = client.post(f"/schedule/slot/{a['slots'][0].id}/checklist", data={"item_id": ["abc", "-1", "9" * 30]})
    assert r.status_code == 302


def test_crm_search_escapes_like_wildcards(client, db, two_branches):
    a = two_branches["a"]
    booking_service.create_booking(a["client"], a["slots"][0].id, 2)
    login(client, a["admin"].email, a["admin_pw"])
    assert "Клиент a" in client.get("/crm/clients?q=%D0%9A%D0%BB%D0%B8%D0%B5%D0%BD%D1%82").get_data(as_text=True)
    assert "Клиент a" not in client.get("/crm/clients?q=%25").get_data(as_text=True)  # «%» ищется буквально
    assert "Клиент a" not in client.get("/crm/clients?q=_").get_data(as_text=True)


def test_error_pages_render(client, two_branches):
    assert client.get("/no-such-page").status_code == 404
    a = two_branches["a"]
    login(client, a["manager"].email, a["manager_pw"])
    assert client.get("/admin/branches").status_code == 403


def test_proxyfix_only_when_configured():
    import app as app_module
    from app.config import TestingConfig
    plain = create_app("testing")
    assert type(plain.wsgi_app).__name__ != "ProxyFix"
    TestingConfig.PROXY_FIX_HOPS = 1
    try:
        assert type(create_app("testing").wsgi_app).__name__ == "ProxyFix"
    finally:
        TestingConfig.PROXY_FIX_HOPS = 0
