from datetime import datetime, timedelta, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.constants import (
    ROLE_CLIENT, ROLE_SUPERADMIN, STAFF_ROLES, LOGIN_MAX_FAILED_ATTEMPTS, LOGIN_LOCK_MINUTES,
)


class User(db.Model, UserMixin):
    """Единая модель пользователя.

    Объединяет сотрудников (роли superadmin/admin/host/manager/accountant)
    и клиентов (роль client) в одну таблицу для упрощения аутентификации
    (Flask-Login) при сохранении ролевой модели (RBAC, ТЗ п.4.1.5).

    Клиентские CRM-поля (loyalty_points, phone) заполняются для роли client;
    сотруднические (branch_id) — для остальных ролей.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False, default=ROLE_CLIENT, index=True)

    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, index=True)
    phone = db.Column(db.String(50), unique=True, index=True)
    password_hash = db.Column(db.String(255))

    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    branch = db.relationship("Branch", back_populates="users")

    is_active_flag = db.Column("is_active", db.Boolean, default=True, nullable=False)
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)

    # Защита от подбора пароля: счётчик неудачных входов и время блокировки
    failed_login_count = db.Column(db.Integer, default=0, nullable=False, server_default="0")
    locked_until = db.Column(db.DateTime, nullable=True)  # naive UTC

    # --- CRM/лояльность (заполняется для клиентов, ТЗ п.4.2.3) ---
    loyalty_points = db.Column(db.Integer, default=0, nullable=False)
    loyalty_status = db.Column(db.String(30), default="Новичок")
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    bookings = db.relationship("Booking", back_populates="client", foreign_keys="Booking.client_id")
    reviews = db.relationship("Review", back_populates="client")

    # ------------------------------------------------------------------
    # Пароли
    # ------------------------------------------------------------------
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    # Блокировка при переборе пароля -----------------------------------------
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > self._utcnow())

    def register_failed_login(self) -> bool:
        """Учитывает неудачную попытку входа. Возвращает True, если учётная запись
        только что заблокирована (достигнут лимит попыток)."""
        self.failed_login_count = (self.failed_login_count or 0) + 1
        if self.failed_login_count >= LOGIN_MAX_FAILED_ATTEMPTS:
            self.locked_until = self._utcnow() + timedelta(minutes=LOGIN_LOCK_MINUTES)
            self.failed_login_count = 0
            return True
        return False

    def reset_failed_logins(self) -> None:
        self.failed_login_count = 0
        self.locked_until = None

    # Flask-Login ---------------------------------------------------------
    @property
    def is_active(self):  # noqa: D401 - переопределение UserMixin
        return self.is_active_flag

    # RBAC helpers ----------------------------------------------------------
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    def has_role(self, *roles) -> bool:
        return self.role in roles

    def can_access_branch(self, branch_id: int) -> bool:
        """Суперадминистратор видит все филиалы, остальные — только свой."""
        if self.role == ROLE_SUPERADMIN:
            return True
        return self.branch_id == branch_id

    def __repr__(self):
        return f"<User {self.email or self.phone} role={self.role}>"
