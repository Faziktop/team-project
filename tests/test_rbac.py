def _login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password, "remember": ""},
                        follow_redirects=True)


def test_anonymous_redirected_from_admin(client, demo_data):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_staff_login_and_dashboard_access(client, demo_data):
    resp = _login(client, "admin@example.com", "test1234")
    assert resp.status_code == 200
    resp = client.get("/admin/")
    assert resp.status_code == 200


def test_wrong_password_rejected(client, demo_data):
    resp = _login(client, "admin@example.com", "wrongpass")
    assert b"\xd0\x9d\xd0\xb5\xd0\xb2\xd0\xb5\xd1\x80\xd0\xbd" in resp.data  # "Неверн..." (email/password)


def test_client_cannot_access_admin(client, demo_data, db):
    from app.models import User
    from app.constants import ROLE_CLIENT
    c = User(role=ROLE_CLIENT, full_name="Просто клиент", email="plain-client@example.com", phone="+79990000009")
    c.set_password("clientpass")
    db.session.add(c)
    db.session.commit()

    _login(client, "plain-client@example.com", "clientpass")
    resp = client.get("/admin/")
    assert resp.status_code == 403
