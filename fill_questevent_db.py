"""Наполнение существующей БД QuestEvent тестовыми записями.

Скопируйте в корень проекта и запустите, например:
 python fill_questevent_db.py --clients 100 --slots 300 --bookings 200 --reviews 50
Все количества означают ДОБАВИТЬ указанное число строк, а не итоговое число.
"""
import argparse
import random
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import User, Quest, Slot, Booking, Review
from app.constants import ROLE_CLIENT, SLOT_AVAILABLE, SLOT_BOOKED, SLOT_COMPLETED, BOOKING_COMPLETED, BOOKING_CONFIRMED

NAMES = ["Алексей", "Мария", "Дмитрий", "Анна", "Игорь", "Екатерина", "Артём", "Ольга", "Максим", "Виктория"]
SURNAMES = ["Иванов", "Петров", "Смирнов", "Кузнецов", "Попов", "Соколов", "Морозов", "Волков"]
COMMENTS = ["Отличные загадки и атмосфера!", "Очень понравилось, придём ещё.", "Интересный сюжет и хороший ведущий.", "Хороший квест для компании."]


def make_clients(n):
    for _ in range(n):
        uid = uuid.uuid4().hex[:16]
        db.session.add(User(
            role=ROLE_CLIENT,
            full_name=f"{random.choice(SURNAMES)} {random.choice(NAMES)}",
            email=f"demo_{uid}@example.invalid",
            phone=None,
            loyalty_points=random.randint(0, 500),
            loyalty_status=random.choice(["Новичок", "Друг квестов", "Постоянный гость"]),
        ))
    db.session.flush()


def make_slots(n):
    quests = Quest.query.filter_by(is_active=True).all()
    if n and not quests:
        raise ValueError("Нет активных квестов. Сначала выполните python seed.py")
    # Для каждой комнаты новые слоты начинаются после последнего существующего.
    last_end = {}
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    for quest in quests:
        existing = db.session.query(db.func.max(Slot.end_time)).filter(Slot.room_id == quest.room_id).scalar()
        last_end[quest.room_id] = max(last_end.get(quest.room_id, now), existing or now, now)
    for i in range(n):
        quest = quests[i % len(quests)]
        start = last_end[quest.room_id] + timedelta(minutes=30)
        end = start + timedelta(minutes=max(quest.duration_minutes, 1))
        db.session.add(Slot(room_id=quest.room_id, quest_id=quest.id, start_time=start,
                            end_time=end, status=SLOT_AVAILABLE))
        last_end[quest.room_id] = end
    db.session.flush()


def make_bookings(n):
    clients = User.query.filter_by(role=ROLE_CLIENT).all()
    if n and not clients:
        raise ValueError("Нет клиентов. Укажите --clients или выполните python seed.py")
    # Слоты с неотменёнными бронированиями исключаем независимо от status.
    occupied = db.session.query(Booking.slot_id).filter(Booking.status != 'canceled')
    available = (Slot.query.filter(Slot.status == SLOT_AVAILABLE, ~Slot.id.in_(occupied))
                 .order_by(Slot.start_time, Slot.id).limit(n).all())
    if len(available) < n:
        raise ValueError(f"Свободных слотов {len(available)}, требуется {n}. Увеличьте --slots.")
    for slot in available:
        quest = slot.quest
        count = random.randint(quest.min_players, max(quest.min_players, quest.max_players))
        tariffs = [t for t in quest.tariffs if t.is_active and
                   (t.valid_from is None or t.valid_from <= slot.start_time.date()) and
                   (t.valid_to is None or t.valid_to >= slot.start_time.date()) and
                   slot.start_time.weekday() in t.weekdays() and
                   t.time_from <= slot.start_time.strftime('%H:%M') <= t.time_to]
        tariff = max(tariffs, key=lambda t: t.priority) if tariffs else None
        base = ((tariff.price_per_slot + (tariff.price_per_extra_player or 0) *
                 max(0, count - quest.min_players)) if tariff else Decimal('2500.00'))
        # Отзывы создаются только для завершённых игр; здесь брони подтверждённые.
        db.session.add(Booking(
            confirmation_code=secrets.token_hex(8).upper(), slot_id=slot.id,
            client_id=random.choice(clients).id, players_count=count,
            status=BOOKING_CONFIRMED, base_price=base, discount_amount=0,
            final_price=base, source=random.choice(['widget', 'phone', 'admin']),
        ))
        slot.status = SLOT_BOOKED
    db.session.flush()


def make_reviews(n):
    # Для новых отзывов подходят брони без отзывов. Если бронь ещё подтверждена,
    # отмечаем её и слот как завершённые (только для демо-данных).
    reviewed = db.session.query(Review.booking_id)
    candidates = (Booking.query.filter(Booking.status.in_([BOOKING_CONFIRMED, BOOKING_COMPLETED]),
                                       ~Booking.id.in_(reviewed))
                  .order_by(Booking.id).limit(n).all())
    if len(candidates) < n:
        raise ValueError(f"Бронирований без отзывов {len(candidates)}, требуется {n}. Увеличьте --bookings.")
    for booking in candidates:
        booking.status = BOOKING_COMPLETED
        booking.slot.status = SLOT_COMPLETED
        db.session.add(Review(booking_id=booking.id, client_id=booking.client_id,
                              rating=random.choices([3, 4, 5], weights=[1, 3, 6])[0],
                              text=random.choice(COMMENTS)))
    db.session.flush()


def main():
    parser = argparse.ArgumentParser(description='Добавить тестовые строки в QuestEvent SQLite')
    for key in ('clients', 'slots', 'bookings', 'reviews'):
        parser.add_argument(f'--{key}', type=int, default=0, metavar='N')
    parser.add_argument('--seed', type=int, default=42, help='Seed генератора случайных чисел')
    parser.add_argument('--dry-run', action='store_true', help='Проверить операцию без сохранения')
    args = parser.parse_args()
    if any(getattr(args, key) < 0 for key in ('clients', 'slots', 'bookings', 'reviews')):
        parser.error('Количество строк не может быть отрицательным')
    random.seed(args.seed)
    app = create_app()
    with app.app_context():
        print('База данных:', db.engine.url.render_as_string(hide_password=True))
        try:
            make_clients(args.clients)
            make_slots(args.slots)
            make_bookings(args.bookings)
            make_reviews(args.reviews)
            if args.dry_run:
                db.session.rollback()
                print('DRY RUN: все изменения отменены.')
            else:
                db.session.commit()
                print('Успешно добавлено:', {k: getattr(args, k) for k in ('clients', 'slots', 'bookings', 'reviews')})
        except Exception:
            db.session.rollback()
            raise


if __name__ == '__main__':
    main()
