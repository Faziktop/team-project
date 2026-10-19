from datetime import datetime, timezone
import secrets
from sqlalchemy import Index, text
from app.extensions import db
from app.constants import BOOKING_CONFIRMED


def generate_confirmation_code():
    return secrets.token_hex(8).upper()


class Booking(db.Model):
    """Бронирование. Центральная сущность подсистемы бронирования и расписания."""

    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    confirmation_code = db.Column(db.String(16), unique=True, default=generate_confirmation_code, nullable=False)

    slot_id = db.Column(db.Integer, db.ForeignKey("slots.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # сотрудник, создавший бронь (если не сам клиент)

    players_count = db.Column(db.Integer, nullable=False, default=2)
    status = db.Column(db.String(20), default=BOOKING_CONFIRMED, nullable=False, index=True)

    base_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    final_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    promocode_id = db.Column(db.Integer, db.ForeignKey("promocodes.id"), nullable=True)
    certificate_id = db.Column(db.Integer, db.ForeignKey("certificates.id"), nullable=True)
    certificate_amount_used = db.Column(db.Numeric(10, 2), default=0)

    source = db.Column(db.String(20), default="widget")  # widget/admin/phone/aggregator
    comment = db.Column(db.String(500))

    reminder_24h_sent = db.Column(db.Boolean, default=False, nullable=False)
    reminder_2h_sent = db.Column(db.Boolean, default=False, nullable=False)
    review_request_sent = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    canceled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    slot = db.relationship("Slot")

    __table_args__ = (
        # Гарантирует не более одного АКТИВНОГО (не отменённого) бронирования на слот,
        # но допускает повторное бронирование того же слота после отмены (история
        # предыдущих отменённых броней сохраняется для CRM/отчётности).
        Index(
            "uq_active_booking_per_slot", "slot_id", unique=True,
            sqlite_where=text("status != 'canceled'"),
        ),
    )
    client = db.relationship("User", back_populates="bookings", foreign_keys=[client_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    promocode = db.relationship("PromoCode")
    certificate = db.relationship("Certificate")
    review = db.relationship("Review", back_populates="booking", uselist=False)

    def __repr__(self):
        return f"<Booking {self.confirmation_code} status={self.status}>"
