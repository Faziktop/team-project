"""Общие валидаторы WTForms."""
import re
from datetime import date

from wtforms.validators import StopValidation, ValidationError

# Самые распространённые слабые пароли, проходящие проверку «буква + цифра»
COMMON_PASSWORDS = frozenset({
    "password1", "password12", "password123", "qwerty123", "qwerty1234", "qwertyuiop1",
    "12345678a", "1234567a", "abc12345", "abcd1234", "admin1234", "admin12345", "letmein123",
    "welcome123", "iloveyou1", "1q2w3e4r", "1qaz2wsx", "zaq12wsx", "qazwsx123", "passw0rd",
    "p@ssw0rd", "adminadmin1", "changeme123", "questevent1", "quest1234", "test1234",
})


class StrongPassword:
    """Пароль: не короче min_length, хотя бы одна буква и одна цифра, не из списка
    распространённых и не совпадает с email/телефоном (если указано поле-сравнение)."""

    def __init__(self, min_length: int = 8, compare_fields: tuple[str, ...] = ("email",)):
        self.min_length = min_length
        self.compare_fields = compare_fields

    def __call__(self, form, field):
        value = field.data or ""
        if not value:  # пустое значение обрабатывают DataRequired/Optional
            return
        if len(value) < self.min_length:
            raise ValidationError(f"Пароль должен содержать не менее {self.min_length} символов")
        if not re.search(r"[^\W\d_]", value, re.UNICODE):
            raise ValidationError("Пароль должен содержать хотя бы одну букву")
        if not re.search(r"\d", value):
            raise ValidationError("Пароль должен содержать хотя бы одну цифру")
        if value.lower() in COMMON_PASSWORDS:
            raise ValidationError("Слишком простой пароль — выберите другой")
        for name in self.compare_fields:
            other = getattr(form, name, None)
            if other is not None and other.data and value.lower() == str(other.data).strip().lower():
                raise ValidationError("Пароль не должен совпадать с логином")


class TimeOfDay:
    """Время в формате HH:MM (00:00–23:59). Тарифы сравнивают время как строки,
    поэтому формат должен быть строгим (с ведущим нулём)."""
    _pattern = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

    def __call__(self, form, field):
        if not self._pattern.match((field.data or "").strip()):
            raise ValidationError("Время должно быть в формате ЧЧ:ММ (например, 09:30)")


class DateNotBefore:
    """Дата в поле не раньше даты в другом поле (например, «по» не раньше «с»)."""

    def __init__(self, other_field: str, message: str | None = None):
        self.other_field = other_field
        self.message = message or "Дата окончания не может быть раньше даты начала"

    def __call__(self, form, field):
        other = getattr(form, self.other_field, None)
        if field.data and other is not None and other.data and field.data < other.data:
            raise ValidationError(self.message)


class FutureOrToday:
    def __call__(self, form, field):
        if field.data and field.data < date.today():
            raise ValidationError("Дата не может быть в прошлом")
