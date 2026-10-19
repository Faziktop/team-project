from datetime import datetime, timezone
from app.extensions import db


class AuditLog(db.Model):
    """Журнал аудита критичных операций. ТЗ п.4.1.5, п.4.2.6.

    Фиксируются: изменение оплат, отмена бронирований, изменение расписания,
    изменение ролей/пользователей.
    """

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.action} by={self.user_id}>"
