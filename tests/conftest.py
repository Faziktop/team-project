import pytest
from datetime import date, time, timedelta

from app import create_app
from app.extensions import db as _db
from app.models import Branch, Location, Room, Quest, Tariff, User
from app.constants import ROLE_SUPERADMIN, ROLE_CLIENT
from app.services import schedule_service


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def demo_data(app, db):
    """Создаёт минимальный набор справочных данных для тестов."""
    branch = Branch(name="Тестовый филиал")
    db.session.add(branch)
    db.session.flush()

    location = Location(branch_id=branch.id, name="Тестовая локация", address="ул. Тестовая, 1")
    db.session.add(location)
    db.session.flush()

    room = Room(location_id=location.id, name="Комната 1")
    db.session.add(room)
    db.session.flush()

    quest = Quest(room_id=room.id, title="Тестовый квест", duration_minutes=60, min_players=2, max_players=6)
    db.session.add(quest)
    db.session.flush()

    tariff = Tariff(quest_id=quest.id, name="Базовый", weekday_mask="0,1,2,3,4,5,6",
                     time_from="00:00", time_to="23:59", price_per_slot=1000, price_per_extra_player=100)
    db.session.add(tariff)

    superadmin = User(role=ROLE_SUPERADMIN, full_name="Admin", email="admin@example.com", branch_id=branch.id)
    superadmin.set_password("test1234")
    db.session.add(superadmin)

    client_user = User(role=ROLE_CLIENT, full_name="Клиент Тестов", phone="+70000000001")
    db.session.add(client_user)

    db.session.commit()

    slots = schedule_service.generate_slots_for_room(
        room, quest, date.today() + timedelta(days=1), date.today() + timedelta(days=1),
        time(10, 0), time(18, 0),
    )

    return {
        "branch": branch, "location": location, "room": room, "quest": quest,
        "tariff": tariff, "superadmin": superadmin, "client_user": client_user, "slots": slots,
    }


# ---------------------------------------------------------------- общие хелперы
def login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=False)


@pytest.fixture()
def two_branches(app, db):
    """Два филиала: у каждого админ, менеджер, клиент, комната/квест/тариф и слоты на завтра."""
    from app.models import Branch, Location, Room, Quest, Tariff, User
    from app.constants import ROLE_LOCATION_ADMIN, ROLE_MANAGER, ROLE_CLIENT

    out = {}
    for key, n in (("a", 1), ("b", 2)):
        branch = Branch(name=f"Филиал {key.upper()}")
        db.session.add(branch)
        db.session.flush()
        loc = Location(branch_id=branch.id, name=f"Локация {key}", address="ул. Тестовая")
        db.session.add(loc)
        db.session.flush()
        room = Room(location_id=loc.id, name=f"Комната {key}")
        db.session.add(room)
        db.session.flush()
        quest = Quest(room_id=room.id, title=f"Квест {key}", duration_minutes=60, min_players=2, max_players=6)
        db.session.add(quest)
        db.session.flush()
        db.session.add(Tariff(quest_id=quest.id, name="Базовый", weekday_mask="0,1,2,3,4,5,6",
                              time_from="00:00", time_to="23:59", price_per_slot=1000, price_per_extra_player=100))
        admin = User(role=ROLE_LOCATION_ADMIN, full_name=f"Админ {key}", email=f"admin_{key}@example.com", branch_id=branch.id)
        admin.set_password("Adm1nPass" + key)
        manager = User(role=ROLE_MANAGER, full_name=f"Менеджер {key}", email=f"manager_{key}@example.com", branch_id=branch.id)
        manager.set_password("Mgr1Pass" + key)
        cl = User(role=ROLE_CLIENT, full_name=f"Клиент {key}", phone=f"+7900000000{n}")
        db.session.add_all([admin, manager, cl])
        db.session.commit()
        slots = schedule_service.generate_slots_for_room(
            room, quest, date.today() + timedelta(days=1), date.today() + timedelta(days=1), time(10, 0), time(14, 0))
        out[key] = dict(branch=branch, location=loc, room=room, quest=quest, admin=admin, manager=manager,
                        client=cl, slots=slots, admin_pw="Adm1nPass" + key, manager_pw="Mgr1Pass" + key)
    return out
