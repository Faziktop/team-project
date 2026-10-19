from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional, Email, Length, NumberRange

from wtforms.validators import Regexp

from app.constants import LOYALTY_STATUSES
from app.forms.booking_forms import PHONE_PATTERN, PHONE_MESSAGE


class ClientEditForm(FlaskForm):
    full_name = StringField("ФИО", validators=[DataRequired(), Length(max=150)])
    phone = StringField("Телефон", validators=[DataRequired(), Length(max=50), Regexp(PHONE_PATTERN, message=PHONE_MESSAGE)])
    email = StringField("Email", validators=[Optional(), Email()])
    loyalty_points = IntegerField("Бонусные баллы", validators=[Optional(), NumberRange(min=0, max=10_000_000)])
    loyalty_status = SelectField("Статус лояльности", choices=[(s, s) for s in LOYALTY_STATUSES])
    notes = TextAreaField("Заметки", validators=[Optional(), Length(max=2000)])
