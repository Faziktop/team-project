"""Формирование расписания сеансов (Slot). ТЗ п.4.2.1."""
from datetime import datetime, date, time, timedelta

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.slot import Slot
from app.models.room import Room, ROOM_STATUS_MAINTENANCE
from app.models.quest import Quest
from app.constants import SLOT_AVAILABLE, MAX_SLOT_GENERATION_DAYS
from app.services.exceptions import ValidationError


def generate_slots_for_room(room: Room, quest: Quest, date_from: date, date_to: date,
                             day_start: time, day_end: time, step_minutes: int | None = None):
    """Генерирует сеансы для комнаты/квеста на диапазон дат.

    Шаг сеанса по умолчанию равен продолжительности квеста (без окон между играми
    можно передать больший step_minutes для технологического перерыва).
    Пропускает слоты, которые уже существуют (идемпотентно) и комнаты на обслуживании.

    Валидация (данные приходят из формы, а не только из доверенного кода):
      * квест обязан принадлежать выбранной комнате — иначе в расписании появились бы
        сеансы «чужого» квеста, ломающие тарифы, отчёты и бронирование;
      * период ограничен MAX_SLOT_GENERATION_DAYS, время окончания дня позже начала;
      * параллельная генерация одного диапазона безопасна: конфликт уникального индекса
        (room_id, start_time) перехватывается и операция повторяется без дублей.
    """
    if quest.room_id != room.id:
        raise ValidationError(f"Квест «{quest.title}» не относится к комнате «{room.name}»")
    if room.status == ROOM_STATUS_MAINTENANCE or not room.is_active:
        raise ValidationError(f"Комната «{room.name}» выведена на обслуживание: {room.maintenance_note or ''}")
    if date_from > date_to:
        raise ValidationError("Дата начала не может быть позже даты окончания")
    if (date_to - date_from).days + 1 > MAX_SLOT_GENERATION_DAYS:
        raise ValidationError(f"За один раз можно создать расписание не более чем на {MAX_SLOT_GENERATION_DAYS} дн.")
    if day_end <= day_start:
        raise ValidationError("Время окончания дня должно быть позже времени начала")

    step = step_minutes or quest.duration_minutes
    if step <= 0:
        raise ValidationError("Шаг сеанса должен быть положительным")
    duration = timedelta(minutes=quest.duration_minutes)

    for attempt in (1, 2):
        range_start = datetime.combine(date_from, time.min)
        range_end = datetime.combine(date_to, time.max)
        existing = {
            row[0] for row in db.session.query(Slot.start_time).filter(
                Slot.room_id == room.id, Slot.start_time >= range_start, Slot.start_time <= range_end,
            )
        }

        created = []
        current_date = date_from
        while current_date <= date_to:
            cursor = datetime.combine(current_date, day_start)
            day_end_dt = datetime.combine(current_date, day_end)
            while cursor + duration <= day_end_dt:
                if cursor not in existing:
                    slot = Slot(room_id=room.id, quest_id=quest.id, start_time=cursor,
                                end_time=cursor + duration, status=SLOT_AVAILABLE)
                    db.session.add(slot)
                    created.append(slot)
                cursor += timedelta(minutes=step)
            current_date += timedelta(days=1)

        try:
            db.session.commit()
            return created
        except IntegrityError:
            # Параллельный запрос успел создать часть слотов: повторяем с обновлённым списком
            db.session.rollback()
            if attempt == 2:
                raise ValidationError("Не удалось создать расписание из-за конфликта — повторите операцию")
    return []


def block_slot(slot: Slot, reason: str = ""):
    from app.constants import SLOT_BLOCKED, SLOT_BOOKED
    if slot.status == SLOT_BOOKED:
        raise ValidationError("Нельзя заблокировать слот с активным бронированием")
    slot.status = SLOT_BLOCKED
    db.session.commit()


def get_available_slots(quest_id: int, date_from: date, date_to: date):
    """Свободные сеансы квеста для публичного виджета.

    В выдачу не попадают прошедшие сеансы, сеансы неактивных квестов/локаций и комнат,
    выведенных на обслуживание (иначе клиент мог бы выбрать время, на которое бронь
    всё равно будет отклонена).
    """
    from app.models.location import Location

    return (
        Slot.query
        .join(Room, Room.id == Slot.room_id)
        .join(Location, Location.id == Room.location_id)
        .join(Quest, Quest.id == Slot.quest_id)
        .filter(
            Slot.quest_id == quest_id,
            Slot.status == SLOT_AVAILABLE,
            Slot.start_time > datetime.now(),
            Slot.start_time >= datetime.combine(date_from, time.min),
            Slot.start_time <= datetime.combine(date_to, time.max),
            Room.is_active.is_(True),
            Room.status != ROOM_STATUS_MAINTENANCE,
            Location.is_active.is_(True),
            Quest.is_active.is_(True),
            Quest.room_id == Slot.room_id,
        )
        .order_by(Slot.start_time.asc())
        .all()
    )
