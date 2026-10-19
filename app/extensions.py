"""Единые экземпляры расширений Flask (инициализируются в app factory)."""
from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Включает контроль внешних ключей и WAL для SQLite-соединений.

    По умолчанию SQLite не проверяет FOREIGN KEY на уровне БД, поэтому
    без этого PRAGMA осиротевшие/противоречивые ссылки не отклоняются движком.
    """
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
cache = Cache()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = "auth.login"
login_manager.session_protection = "strong"  # сессия привязывается к IP/User-Agent
login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."
login_manager.login_message_category = "warning"
