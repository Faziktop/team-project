from datetime import datetime, timezone
from app.extensions import db
from app.constants import SLOT_AVAILABLE


class Slot(db.Model):
    """Сеанс расписания (сессия проведения квеста в комнате).

    Единый календарь загрузки локаций (ТЗ п.2.2.2 — исключение двойных
    бронирований). Уникальность по (room_id, start_time) на уровне БД
    гарантирует отсутствие пересечения сеансов в одной комнате.
    """

    __tablename__ = "slots"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    quest_id = db.Column(db.Integer, db.ForeignKey("quests.id"), nullable=False)

    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.String(20), default=SLOT_AVAILABLE, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    room = db.relationship("Room", back_populates="slots")
    quest = db.relationship("Quest", back_populates="slots")

    __table_args__ = (
        db.UniqueConstraint("room_id", "start_time", name="uq_room_start_time"),
    )

    @property
    def active_booking(self):
        """Текущее незакрытое бронирование слота (не 'canceled').

        Слот исторически может иметь несколько записей Booking (после отмены
        и повторного бронирования), поэтому это не ORM-relationship uselist=False,
        а явный запрос за актуальной (не отменённой) записью.
        """
        from app.models.booking import Booking
        from app.constants import BOOKING_CANCELED
        return (
            Booking.query.filter(Booking.slot_id == self.id, Booking.status != BOOKING_CANCELED)
            .order_by(Booking.id.desc())
            .first()
        )

    def __repr__(self):
        return f"<Slot room={self.room_id} start={self.start_time} status={self.status}>"
