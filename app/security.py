"""Небольшие безопасные помощники, общие для нескольких blueprint'ов.

Модуль намеренно не зависит от Flask-контекста (кроме parse_date_arg,
которая вызывает abort), чтобы его можно было тестировать изолированно.
"""
import re
from datetime import date, datetime
from urllib.parse import urlsplit

from flask import abort, request

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_PHONE_NON_DIGITS = re.compile(r"\D+")


def is_safe_redirect_url(target: str | None) -> bool:
    """Разрешает редирект только на локальный путь приложения (защита от open redirect).

    Отклоняются:
      * пустые значения и значения с управляющими символами (\\t, \\n, \\r ...) —
        браузеры вырезают их из URL, что позволяет замаскировать ``//evil.com``;
      * любые обратные слэши: браузеры нормализуют ``\\`` в ``/``, поэтому
        ``/\\evil.com`` фактически превращается в ``//evil.com``;
      * протокол-относительные URL (``//host``) и абсолютные URL со схемой/хостом.
    """
    if not target or not isinstance(target, str):
        return False
    if _CONTROL_CHARS.search(target) or "\\" in target:
        return False
    if not target.startswith("/") or target.startswith("//"):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


def sanitize_for_log(value: object, max_len: int = 500) -> str:
    """Убирает переводы строк и управляющие символы из значения перед записью в лог
    (защита от log injection: клиент не должен уметь подделывать строки журнала)."""
    text = _CONTROL_CHARS.sub(" ", str(value))
    return text[:max_len]


def normalize_phone(raw: str | None) -> str:
    """Приводит телефон к виду «только цифры» для СРАВНЕНИЯ (8XXXXXXXXXX == +7XXXXXXXXXX)."""
    digits = _PHONE_NON_DIGITS.sub("", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def parse_iso_date(value: str | None, *, field: str = "date") -> date | None:
    """Разбирает YYYY-MM-DD. Возвращает None для пустого значения, ValueError — для мусора."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        raise ValueError(f"Некорректная дата в параметре «{field}» (ожидается YYYY-MM-DD)")


def date_arg_or_400(value: str | None, *, field: str = "date") -> date | None:
    """Как parse_iso_date, но вместо ValueError отдаёт HTTP 400 (а не 500)."""
    try:
        return parse_iso_date(value, field=field)
    except ValueError as exc:
        abort(400, description=str(exc))


def truncate(value: str | None, max_len: int) -> str:
    return (value or "").strip()[:max_len]


def safe_referrer_or(default: str) -> str:
    """Возвращает путь предыдущей страницы, только если она находится на этом же хосте;
    иначе — default. (request.referrer нельзя использовать в redirect() напрямую.)"""
    ref = request.referrer
    if not ref:
        return default
    parts = urlsplit(ref)
    if parts.netloc and parts.netloc != request.host:
        return default
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    return path if is_safe_redirect_url(path) else default
