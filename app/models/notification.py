from datetime import datetime, timezone
from app.extensions import db


class Notification(db.Model):
    """Журнал отправленных уведомлений. ТЗ п.4.2.5.

    Отправка через реальные email/SMS/мессенджер-провайдеры выполняется
    сервисным слоем (app/services/notification_service.py) через сменные
    адаптеры; в демонстрационной конфигурации используется консольный/лог
    адаптер (см. README «Известные ограничения демо-версии»).
    """

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    channel = db.Column(db.String(20), nullable=False)
    notif_type = db.Column(db.String(40), nullable=False)
    recipient = db.Column(db.String(150))
    subject = db.Column(db.String(200))
    body = db.Column(db.Text)

    status = db.Column(db.String(20), default="sent")  # sent/failed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Notification {self.notif_type} -> {self.recipient}>"
