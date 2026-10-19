from datetime import date
from app.extensions import db


class PromoCode(db.Model):
    """Промокод. ТЗ п.4.2.4: онлайн-оплата, депозиты, возвраты, сертификаты, промокоды."""

    __tablename__ = "promocodes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_percent = db.Column(db.Integer, default=0)   # 0-100
    discount_amount = db.Column(db.Numeric(10, 2), default=0)  # фикс. скидка в валюте
    valid_from = db.Column(db.Date)
    valid_to = db.Column(db.Date)
    usage_limit = db.Column(db.Integer, default=0)  # 0 = без ограничения
    used_count = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def is_valid(self, on_date: date | None = None) -> bool:
        on_date = on_date or date.today()
        if not self.is_active:
            return False
        if self.valid_from and on_date < self.valid_from:
            return False
        if self.valid_to and on_date > self.valid_to:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def __repr__(self):
        return f"<PromoCode {self.code}>"
