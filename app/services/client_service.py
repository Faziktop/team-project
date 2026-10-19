"""Работа с клиентскими учётными записями при гостевом бронировании."""
from sqlalchemy import func

from app.extensions import db
from app.constants import ROLE_CLIENT
from app.models.user import User
from app.services.exceptions import ValidationError


def get_or_create_guest_client(full_name: str, phone: str, email: str | None = None) -> User:
    """Находит клиента по телефону либо создаёт нового (без пароля) для гостевой брони.

    Безопасность:
      * телефон сотрудника (admin/host/manager/...) не может «притянуть» бронь к учётной записи
        сотрудника — вместо этого возвращается понятная ошибка;
      * email, который уже принадлежит другому пользователю, НЕ сохраняется для нового клиента
        (иначе INSERT падал бы на UNIQUE и пользователь видел бы 500); подтверждения брони
        в таком случае уходят только по SMS/на телефон.
    """
    phone = (phone or "").strip()
    full_name = (full_name or "").strip()
    if not phone:
        raise ValidationError("Укажите телефон")

    existing = User.query.filter_by(phone=phone).first()
    if existing is not None:
        if existing.role != ROLE_CLIENT:
            raise ValidationError(
                "Этот номер телефона нельзя использовать для онлайн-бронирования — укажите другой номер."
            )
        return existing

    email_norm = (email or "").strip().lower() or None
    if email_norm and User.query.filter(func.lower(User.email) == email_norm).first() is not None:
        email_norm = None

    client = User(role=ROLE_CLIENT, full_name=full_name, phone=phone, email=email_norm)
    db.session.add(client)
    db.session.commit()
    return client
