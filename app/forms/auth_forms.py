from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional

from wtforms.validators import Regexp

from app.forms.booking_forms import PHONE_PATTERN, PHONE_MESSAGE
from app.forms.validators import StrongPassword


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Запомнить меня")


class ClientRegisterForm(FlaskForm):
    full_name = StringField("Имя", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[Optional(), Email()])
    phone = StringField("Телефон", validators=[DataRequired(), Length(max=50), Regexp(PHONE_PATTERN, message=PHONE_MESSAGE)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(max=128), StrongPassword(compare_fields=("email", "phone"))])


class StaffUserForm(FlaskForm):
    full_name = StringField("ФИО", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Телефон", validators=[Optional(), Length(max=50)])
    password = PasswordField("Пароль", validators=[DataRequired(), Length(max=128), StrongPassword()])
    role = SelectField("Роль", validators=[DataRequired()])
    branch_id = SelectField("Филиал", coerce=int, validators=[Optional()])


class StaffUserEditForm(FlaskForm):
    full_name = StringField("ФИО", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Телефон", validators=[Optional(), Length(max=50)])
    password = PasswordField("Новый пароль", validators=[Optional(), Length(max=128), StrongPassword()])
    role = SelectField("Роль", validators=[DataRequired()])
    branch_id = SelectField("Филиал", coerce=int, validators=[Optional()])
