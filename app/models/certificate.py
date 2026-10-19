from datetime import date
from app.extensions import db


class Certificate(db.Model):
    """Сертификат (подарочная карта). ТЗ п.4.2.4."""

    __tablename__ = "certificates"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    initial_balance = db.Column(db.Numeric(10, 2), nullable=False)
    balance = db.Column(db.Numeric(10, 2), nullable=False)
    expires_at = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    issued_to_name = db.Column(db.String(150))

    def is_valid(self, on_date: date | None = None) -> bool:
        on_date = on_date or date.today()
        if not self.is_active or float(self.balance) <= 0:
            return False
        if self.expires_at and on_date > self.expires_at:
            return False
        return True

    def __repr__(self):
        return f"<Certificate {self.code} balance={self.balance}>"
