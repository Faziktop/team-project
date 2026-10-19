from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SelectField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Optional, Length, Email, Regexp

PHONE_PATTERN = r"^\+?[\d\s\-()]{7,25}$"
PHONE_MESSAGE = "Телефон: только цифры, пробелы, «+», «-» и скобки (7–25 символов)"


class WidgetBookingForm(FlaskForm):
    slot_id = HiddenField(validators=[DataRequired()])
    full_name = StringField("Ваше имя", validators=[DataRequired(), Length(max=150)])
    phone = StringField("Телефон", validators=[DataRequired(), Length(max=50), Regexp(PHONE_PATTERN, message=PHONE_MESSAGE)])
    email = StringField("Email", validators=[Optional(), Length(max=150), Email()])
    players_count = IntegerField("Число игроков", validators=[DataRequired(), NumberRange(min=1, max=30)])
    promo_code = StringField("Промокод", validators=[Optional(), Length(max=50)])
    certificate_code = StringField("Сертификат", validators=[Optional(), Length(max=50)])
    comment = StringField("Комментарий к брони", validators=[Optional(), Length(max=500)])


class StaffBookingForm(FlaskForm):
    slot_id = SelectField("Сеанс", coerce=int, validators=[DataRequired()])
    client_phone = StringField("Телефон клиента", validators=[DataRequired(), Length(max=50), Regexp(PHONE_PATTERN, message=PHONE_MESSAGE)])
    client_name = StringField("Имя клиента", validators=[DataRequired(), Length(max=150)])
    players_count = IntegerField("Число игроков", validators=[DataRequired(), NumberRange(min=1, max=30)])
    promo_code = StringField("Промокод", validators=[Optional(), Length(max=50)])
    certificate_code = StringField("Сертификат", validators=[Optional(), Length(max=50)])
    comment = StringField("Комментарий к брони", validators=[Optional(), Length(max=500)])
