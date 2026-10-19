from datetime import datetime, timezone
from app.extensions import db


class Review(db.Model):
    """Отзыв клиента после проведения игры. ТЗ п.4.2.3."""

    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False, unique=True)
    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)  # 1-5
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    booking = db.relationship("Booking", back_populates="review")
    client = db.relationship("User", back_populates="reviews")

    def __repr__(self):
        return f"<Review booking={self.booking_id} rating={self.rating}>"
