"""Публичный веб-виджет бронирования (клиентский портал). ТЗ п.4.2.8.

Доступен без авторизации (гостевое бронирование) либо с личным кабинетом
клиента (после регистрации/входа) — история и статус бронирований.
Оформление брони укладывается в 3 шага (ТЗ п.4.1.6):
  1) выбор квеста и локации;  2) выбор даты/времени;  3) данные и подтверждение.
"""
import hmac
from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.blueprints.widget import bp
from app.models import Quest, Room, Location, Slot, Booking
from app.extensions import db
from app.constants import ROLE_CLIENT, BOOKING_COMPLETED
from app.forms.booking_forms import WidgetBookingForm
from app.forms.quest_forms import ReviewForm
from app.extensions import limiter
from app.security import normalize_phone
from app.services import booking_service, client_service
from app.services.exceptions import DomainError


@bp.route("/")
def index():
    quests = (
        Quest.query.filter(Quest.is_active.is_(True))
        .join(Room, Room.id == Quest.room_id).join(Location, Location.id == Room.location_id)
        .filter(Room.is_active.is_(True), Location.is_active.is_(True))
        .all()
    )
    return render_template("widget/index.html", quests=quests)


@bp.route("/quest/<int:quest_id>")
def quest_detail(quest_id):
    from app.models import Review

    quest = db.get_or_404(Quest, quest_id)
    if not quest.is_active:
        abort(404)
    today = date.today()

    reviews = (
        Review.query.join(Booking, Booking.id == Review.booking_id)
        .join(Slot, Slot.id == Booking.slot_id)
        .filter(Slot.quest_id == quest.id)
        .order_by(Review.created_at.desc())
        .limit(6)
        .all()
    )
    active_tariffs = [t for t in quest.tariffs if t.is_active]
    min_price = min((t.price_per_slot for t in active_tariffs), default=None)

    return render_template(
        "widget/quest_detail.html", quest=quest, today=today,
        week_ahead=today + timedelta(days=14), reviews=reviews, min_price=min_price,
    )


@bp.route("/booking/step2/<int:slot_id>", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def booking_step2(slot_id):
    """Шаг 2-3: подтверждение выбранного сеанса + данные клиента (бронь подтверждается сразу)."""
    slot = db.get_or_404(Slot, slot_id)
    if slot.status != "available" or not slot.quest.is_active:
        flash("Этот сеанс уже занят, выберите другое время", "warning")
        return redirect(url_for("widget.quest_detail", quest_id=slot.quest_id))

    form = WidgetBookingForm(slot_id=slot_id)
    if current_user.is_authenticated and current_user.role == ROLE_CLIENT:
        form.full_name.data = form.full_name.data or current_user.full_name
        form.phone.data = form.phone.data or current_user.phone
        form.email.data = form.email.data or current_user.email

    if form.validate_on_submit():
        # slot_id берём из URL, а не из скрытого поля формы, чтобы значения не могли разойтись
        try:
            if current_user.is_authenticated and current_user.role == ROLE_CLIENT:
                client = current_user
            else:
                client = client_service.get_or_create_guest_client(
                    form.full_name.data, form.phone.data, form.email.data,
                )
            booking = booking_service.create_booking(
                client=client, slot_id=slot.id, players_count=form.players_count.data,
                promo_code=form.promo_code.data or None, certificate_code=form.certificate_code.data or None,
                source="widget", comment=form.comment.data,
            )
            return redirect(url_for("widget.booking_confirmation", code=booking.confirmation_code))
        except DomainError as exc:
            flash(str(exc), "danger")

    return render_template("widget/booking_step2.html", slot=slot, form=form)


@bp.route("/booking/confirmation/<code>")
def booking_confirmation(code):
    booking = Booking.query.filter_by(confirmation_code=code).first_or_404()
    return render_template("widget/confirmation.html", booking=booking)


@bp.route("/my-bookings")
@login_required
def my_bookings():
    if current_user.role != ROLE_CLIENT:
        return redirect(url_for("admin.dashboard"))
    bookings = Booking.query.filter_by(client_id=current_user.id).order_by(Booking.created_at.desc()).all()
    return render_template("widget/my_bookings.html", bookings=bookings)


@bp.route("/my-bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
def my_booking_cancel(booking_id):
    booking = Booking.query.filter_by(id=booking_id, client_id=current_user.id).first_or_404()
    try:
        booking_service.cancel_booking(booking, reason="Отменено клиентом", initiated_by=current_user)
    except DomainError as exc:
        flash(str(exc), "danger")
    else:
        flash("Бронирование отменено", "info")
    return redirect(url_for("widget.my_bookings"))


@bp.route("/my-bookings/<int:booking_id>/review", methods=["GET", "POST"])
@login_required
def leave_review(booking_id):
    from app.models import Review
    booking = Booking.query.filter_by(id=booking_id, client_id=current_user.id).first_or_404()
    if booking.status != BOOKING_COMPLETED:
        flash("Отзыв можно оставить только после проведения игры", "warning")
        return redirect(url_for("widget.my_bookings"))
    if booking.review:
        flash("Отзыв уже оставлен", "info")
        return redirect(url_for("widget.my_bookings"))

    form = ReviewForm()
    if form.validate_on_submit():
        review = Review(booking_id=booking.id, client_id=current_user.id,
                         rating=int(form.rating.data), text=form.text.data)
        db.session.add(review)
        db.session.commit()
        flash("Спасибо за отзыв!", "success")
        return redirect(url_for("widget.my_bookings"))
    return render_template("widget/review_form.html", form=form, booking=booking)


@bp.route("/lookup", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def lookup_booking():
    """Поиск брони по коду подтверждения + телефону — без авторизации (гостевой доступ)."""
    booking = None
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        phone = request.form.get("phone", "").strip()
        booking = Booking.query.filter_by(confirmation_code=code).first()
        # Телефоны сравниваем в нормализованном виде (8… == +7…) и за константное время
        phones_match = bool(booking) and hmac.compare_digest(
            normalize_phone(booking.client.phone).encode(), normalize_phone(phone).encode(),
        ) and bool(normalize_phone(phone))
        if not booking or not phones_match:
            flash("Бронирование не найдено — проверьте код и телефон", "warning")
            booking = None
    return render_template("widget/lookup.html", booking=booking)


@bp.route('/my-bookings/<int:booking_id>/google-calendar')
@login_required
def google_calendar(booking_id):
    from app.services.external_integrations import google_calendar_url
    booking = Booking.query.filter_by(id=booking_id, client_id=current_user.id).first_or_404()
    if current_user.role != ROLE_CLIENT or booking.status == 'canceled':
        abort(403)
    return redirect(google_calendar_url(booking))


@bp.route('/my-bookings/<int:booking_id>/yandex-route')
@login_required
def yandex_route(booking_id):
    from app.services.external_integrations import yandex_route_url
    booking = Booking.query.filter_by(id=booking_id, client_id=current_user.id).first_or_404()
    if current_user.role != ROLE_CLIENT or booking.status == 'canceled':
        abort(403)
    return redirect(yandex_route_url(booking))
