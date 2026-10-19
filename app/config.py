import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    """Базовая конфигурация приложения."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(basedir, "instance", "questevent.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        # PRAGMA foreign_keys/journal_mode задаются в app/extensions.py на событии connect
        "connect_args": {"check_same_thread": False},
    }

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600 * 8  # токен живёт не дольше рабочей смены

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # «Запомнить меня»: cookie так же недоступна из JS и не уходит на чужие сайты
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = False
    REMEMBER_COOKIE_DURATION = timedelta(days=7)

    # Число доверенных reverse-proxy перед приложением (X-Forwarded-For/Proto).
    # 0 — прокси нет, заголовкам X-Forwarded-* НЕ доверяем (иначе IP можно подделать
    # и обойти rate limiting). Если приложение стоит за nginx — задайте 1.
    PROXY_FIX_HOPS = int(os.environ.get("PROXY_FIX_HOPS", "0"))

    # Ограничение размера тела запроса (защита от загрузки гигантских форм)
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024

    CACHE_TYPE = os.environ.get("CACHE_TYPE", "SimpleCache")
    CACHE_DEFAULT_TIMEOUT = 60

    # Бизнес-параметры (могут быть переопределены в БД / настройках филиала)
    REMINDER_24H_HOURS_BEFORE = 24
    REMINDER_2H_HOURS_BEFORE = 2
    REVIEW_REQUEST_DELAY = timedelta(hours=3)

    REMINDER_POLL_SECONDS = int(os.environ.get("REMINDER_POLL_SECONDS", "60"))
    SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "1") == "1"

    GOOGLE_SHEETS_ID = os.environ.get('GOOGLE_SHEETS_ID', '')
    GOOGLE_SHEETS_CREDENTIALS = os.environ.get('GOOGLE_SHEETS_CREDENTIALS', '')

    ITEMS_PER_PAGE = 20

    RATELIMIT_ENABLED = True
    # memory:// работает только в рамках одного процесса. Для нескольких воркеров
    # (gunicorn -w N) задайте общее хранилище: RATELIMIT_STORAGE_URI=redis://host:6379
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SCHEDULER_ENABLED = False
    RATELIMIT_ENABLED = False
    # StaticPool + shared connection необходимы, чтобы in-memory SQLite не
    # "терялась" между запросами теста (иначе каждое новое соединение получает
    # собственную пустую базу).
    from sqlalchemy.pool import StaticPool
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # требует, чтобы приложение обслуживалось по HTTPS
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


# Значения SECRET_KEY, которые нельзя использовать в production
INSECURE_SECRET_PREFIXES = ("dev-secret", "change-me", "changeme", "secret", "test")
MIN_SECRET_KEY_LENGTH = 32


def is_insecure_secret_key(value: str | None) -> bool:
    """True, если ключ пустой, короткий или похож на заглушку из примера/README."""
    if not value or len(value) < MIN_SECRET_KEY_LENGTH:
        return True
    return value.lower().startswith(INSECURE_SECRET_PREFIXES)


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
