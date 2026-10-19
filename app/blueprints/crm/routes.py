from flask import render_template, request, redirect, url_for, flash, abort
from sqlalchemy import false
from flask_login import login_required, current_user

from app.blueprints.crm import bp
from app.blueprints.rbac import staff_required, roles_required
from app.extensions import db
from app.models import User, Review, Booking, Slot, Room, Location
from app.constants import ROLE_CLIENT, ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN
from app.forms.crm_forms import ClientEditForm
from app.services.audit_service import log_action


def _scope_clients_to_branch(query):
    """Для не-суперадминов ограничивает список клиентов теми, у кого есть
    хотя бы одна бронь в филиале текущего сотрудника (клиенты — общие для
    всей сети, поэтому фильтруем не по User.branch_id, а по броням)."""
    if current_user.role == ROLE_SUPERADMIN:
        return query
    if not current_user.branch_id:
        return query.filter(false())  # fail-closed: сотрудник без филиала клиентов не видит
    return (
        query.join(Booking, Booking.client_id == User.id)
        .join(Slot, Slot.id == Booking.slot_id)
        .join(Room, Room.id == Slot.room_id)
        .join(Location, Location.id == Room.location_id)
        .filter(Location.branch_id == current_user.branch_id)
        .distinct()
    )


@bp.route("/clients")
@login_required
@staff_required
def clients():
    search = request.args.get("q", "").strip()
    query = _scope_clients_to_branch(User.query.filter_by(role=ROLE_CLIENT))
    if search:
        # Спецсимволы LIKE (% _ \) экранируем: поиск «100%» не должен превращаться в «найти всех»
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        query = query.filter(
            (User.full_name.ilike(like, escape="\\")) | (User.phone.ilike(like, escape="\\"))
            | (User.email.ilike(like, escape="\\"))
        )
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("crm/clients.html", pagination=pagination, search=search)


def _client_or_403(client_id):
    """Клиент, доступный текущему сотруднику (по общей сети или по своему филиалу)."""
    client = User.query.filter_by(id=client_id, role=ROLE_CLIENT).first_or_404()
    if current_user.role != ROLE_SUPERADMIN:
        has_access = (
            current_user.branch_id and
            Booking.query.join(Slot, Slot.id == Booking.slot_id)
            .join(Room, Room.id == Slot.room_id)
            .join(Location, Location.id == Room.location_id)
            .filter(Booking.client_id == client.id, Location.branch_id == current_user.branch_id)
            .first()
        )
        if not has_access:
            abort(403)
    return client


@bp.route("/clients/<int:client_id>")
@login_required
@staff_required
def client_detail(client_id):
    client = _client_or_403(client_id)
    return render_template("crm/client_detail.html", client=client)


@bp.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN)
def client_edit(client_id):
    client = _client_or_403(client_id)
    form = ClientEditForm(obj=client)
    if form.validate_on_submit():
        phone = form.phone.data.strip()
        email = (form.email.data or "").strip().lower() or None
        if User.query.filter(User.phone == phone, User.id != client.id).first():
            flash("Телефон уже используется другим пользователем", "danger")
            return render_template("crm/client_form.html", form=form, client=client)
        if email and User.query.filter(User.email == email, User.id != client.id).first():
            flash("Email уже используется другим пользователем", "danger")
            return render_template("crm/client_form.html", form=form, client=client)

        client.full_name = form.full_name.data.strip()
        client.phone = phone
        client.email = email
        client.loyalty_points = form.loyalty_points.data or 0
        client.loyalty_status = form.loyalty_status.data
        client.notes = form.notes.data
        log_action("client_updated", "User", client.id)
        db.session.commit()
        flash("Данные клиента обновлены", "success")
        return redirect(url_for("crm.client_detail", client_id=client.id))
    return render_template("crm/client_form.html", form=form, client=client)


@bp.route("/clients/<int:client_id>/toggle-active", methods=["POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN)
def client_toggle_active(client_id):
    client = _client_or_403(client_id)
    client.is_active_flag = not client.is_active_flag
    log_action("client_activity_toggled", "User", client.id, "active" if client.is_active_flag else "blocked")
    db.session.commit()
    flash("Клиент разблокирован" if client.is_active_flag else "Клиент заблокирован", "success")
    return redirect(url_for("crm.client_detail", client_id=client.id))


@bp.route("/reviews")
@login_required
@staff_required
def reviews():
    page = request.args.get("page", 1, type=int)
    query = Review.query
    if current_user.role != ROLE_SUPERADMIN:
        query = (
            query.join(Booking, Booking.id == Review.booking_id)
            .join(Slot, Slot.id == Booking.slot_id)
            .join(Room, Room.id == Slot.room_id)
            .join(Location, Location.id == Room.location_id)
            .filter(Location.branch_id == current_user.branch_id)
        )
    pagination = query.order_by(Review.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("crm/reviews.html", pagination=pagination)
