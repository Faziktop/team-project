from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.blueprints.auth import bp
from app.forms.auth_forms import LoginForm, ClientRegisterForm
from app.models.user import User
from app.extensions import db, limiter
from app.constants import ROLE_CLIENT
from app.security import is_safe_redirect_url, sanitize_for_log
from app.services.audit_service import log_action

# Хеш-заглушка: при неизвестном email всё равно выполняем проверку пароля, чтобы время
# ответа не выдавало, существует ли такая учётная запись (защита от user enumeration).
_DUMMY_PASSWORD_HASH = generate_password_hash("qe-timing-equalizer")

LOGIN_FAILED_MESSAGE = (
    "Неверный email или пароль. После нескольких неудачных попыток вход в учётную запись "
    "временно блокируется."
)


def _verify_password(user, raw_password: str) -> bool:
    """Проверяет пароль; для несуществующего пользователя/без пароля всё равно тратит
    столько же времени (сверка с хешем-заглушкой) и возвращает False."""
    if user is not None and user.password_hash:
        return check_password_hash(user.password_hash, raw_password)
    check_password_hash(_DUMMY_PASSWORD_HASH, raw_password)
    return False


def _is_safe_next_url(target: str | None) -> bool:
    """Обратно-совместимое имя; реализация — в app.security.is_safe_redirect_url."""
    return is_safe_redirect_url(target)


def _home_for(user) -> str:
    return url_for("admin.dashboard") if user.is_staff() else url_for("widget.index")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()

        locked = bool(user and user.is_locked())
        password_ok = _verify_password(user, form.password.data)

        if user and not locked and password_ok and user.is_active:
            user.reset_failed_logins()
            session.clear()          # новая сессия после аутентификации (против session fixation)
            session.permanent = True  # действует PERMANENT_SESSION_LIFETIME
            login_user(user, remember=form.remember.data)
            log_action("login", "User", user.id)
            db.session.commit()
            next_url = request.args.get("next")
            if is_safe_redirect_url(next_url):
                return redirect(next_url)
            return redirect(_home_for(user))

        # --- неудачная попытка ------------------------------------------------
        if user and not locked:
            just_locked = user.register_failed_login()
            log_action("login_failed", "User", user.id, f"email={sanitize_for_log(email, 150)}")
            if just_locked:
                log_action("login_locked", "User", user.id, "лимит неудачных попыток исчерпан")
            db.session.commit()
        elif user and locked:
            log_action("login_rejected_locked", "User", user.id)
            db.session.commit()
        flash(LOGIN_FAILED_MESSAGE, "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_action("logout", "User", current_user.id)
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def register():
    """Регистрация клиента для личного кабинета (публичный виджет)."""
    form = ClientRegisterForm()
    if form.validate_on_submit():
        email = (form.email.data or "").strip().lower() or None
        phone = form.phone.data.strip()
        conditions = [User.phone == phone]
        if email:
            conditions.append(User.email == email)
        existing = User.query.filter(db.or_(*conditions)).first()
        if existing:
            flash("Пользователь с таким email/телефоном уже существует", "warning")
            return render_template("auth/register.html", form=form)

        user = User(
            role=ROLE_CLIENT,
            full_name=form.full_name.data.strip(),
            email=email,
            phone=phone,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        session.clear()
        session.permanent = True
        login_user(user)
        flash("Регистрация успешна!", "success")
        return redirect(url_for("widget.my_bookings"))
    return render_template("auth/register.html", form=form)
