from datetime import datetime, timezone
from app.extensions import db


class Branch(db.Model):
    """Филиал сети (Tenant). ТЗ п.4.2.2: сущность «Филиал (Tenant)».

    Каждая Локация принадлежит ровно одному филиалу. Сотрудники (кроме
    суперадминистратора) привязываются к филиалу для разграничения доступа
    (multi-tenant, ТЗ п.4.1.6).
    """

    __tablename__ = "branches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    city = db.Column(db.String(120))
    address = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    locations = db.relationship("Location", back_populates="branch", cascade="all, delete-orphan")
    users = db.relationship("User", back_populates="branch")

    def __repr__(self):
        return f"<Branch {self.name}>"
