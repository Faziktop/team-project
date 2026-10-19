from datetime import time

from flask_wtf import FlaskForm
from wtforms import (
    StringField, IntegerField, TextAreaField, SelectField, BooleanField, DecimalField,
    DateField, TimeField,
)
from wtforms.validators import DataRequired, NumberRange, Optional, Length, Regexp, ValidationError

from app.forms.validators import TimeOfDay, DateNotBefore, FutureOrToday


# Коды промокодов/сертификатов вводятся клиентами вручную: только буквы, цифры, «-» и «_»
CODE_PATTERN = r"^[A-Za-zА-Яа-яЁё0-9_\-]{3,50}$"
CODE_MESSAGE = "Код: 3–50 символов — буквы, цифры, «-» и «_» (без пробелов)"


class BranchForm(FlaskForm):
    name = StringField("Название филиала", validators=[DataRequired(), Length(max=150)])
    city = StringField("Город", validators=[Optional(), Length(max=120)])
    address = StringField("Адрес", validators=[Optional(), Length(max=255)])
    phone = StringField("Телефон", validators=[Optional(), Length(max=50)])


class LocationForm(FlaskForm):
    branch_id = SelectField("Филиал", coerce=int, validators=[DataRequired()])
    name = StringField("Название локации", validators=[DataRequired(), Length(max=150)])
    address = StringField("Адрес", validators=[DataRequired(), Length(max=255)])


class RoomForm(FlaskForm):
    location_id = SelectField("Локация", coerce=int, validators=[DataRequired()])
    name = StringField("Название комнаты", validators=[DataRequired(), Length(max=150)])
    status = SelectField("Статус", choices=[("ok", "В строю"), ("maintenance", "На обслуживании")])
    maintenance_note = StringField("Примечание", validators=[Optional(), Length(max=255)])


class QuestForm(FlaskForm):
    room_id = SelectField("Комната", coerce=int, validators=[DataRequired()])
    title = StringField("Название квеста", validators=[DataRequired(), Length(max=150)])
    description = TextAreaField("Описание", validators=[Optional()])
    difficulty = SelectField("Сложность", choices=[("легкий", "Лёгкий"), ("средний", "Средний"), ("сложный", "Сложный")])
    duration_minutes = IntegerField("Длительность (мин)", validators=[DataRequired(), NumberRange(min=15, max=480)])
    min_players = IntegerField("Мин. игроков", validators=[DataRequired(), NumberRange(min=1)])
    max_players = IntegerField("Макс. игроков", validators=[DataRequired(), NumberRange(min=1)])
    min_age = IntegerField("Мин. возраст", validators=[Optional(), NumberRange(min=0, max=99)])
    is_horror = BooleanField("Хоррор-квест (усиленная атмосфера в виджете: 18+)")


class TariffForm(FlaskForm):
    quest_id = SelectField("Квест", coerce=int, validators=[DataRequired()])
    name = StringField("Название тарифа", validators=[DataRequired(), Length(max=100)])
    # Дни недели вводятся чекбоксами name="weekday" напрямую в шаблоне
    # (app/templates/admin/tariff_form.html) и читаются через request.form.getlist().
    time_from = StringField("Время с (ЧЧ:ММ)", default="00:00", validators=[DataRequired(), TimeOfDay()])
    time_to = StringField("Время по (ЧЧ:ММ)", default="23:59", validators=[DataRequired(), TimeOfDay()])
    price_per_slot = DecimalField("Цена за сеанс", validators=[DataRequired(), NumberRange(min=0, max=1_000_000)])
    price_per_extra_player = DecimalField("Доплата за игрока сверх мин.", validators=[Optional(), NumberRange(min=0, max=1_000_000)], default=0)
    priority = IntegerField("Приоритет", default=0, validators=[Optional(), NumberRange(min=0, max=1000)])

    def validate_time_to(self, field):
        # Время хранится строками «ЧЧ:ММ», сравнение лексикографическое корректно только при этом формате
        if self.time_from.data and field.data and field.data < self.time_from.data:
            raise ValidationError("Время окончания тарифа не может быть раньше времени начала")


class SlotGenerationForm(FlaskForm):
    room_id = SelectField("Комната", coerce=int, validators=[DataRequired()])
    quest_id = SelectField("Квест", coerce=int, validators=[DataRequired()])
    date_from = DateField("Дата с", format="%Y-%m-%d", validators=[DataRequired(message="Укажите дату начала")])
    date_to = DateField("Дата по", format="%Y-%m-%d",
                        validators=[DataRequired(message="Укажите дату окончания"),
                                    DateNotBefore("date_from", "Дата начала не может быть позже даты окончания")])
    day_start = TimeField("Начало дня", format="%H:%M", default=time(10, 0),
                          validators=[DataRequired(message="Укажите время начала дня")])
    day_end = TimeField("Конец дня", format="%H:%M", default=time(22, 0),
                        validators=[DataRequired(message="Укажите время окончания дня")])

    def validate_day_end(self, field):
        if self.day_start.data and field.data and field.data <= self.day_start.data:
            raise ValidationError("Конец дня должен быть позже начала дня")


class PromoCodeForm(FlaskForm):
    code = StringField("Код", validators=[DataRequired(), Length(max=50), Regexp(CODE_PATTERN, message=CODE_MESSAGE)])
    discount_percent = IntegerField("Скидка, %", validators=[Optional(), NumberRange(min=0, max=100)], default=0)
    discount_amount = DecimalField("Скидка, сумма", validators=[Optional(), NumberRange(min=0, max=1_000_000)], default=0)
    valid_from = DateField("Действует с", format="%Y-%m-%d", validators=[Optional()])
    valid_to = DateField("Действует по", format="%Y-%m-%d",
                         validators=[Optional(), DateNotBefore("valid_from", "Дата окончания раньше даты начала")])
    usage_limit = IntegerField("Лимит использований (0 = без лимита)", default=0,
                               validators=[Optional(), NumberRange(min=0, max=1_000_000)])

    def validate_discount_amount(self, field):
        # Промокод без скидки бессмыслен и, скорее всего, — ошибка ввода
        if not (self.discount_percent.data or 0) and not (field.data or 0):
            raise ValidationError("Укажите скидку в процентах или в рублях")


class CertificateForm(FlaskForm):
    code = StringField("Код сертификата", validators=[DataRequired(), Length(max=50), Regexp(CODE_PATTERN, message=CODE_MESSAGE)])
    initial_balance = DecimalField("Номинал", validators=[DataRequired(), NumberRange(min=1, max=1_000_000)])
    expires_at = DateField("Действует до", format="%Y-%m-%d", validators=[Optional(), FutureOrToday()])
    issued_to_name = StringField("Кому выдан", validators=[Optional(), Length(max=150)])


class ReviewForm(FlaskForm):
    rating = SelectField("Оценка", choices=[(str(i), str(i)) for i in range(1, 6)], validators=[DataRequired()])
    text = TextAreaField("Отзыв", validators=[Optional(), Length(max=2000)])
