from datetime import datetime, date, timedelta

from flask import render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user

from app.blueprints.schedule import bp
from app.blueprints.rbac import staff_required, roles_required, branch_scoped_query
from app.extensions import db, limiter
from app.models import Room, Quest, Slot, Booking, Location
from app.constants import (
    ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN, MAX_PUBLIC_SLOTS_RANGE_DAYS, MAX_TEXT_FIELD_LENGTH, SLOT_AVAILABLE,
)
from app.forms.quest_forms import SlotGenerationForm
from app.forms.booking_forms import StaffBookingForm
from app.security import date_arg_or_400, safe_referrer_or, truncate
from app.services import schedule_service, booking_service, client_service
from app.services.exceptions import DomainError


def _branch_scoped_booking_or_404(booking_id):
    """Booking, доступный только если его слот принадлежит филиалу текущего
    сотрудника (суперадминистратор видит все филиалы)."""
    q = (
        Booking.query.filter(Booking.id == booking_id)
        .join(Slot, Slot.id == Booking.slot_id)
        .join(Room, Room.id == Slot.room_id)
        .join(Location, Location.id == Room.location_id)
    )
    booking = branch_scoped_query(q, Location.branch_id).first()
    if booking is None:
        abort(404)
    return booking


def _branch_scoped_slot_or_404(slot_id):
    q = (
        Slot.query.filter(Slot.id == slot_id)
        .join(Room, Room.id == Slot.room_id)
        .join(Location, Location.id == Room.location_id)
    )
    slot = branch_scoped_query(q, Location.branch_id).first()
    if slot is None:
        abort(404)
    return slot


@bp.route("/")
@login_required
@staff_required
def calendar():
    day = date_arg_or_400(request.args.get("date"), field="date") or date.today()

    rooms_q = Room.query.join(Location)
    rooms_q = branch_scoped_query(rooms_q, Location.branch_id)
    rooms = rooms_q.order_by(Room.name).all()

    slots = (
        Slot.query.filter(
            Slot.start_time >= datetime.combine(day, datetime.min.time()),
            Slot.start_time <= datetime.combine(day, datetime.max.time()),
        )
        .join(Room)
        .join(Location)
    )
    slots = branch_scoped_query(slots, Location.branch_id).order_by(Slot.start_time).all()

    slots_by_room = {}
    for s in slots:
        slots_by_room.setdefault(s.room_id, []).append(s)

    return render_template(
        "schedule/calendar.html", rooms=rooms, day=day, slots_by_room=slots_by_room,
        prev_day=day - timedelta(days=1), next_day=day + timedelta(days=1),
    )


@bp.route("/generate", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN)
def generate_slots():
    form = SlotGenerationForm()
    rooms_q = Room.query.join(Location)
    rooms_q = branch_scoped_query(rooms_q, Location.branch_id)
    rooms = rooms_q.all()
    form.room_id.choices = [(r.id, f"{r.location.name} / {r.name}") for r in rooms]
    form.quest_id.choices = [(q.id, f"{q.room.name} — {q.title}") for r in rooms for q in r.quests]

    if form.validate_on_submit():
        # Комната и квест уже ограничены филиалом пользователя через choices формы;
        # взаимное соответствие «квест принадлежит комнате» проверяет сервис.
        room = next((r for r in rooms if r.id == form.room_id.data), None)
        quest = db.session.get(Quest, form.quest_id.data)
        if room is None or quest is None:
            abort(404)
        try:
            created = schedule_service.generate_slots_for_room(
                room, quest, form.date_from.data, form.date_to.data,
                form.day_start.data, form.day_end.data,
            )
        except DomainError as exc:
            flash(str(exc), "danger")
        else:
            flash(f"Создано сеансов: {len(created)}", "success")
            return redirect(url_for("schedule.calendar", date=form.date_from.data.isoformat()))
    return render_template("schedule/generate_form.html", form=form)


@bp.route("/booking/new", methods=["GET", "POST"])
@login_required
@staff_required
def booking_new():
    slot_id = request.args.get("slot_id", type=int)
    form = StaffBookingForm()
    if slot_id:
        form.slot_id.data = slot_id
    open_slots_q = (
        Slot.query.filter_by(status=SLOT_AVAILABLE).filter(Slot.start_time > datetime.now() - timedelta(hours=2))
        .join(Room, Room.id == Slot.room_id)
        .join(Location, Location.id == Room.location_id)
    )
    open_slots = branch_scoped_query(open_slots_q, Location.branch_id).order_by(Slot.start_time).limit(200).all()
    form.slot_id.choices = [
        (s.id, f"{s.room.name} — {s.quest.title} — {s.start_time:%d.%m %H:%M}") for s in open_slots
    ]

    if form.validate_on_submit():
        try:
            client = client_service.get_or_create_guest_client(
                form.client_name.data, form.client_phone.data,
            )
            booking = booking_service.create_booking(
                client=client, slot_id=form.slot_id.data, players_count=form.players_count.data,
                promo_code=form.promo_code.data or None, certificate_code=form.certificate_code.data or None,
                source="admin", created_by=current_user, comment=form.comment.data,
            )
            flash(f"Бронирование создано: {booking.confirmation_code}", "success")
            return redirect(url_for("schedule.calendar"))
        except DomainError as exc:
            flash(str(exc), "danger")
    return render_template("schedule/booking_form.html", form=form)


@bp.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
@staff_required
def booking_cancel(booking_id):
    booking = _branch_scoped_booking_or_404(booking_id)
    reason = truncate(request.form.get("reason"), MAX_TEXT_FIELD_LENGTH) or "Отменено сотрудником"
    try:
        booking_service.cancel_booking(booking, reason=reason, initiated_by=current_user)
    except DomainError as exc:
        flash(str(exc), "danger")
    else:
        flash("Бронирование отменено", "info")
    return redirect(safe_referrer_or(url_for("schedule.calendar")))


@bp.route("/booking/<int:booking_id>/complete", methods=["POST"])
@login_required
@staff_required
def booking_complete(booking_id):
    booking = _branch_scoped_booking_or_404(booking_id)
    try:
        booking_service.mark_completed(booking)
    except DomainError as exc:
        flash(str(exc), "danger")
    else:
        flash("Бронирование отмечено как проведённое", "success")
    return redirect(safe_referrer_or(url_for("schedule.calendar")))


@bp.route("/booking/<int:booking_id>/no-show", methods=["POST"])
@login_required
@staff_required
def booking_no_show(booking_id):
    booking = _branch_scoped_booking_or_404(booking_id)
    try:
        booking_service.mark_no_show(booking)
    except DomainError as exc:
        flash(str(exc), "danger")
    else:
        flash("Бронирование отмечено как «неявка»", "info")
    return redirect(safe_referrer_or(url_for("schedule.calendar")))


@bp.route("/slot/<int:slot_id>/checklist", methods=["GET", "POST"])
@login_required
@staff_required
def slot_checklist(slot_id):
    from app.models.checklist import SlotChecklistMark
    slot = _branch_scoped_slot_or_404(slot_id)
    templates = slot.quest.checklist_templates
    items = sorted((item for t in templates for item in t.items), key=lambda i: (i.order or 0, i.id))

    if request.method == "POST":
        checked_ids = set()
        for raw in request.form.getlist("item_id"):
            if raw.isdigit():  # мусорные значения игнорируем, а не роняем запрос в 500
                checked_ids.add(int(raw))
        for item in items:
            mark = SlotChecklistMark.query.filter_by(slot_id=slot.id, item_id=item.id).first()
            if not mark:
                mark = SlotChecklistMark(slot_id=slot.id, item_id=item.id)
                db.session.add(mark)
            mark.is_done = item.id in checked_ids
            mark.marked_by_id = current_user.id
        db.session.commit()
        flash("Чек-лист обновлён", "success")
        return redirect(url_for("schedule.slot_checklist", slot_id=slot.id))

    marks = {m.item_id: m for m in SlotChecklistMark.query.filter_by(slot_id=slot.id).all()}
    return render_template("schedule/checklist.html", slot=slot, items=items, marks=marks)


@bp.route("/api/available-slots")
@limiter.limit("60 per minute")
def api_available_slots():
    """Публичный JSON-эндпоинт для AJAX-календаря виджета бронирования."""
    quest_id = request.args.get("quest_id", type=int)
    d_from = date_arg_or_400(request.args.get("date_from"), field="date_from")
    d_to = date_arg_or_400(request.args.get("date_to"), field="date_to")
    if not (quest_id and d_from and d_to):
        return jsonify({"error": "quest_id, date_from, date_to обязательны"}), 400
    if d_to < d_from:
        return jsonify({"error": "date_to не может быть раньше date_from"}), 400
    if (d_to - d_from).days + 1 > MAX_PUBLIC_SLOTS_RANGE_DAYS:
        return jsonify({"error": f"Диапазон не более {MAX_PUBLIC_SLOTS_RANGE_DAYS} дней"}), 400
    slots = schedule_service.get_available_slots(quest_id, d_from, d_to)
    return jsonify([
        {"id": s.id, "start_time": s.start_time.isoformat(), "end_time": s.end_time.isoformat(), "room": s.room.name}
        for s in slots
    ])
