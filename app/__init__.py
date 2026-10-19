"""Application Factory (ТЗ п.4.2.4 — принцип «Application Factory» Flask)."""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, redirect, url_for, jsonify

from app.config import config_by_name, is_insecure_secret_key, MIN_SECRET_KEY_LENGTH
from app.extensions import db, migrate, login_manager, csrf, cache, limiter


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    if config_name == "production" and is_insecure_secret_key(app.config.get("SECRET_KEY")):
        raise RuntimeError(
            "SECRET_KEY не задан, слишком короткий (< %d символов) или похож на заглушку "
            "из примера. Сгенерируйте криптостойкий секрет: "
            "python -c \"import secrets; print(secrets.token_hex(32))\" "
            "и задайте его переменной окружения SECRET_KEY (см. .env.example)." % MIN_SECRET_KEY_LENGTH
        )

    if app.config.get("PROXY_FIX_HOPS", 0) > 0:
        # Доверяем X-Forwarded-* только от заданного числа прокси (иначе IP клиента подделывается)
        from werkzeug.middleware.proxy_fix import ProxyFix
        hops = app.config["PROXY_FIX_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.join(app.instance_path, "..", "logs"), exist_ok=True)

    _init_extensions(app)
    from app.services.sql_profiler import install as install_sql_profiler
    install_sql_profiler()
    _init_logging(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_session_guards(app)
    _register_cli(app)

    if app.config.get("SCHEDULER_ENABLED", True) and not app.config.get("TESTING") and _should_start_scheduler(app):
        from app.tasks.scheduler import init_scheduler
        init_scheduler(app)

    return app


def _should_start_scheduler(app: Flask) -> bool:
    """Werkzeug-reloader (debug=True) запускает приложение в двух процессах: родитель следит
    за файлами, дочерний (WERKZEUG_RUN_MAIN=true) обслуживает запросы. Планировщик нужен только
    в рабочем процессе — иначе напоминания клиентам уходили бы дважды. Команды `flask db ...`
    и `flask seed-demo` планировщик тоже не запускают."""
    if os.environ.get("QE_DISABLE_SCHEDULER") == "1":
        return False
    # Служебные команды CLI (flask db upgrade, flask seed-demo, flask shell) — не сервер: без планировщика
    argv = sys.argv
    if argv and os.path.basename(argv[0]).startswith("flask") and len(argv) > 1 and argv[1] in ("db", "seed-demo", "shell", "routes"):
        return False
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return True
    # Без reloader'а (production/gunicorn/python run.py без debug) запускаем всегда,
    # а при включённом debug — ждём дочерний процесс reloader'а.
    return not app.debug


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))


def _init_logging(app: Flask) -> None:
    """Структурированное журналирование с ротацией (ТЗ п.4.1.5 — надёжность,
    журналирование ошибок и инцидентов)."""
    if app.testing:
        return
    log_dir = os.path.join(app.root_path, "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(log_dir, "questevent.log"), maxBytes=2_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d]: %(message)s"
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    logging.getLogger("questevent").addHandler(handler)
    logging.getLogger("questevent").setLevel(logging.INFO)


def _register_blueprints(app: Flask) -> None:
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.schedule import bp as schedule_bp
    from app.blueprints.crm import bp as crm_bp
    from app.blueprints.payments import bp as payments_bp
    from app.blueprints.reports import bp as reports_bp
    from app.blueprints.widget import bp as widget_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(widget_bp)


def _register_error_handlers(app: Flask) -> None:
    def _wants_json() -> bool:
        return request.path.startswith("/schedule/api/")

    @app.errorhandler(400)
    def bad_request(e):
        description = getattr(e, "description", None)
        if _wants_json():
            return jsonify({"error": description or "Некорректный запрос"}), 400
        return render_template("errors/400.html", description=description), 400

    @app.errorhandler(401)
    def unauthorized(e):
        if _wants_json():
            return jsonify({"error": "Требуется авторизация"}), 401
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(429)
    def too_many_requests(e):
        if _wants_json():
            return jsonify({"error": "Слишком много запросов"}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Внутренняя ошибка сервера: %s", e)
        return render_template("errors/500.html"), 500


# Content-Security-Policy. Все скрипты и стили — собственные (Bootstrap, иконки и шрифты
# лежат в app/static/vendor), inline-JS в шаблонах запрещён. 'unsafe-inline' оставлен
# только для стилей (в шаблонах есть style="..."); на выполнение скриптов он не влияет.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def _register_security_headers(app: Flask) -> None:
    """Защитные заголовки ответа: CSP, кликджекинг, MIME-sniffing, Referrer, изоляция окна,
    запрет кеширования страниц с персональными данными."""
    @app.after_request
    def set_security_headers(response):
        h = response.headers
        h.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if not app.debug and not app.testing:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Динамические страницы (кабинет, CRM, отчёты, брони) содержат ПДн: не кешируем в браузере
        # и общих прокси. Статика (/static/...) остаётся кешируемой.
        if request.endpoint != "static":
            h["Cache-Control"] = "no-store"
            h.setdefault("Pragma", "no-cache")
        return response


def _register_session_guards(app: Flask) -> None:
    """Немедленно завершает сессию заблокированного пользователя.

    Flask-Login проверяет is_active только на этапе логина, поэтому без
    этой проверки заблокированный сотрудник/клиент с уже открытой сессией
    мог бы продолжать работу до истечения cookie."""
    from flask import redirect, url_for
    from flask_login import current_user, logout_user

    @app.before_request
    def _reject_blocked_user():
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            return redirect(url_for("auth.login"))


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed-demo")
    def seed_demo():
        """Наполняет БД демонстрационными данными: flask seed-demo"""
        from seed import run_seed
        run_seed()
        print("Демо-данные загружены.")
