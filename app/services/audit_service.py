from flask import request
from flask_login import current_user

from app.extensions import db
from app.models.audit import AuditLog


def log_action(action: str, entity_type: str | None = None, entity_id: int | None = None, details: str | None = None):
    """Записывает событие в журнал аудита. Вызывается сервисами на критичных операциях."""
    user_id = None
    try:
        if current_user and current_user.is_authenticated:
            user_id = current_user.id
    except Exception:
        user_id = None

    ip = None
    try:
        ip = request.remote_addr
    except RuntimeError:
        ip = None

    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip,
    )
    db.session.add(entry)
    # Коммит выполняется вызывающим сервисом в рамках общей транзакции
