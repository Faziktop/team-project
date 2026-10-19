"""Скрипт наполнения БД демонстрационными данными.

Использование:
    flask seed-demo
или напрямую:
    python seed.py

Создаёт: 2 филиала, 3 локации, 6 комнат/квестов с тарифами и чек-листами,
персонал всех ролей, ~25 клиентов, промокоды/сертификаты разной валидности,
сеансы за последние 14 дней и на 10 дней вперёд, а также реалистичную историю
бронирований (подтверждённые/проведённые/отменённые) с отзывами — так что
отчёты, CRM, журнал уведомлений и журнал аудита не пустуют сразу после сидирования.
"""
import random
from datetime import date, datetime, timedelta, time, timezone

from app import create_app
from app.extensions import db
from app.models import (
    Branch, Location, Room, Quest, Tariff, User, PromoCode, Certificate,
    ChecklistTemplate, ChecklistItem, Review,
)
from app.constants import (
    ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN, ROLE_HOST, ROLE_MANAGER, ROLE_ACCOUNTANT,
)
from app.services import schedule_service, booking_service
from app.services.exceptions import DomainError

random.seed(42)

CLIENT_NAMES = [
    "Иванов Алексей", "Петрова Мария", "Сидоров Дмитрий", "Кузнецова Анна",
    "Смирнов Игорь", "Попова Екатерина", "Васильев Николай", "Соколова Ольга",
    "Михайлов Сергей", "Новикова Татьяна", "Фёдоров Андрей", "Морозова Юлия",
    "Волков Максим", "Алексеева Наталья", "Лебедев Артём", "Семёнова Виктория",
    "Егоров Владимир", "Павлова Дарья", "Козлов Роман", "Степанова Елена",
    "Николаев Кирилл", "Орлова Ксения", "Андреев Денис", "Макарова Полина",
    "Никитин Илья",
]


CANCEL_REASONS = [
    "Заболел ребёнок", "Не смогли приехать вовремя", "Перенесли на другую дату",
    "Изменились планы", "Дублирующая запись по телефону",
]

REVIEW_TEXTS = {
    5: [
        "Потрясающий квест, атмосфера на высоте! Обязательно вернёмся ещё.",
        "Лучший квест из всех, что проходили. Ведущий — огонь!",
        "Сюжет держит в напряжении до последней минуты. Всем советую.",
    ],
    4: [
        "Очень понравилось, но пара загадок была слишком простой.",
        "Хорошая локация, интересные механики. Чуть подкачал звук.",
        "Достойный квест, играли большой компанией — всем зашло.",
    ],
    3: [
        "В целом неплохо, но ожидали большего за эту цену.",
        "Есть над чем поработать: пара реквизитов сломана.",
    ],
    2: [
        "Не оправдал ожиданий, часть комнаты явно требует ремонта.",
    ],
}

SOURCES_WEIGHTED = ["widget", "widget", "widget", "admin", "phone"]


def _make_client(i: int, name: str) -> User:
    has_email = i % 3 != 0
    points = random.randint(0, 850)
    if points >= 600:
        status = "VIP"
    elif points >= 300:
        status = "Постоянный гость"
    elif points >= 100:
        status = "Друг квестов"
    else:
        status = "Новичок"
    user = User(
        role="client",
        full_name=name,
        phone=f"+7900{1000000 + i:07d}",
        email=f"client{i}@example.com" if has_email else None,
        loyalty_points=points,
        loyalty_status=status,
    )
    user.set_password("client123")
    return user


def _make_quest_with_tariffs(room: Room, title: str, description: str, difficulty: str,
                              duration: int, min_p: int, max_p: int, min_age: int,
                              weekday_price: int, weekend_price: int, is_horror: bool = False) -> Quest:
    quest = Quest(
        room_id=room.id, title=title, description=description, difficulty=difficulty,
        duration_minutes=duration, min_players=min_p, max_players=max_p, min_age=min_age,
        is_horror=is_horror,
    )
    db.session.add(quest)
    db.session.flush()

    db.session.add_all([
        Tariff(quest_id=quest.id, name="Будни", weekday_mask="0,1,2,3,4", time_from="10:00", time_to="17:00",
               price_per_slot=weekday_price, price_per_extra_player=round(weekday_price * 0.1), priority=1),
        Tariff(quest_id=quest.id, name="Вечер/выходные", weekday_mask="0,1,2,3,4,5,6",
               time_from="00:00", time_to="23:59",
               price_per_slot=weekend_price, price_per_extra_player=round(weekend_price * 0.1), priority=0),
    ])

    checklist = ChecklistTemplate(quest_id=quest.id, name="Подготовка к сеансу")
    db.session.add(checklist)
    db.session.flush()
    for i, text in enumerate([
        "Проверить реквизит и декорации", "Проверить работу замков/датчиков",
        "Убрать следы предыдущей игры", "Проверить освещение и звук",
    ]):
        db.session.add(ChecklistItem(template_id=checklist.id, text=text, order=i))

    return quest


def run_seed():
    db.create_all()

    if Branch.query.first():
        print("База уже содержит данные — пропускаем наполнение.")
        return

    # ------------------------------------------------------------ филиалы
    branch_msk = Branch(name="QuestEvent Москва", city="Москва", address="ул. Тверская, 1",
                         phone="+7 495 000-00-00")
    branch_spb = Branch(name="QuestEvent Санкт-Петербург", city="Санкт-Петербург",
                         address="Невский пр-т, 28", phone="+7 812 000-00-00")
    db.session.add_all([branch_msk, branch_spb])
    db.session.flush()

    loc_tverskaya = Location(branch_id=branch_msk.id, name="Локация на Тверской", address="ул. Тверская, 1")
    loc_arbat = Location(branch_id=branch_msk.id, name="Локация на Арбате", address="ул. Арбат, 20")
    loc_nevsky = Location(branch_id=branch_spb.id, name="Локация на Невском", address="Невский пр-т, 28")
    db.session.add_all([loc_tverskaya, loc_arbat, loc_nevsky])
    db.session.flush()

    room1 = Room(location_id=loc_tverskaya.id, name="Комната «Тайна пирамиды»")
    room2 = Room(location_id=loc_tverskaya.id, name="Комната «Заброшенный госпиталь»")
    room3 = Room(location_id=loc_arbat.id, name="Комната «Космическая станция»")
    room4 = Room(location_id=loc_arbat.id, name="Кабинет частного детектива")
    room5 = Room(location_id=loc_nevsky.id, name="Особняк с привидениями")
    room6 = Room(location_id=loc_nevsky.id, name="Тюремный блок")
    db.session.add_all([room1, room2, room3, room4, room5, room6])
    db.session.flush()

    quest1 = _make_quest_with_tariffs(
        room1, "Тайна пирамиды",
        "Экспедиция вашей группы обнаружила нетронутый вход в гробницу фараона, "
        "запечатанную три тысячи лет назад. Древние жрецы оставили здесь не только "
        "сокровища, но и хитроумные ловушки для тех, кто потревожит покой правителя.\n\n"
        "Вам предстоит расшифровать иероглифы, разгадать механизмы каменных дверей "
        "и найти путь к погребальной камере раньше, чем сомкнутся стены коридора. "
        "60 минут, чтобы забрать амулет фараона и выбраться на поверхность — если, "
        "конечно, древнее проклятие позволит вам уйти.",
        "средний", 60, 2, 6, 10, 3000, 4000,
    )
    quest2 = _make_quest_with_tariffs(
        room2, "Заброшенный госпиталь",
        "Психиатрическая лечебница была закрыта после серии необъяснимых происшествий "
        "и с тех пор простояла заброшенной больше двадцати лет. Местные утверждают, что "
        "по ночам в тёмных палатах до сих пор слышны шаги и скрип каталок.\n\n"
        "Вы — команда, решившая выяснить правду о последнем пациенте главного врача. "
        "Тёмные коридоры, гнетущая тишина и звуки, которым нет объяснения — этот квест "
        "не прощает нервных и мнительных. Рекомендуется крепкая компания и трезвый рассудок.",
        "сложный", 60, 3, 5, 18, 4000, 4500, is_horror=True,
    )
    quest3 = _make_quest_with_tariffs(
        room3, "SOS с орбиты",
        "Орбитальная станция «Гагарин-9» потеряла связь с Землёй после столкновения с "
        "неопознанным объектом. Системы жизнеобеспечения повреждены, кислорода "
        "остаётся на 75 минут, а часть экипажа заблокирована в отсеках за неисправными шлюзами.\n\n"
        "Вам предстоит восстановить энергоснабжение, перепрограммировать бортовой "
        "компьютер и найти способ отправить сигнал бедствия прежде, чем станция сойдёт "
        "с орбиты. Квест построен на технических головоломках и требует слаженной работы "
        "всей команды.",
        "средний", 75, 2, 5, 12, 3500, 4500,
    )
    quest4 = _make_quest_with_tariffs(
        room4, "Дело №13",
        "В кабинет частного детектива поступило дело, от которого отказалась полиция: "
        "пропажа важных документов из закрытого архива, и подозреваемых — не меньше "
        "полудюжины. Собранные детективом улики разложены по всему кабинету, но "
        "часть из них — намеренная ложь.\n\n"
        "Изучите картотеку, сопоставьте алиби и найдите настоящего похитителя, прежде "
        "чем дело закроют за отсутствием улик. Лёгкий и атмосферный квест в духе "
        "классического детектива — отличный вариант для первого опыта или семейной игры.",
        "легкий", 60, 2, 6, 8, 2500, 3200,
    )
    quest5 = _make_quest_with_tariffs(
        room5, "Проклятие особняка Вороных",
        "Старинный особняк рода Вороных пустует уже полвека — с тех пор, как вся семья "
        "исчезла в одну ночь при загадочных обстоятельствах. Слухи о фамильном проклятии "
        "отпугивали любопытных, пока ваша группа не решила узнать правду.\n\n"
        "Готический интерьер, фамильные портреты, которые будто следят за каждым шагом, "
        "и тайна, спрятанная в подвале дома — 90 минут в особняке Вороных подарят "
        "по-настоящему сильные впечатления. Самый атмосферный и пугающий квест сети, "
        "финал непредсказуем даже для тех, кто проходил его раньше.",
        "сложный", 90, 3, 6, 18, 4500, 5500, is_horror=True,
    )
    quest6 = _make_quest_with_tariffs(
        room6, "Побег из Крестов",
        "Вас несправедливо осудили и заперли в одном из самых суровых тюремных блоков "
        "страны. Охрана меняется через час — это единственное окно, чтобы раздобыть "
        "ключи, договориться с сокамерниками и выбраться на свободу до обхода.\n\n"
        "Классический квест-побег с настоящими решётками, тайниками в камерах и "
        "многоступенчатыми механическими замками. Держите себя в руках: одна ошибка — "
        "и придётся начинать план побега заново.",
        "средний", 60, 2, 4, 14, 3000, 3800,
    )

    rooms_quests = [
        (room1, quest1, branch_msk), (room2, quest2, branch_msk),
        (room3, quest3, branch_msk), (room4, quest4, branch_msk),
        (room5, quest5, branch_spb), (room6, quest6, branch_spb),
    ]

    # ------------------------------------------------------------- персонал
    superadmin = User(full_name="Суперадминистратор", email="superadmin@questevent.ru",
                       role=ROLE_SUPERADMIN, branch_id=None)
    superadmin.set_password("admin123")
    db.session.add(superadmin)

    staff_msk = []
    staff_spb = []
    for name, email, role, target in [
        ("Администратор Тверская", "admin@questevent.ru", ROLE_LOCATION_ADMIN, staff_msk),
        ("Ведущий Иван", "host@questevent.ru", ROLE_HOST, staff_msk),
        ("Ведущий Пётр", "host2@questevent.ru", ROLE_HOST, staff_msk),
        ("Менеджер Ольга", "manager@questevent.ru", ROLE_MANAGER, staff_msk),
        ("Бухгалтер Мария", "accountant@questevent.ru", ROLE_ACCOUNTANT, staff_msk),
        ("Администратор Невский", "admin_spb@questevent.ru", ROLE_LOCATION_ADMIN, staff_spb),
        ("Ведущая Анна", "host_spb@questevent.ru", ROLE_HOST, staff_spb),
        ("Менеджер Дмитрий", "manager_spb@questevent.ru", ROLE_MANAGER, staff_spb),
        ("Бухгалтер Светлана", "accountant_spb@questevent.ru", ROLE_ACCOUNTANT, staff_spb),
    ]:
        branch_id = branch_msk.id if target is staff_msk else branch_spb.id
        u = User(full_name=name, email=email, role=role, branch_id=branch_id)
        u.set_password("admin123")
        db.session.add(u)
        target.append(u)

    staff_by_branch = {branch_msk.id: staff_msk, branch_spb.id: staff_spb}

    # -------------------------------------------------------------- клиенты
    clients = [_make_client(i, name) for i, name in enumerate(CLIENT_NAMES)]
    db.session.add_all(clients)

    # ----------------------------------------------- промокоды/сертификаты
    promo_welcome = PromoCode(code="WELCOME10", discount_percent=10, usage_limit=0)
    promo_vip = PromoCode(code="VIP20", discount_percent=20, usage_limit=30)
    promo_friend = PromoCode(code="FRIEND5", discount_percent=5, usage_limit=0)
    promo_expired = PromoCode(code="SUMMER15", discount_percent=15, usage_limit=100,
                               valid_from=date.today() - timedelta(days=200),
                               valid_to=date.today() - timedelta(days=120))
    db.session.add_all([promo_welcome, promo_vip, promo_friend, promo_expired])

    cert_gift1000 = Certificate(code="GIFT1000", initial_balance=1000, balance=1000,
                                 expires_at=date.today() + timedelta(days=365))
    cert_gift2000 = Certificate(code="GIFT2000", initial_balance=2000, balance=2000,
                                 expires_at=date.today() + timedelta(days=180))
    cert_gift_partial = Certificate(code="GIFT500", initial_balance=500, balance=200,
                                     expires_at=date.today() + timedelta(days=90),
                                     issued_to_name="Иванов Алексей")
    cert_expired = Certificate(code="GIFTOLD", initial_balance=300, balance=300,
                                expires_at=date.today() - timedelta(days=10))
    db.session.add_all([cert_gift1000, cert_gift2000, cert_gift_partial, cert_expired])

    db.session.commit()

    active_promos = [promo_welcome, promo_vip, promo_friend]
    active_certs = [cert_gift1000, cert_gift2000, cert_gift_partial]

    # ------------------------------------------------------------- сеансы
    date_from = date.today() - timedelta(days=14)
    date_to = date.today() + timedelta(days=10)
    now = datetime.now()

    all_slots = []
    for room, quest, branch in rooms_quests:
        created = schedule_service.generate_slots_for_room(
            room, quest, date_from, date_to, time(10, 0), time(21, 0)
        )
        for slot in created:
            all_slots.append((slot, branch))

    # ---------------------------------------------------------- бронирования
    booked_count = completed_count = canceled_count = review_count = 0

    for slot, branch in all_slots:
        is_past = slot.start_time < now
        probability = 0.6 if is_past else 0.25
        if random.random() >= probability:
            continue

        quest = slot.quest
        client = random.choice(clients)
        players = random.randint(quest.min_players, quest.max_players)
        source = random.choice(SOURCES_WEIGHTED)
        created_by = None if source == "widget" else random.choice(staff_by_branch[branch.id])

        promo_code = None
        cert_code = None
        pick = random.random()
        if pick < 0.15:
            candidates = [p for p in active_promos if p.is_valid(slot.start_time.date())]
            if candidates:
                promo_code = random.choice(candidates).code
        elif pick < 0.22:
            candidates = [c for c in active_certs if c.is_valid(slot.start_time.date())]
            if candidates:
                cert_code = random.choice(candidates).code

        try:
            booking = booking_service.create_booking(
                client=client, slot_id=slot.id, players_count=players,
                promo_code=promo_code, certificate_code=cert_code,
                source=source, created_by=created_by, allow_past=is_past,
            )
        except DomainError:
            continue

        # Бронь обычно делается за некоторое время до сеанса, а не в момент сидирования —
        # без этого вся история "создания" схлопывается в один момент и график
        # динамики выручки по дням превращается в один пик.
        lead_time = timedelta(hours=random.randint(1, 240))
        raw_created_at = slot.start_time - lead_time
        if raw_created_at > now:
            # Бронь на дальний будущий сеанс, при этом "заказанная" совсем недавно —
            # разбрасываем такие по последним дням, а не складываем всё в один момент.
            raw_created_at = now - timedelta(hours=random.randint(0, 72))
        booking.created_at = raw_created_at.replace(tzinfo=timezone.utc)
        db.session.commit()

        booked_count += 1

        if is_past:
            if random.random() < 0.08:
                # Исторические отмены выполняет сотрудник (клиент не может отменить уже начавшуюся игру)
                booking_service.cancel_booking(
                    booking, reason=random.choice(CANCEL_REASONS),
                    initiated_by=created_by or random.choice(staff_by_branch[branch.id]),
                )
                canceled_count += 1
            else:
                booking_service.mark_completed(booking)
                completed_count += 1
                if random.random() < 0.65:
                    rating = random.choices([5, 4, 3, 2], weights=[50, 30, 15, 5])[0]
                    text = random.choice(REVIEW_TEXTS[rating])
                    db.session.add(Review(booking_id=booking.id, client_id=client.id,
                                           rating=rating, text=text))
                    db.session.commit()
                    review_count += 1

    print(
        f"Демо-данные успешно созданы: 2 филиала, 3 локации, 6 комнат/квестов, "
        f"{len(clients)} клиентов, {len(all_slots)} сеансов, {booked_count} бронирований "
        f"({completed_count} проведено, {canceled_count} отменено, {review_count} отзывов)."
    )


if __name__ == "__main__":
    app = create_app("development")
    with app.app_context():
        run_seed()
