"""
Пакет доменных моделей (app/models).

Слой Domain models согласно ТЗ п.4.2.4 (слоистая архитектура):
Presentation/Views -> Service -> Repository/Data Access -> Domain models.
Здесь модели одновременно выполняют роль Domain + Data Access (SQLAlchemy ORM),
а бизнес-логика вынесена в app/services.
"""
from app.extensions import db

from app.models.branch import Branch
from app.models.user import User
from app.models.location import Location
from app.models.room import Room
from app.models.quest import Quest
from app.models.tariff import Tariff
from app.models.checklist import ChecklistTemplate, ChecklistItem, SlotChecklistMark
from app.models.slot import Slot
from app.models.promocode import PromoCode
from app.models.certificate import Certificate
from app.models.booking import Booking
from app.models.review import Review
from app.models.notification import Notification
from app.models.audit import AuditLog

__all__ = [
    "db",
    "Branch",
    "User",
    "Location",
    "Room",
    "Quest",
    "Tariff",
    "ChecklistTemplate",
    "ChecklistItem",
    "SlotChecklistMark",
    "Slot",
    "PromoCode",
    "Certificate",
    "Booking",
    "Review",
    "Notification",
    "AuditLog",
]
