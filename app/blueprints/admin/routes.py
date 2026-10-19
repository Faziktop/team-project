from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.blueprints.admin import bp
from app.blueprints.rbac import staff_required, roles_required, branch_scoped_query
from app.extensions import db
from app.models import Branch, Location, Room, Quest, Tariff, User, AuditLog, Slot, Booking
from app.models.tariff import WEEKDAY_CHOICES
from app.constants import (
    ROLE_LABELS, STAFF_ROLES, ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN, LOCATION_ADMIN_MANAGEABLE_ROLES,
    BOOKING_CONFIRMED, MAX_TEXT_FIELD_LENGTH,
)
from app.security import truncate
from app.forms.auth_forms import StaffUserForm, StaffUserEditForm
from app.forms.quest_forms import BranchForm, LocationForm, RoomForm, QuestForm, TariffForm
from app.services.audit_service import log_action
from app.services import report_service


@bp.route("/")
@login_required
@staff_required
def dashboard():
    kpi = report_service.kpi_dashboard(
        branch_id=None if current_user.role == ROLE_SUPERADMIN else current_user.branch_id
    )
    return render_template("admin/dashboard.html", kpi=kpi)


def _manageable_roles():
    """Роли, которые текущий пользователь вправе назначать/редактировать: суперадмин — любые,
    администратор локации — только линейный персонал (не админов и не суперадминов)."""
    return STAFF_ROLES if current_user.role == ROLE_SUPERADMIN else LOCATION_ADMIN_MANAGEABLE_ROLES


def _count_active_superadmins(exclude_user_id=None) -> int:
    q = User.query.filter(User.role == ROLE_SUPERADMIN, User.is_active_flag.is_(True))
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.count()


def _phone_taken(phone, exclude_user_id=None) -> bool:
    if not phone:
        return False
    q = User.query.filter(User.phone == phone)
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.first() is not None


# ---------------------------------------------------------------- branches
@bp.route("/branches")
@login_required
@roles_required(ROLE_SUPERADMIN)
def branches():
    items = Branch.query.order_by(Branch.name).all()
    return render_template("admin/branches.html", items=items)


@bp.route("/branches/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN)
def branch_new():
    form = BranchForm()
    if form.validate_on_submit():
        b = Branch(name=form.name.data, city=form.city.data, address=form.address.data, phone=form.phone.data)
        db.session.add(b)
        db.session.flush()
        log_action("branch_created", "Branch", b.id)
        db.session.commit()
        flash("Филиал создан", "success")
        return redirect(url_for("admin.branches"))
    return render_template("admin/branch_form.html", form=form, title="Новый филиал")


# ---------------------------------------------------------------- locations
@bp.route("/locations")
@login_required
@staff_required
def locations():
    q = branch_scoped_query(Location.query, Location.branch_id)
    return render_template("admin/locations.html", items=q.order_by(Location.name).all())


@bp.route("/locations/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def location_new():
    form = LocationForm()
    form.branch_id.choices = [(b.id, b.name) for b in Branch.query.order_by(Branch.name)]
    if form.validate_on_submit():
        if current_user.role != ROLE_SUPERADMIN and form.branch_id.data != current_user.branch_id:
            flash("Нет доступа к выбранному филиалу", "danger")
            return redirect(url_for("admin.locations"))
        loc = Location(branch_id=form.branch_id.data, name=form.name.data, address=form.address.data)
        db.session.add(loc)
        db.session.flush()
        log_action("location_created", "Location", loc.id)
        db.session.commit()
        flash("Локация создана", "success")
        return redirect(url_for("admin.locations"))
    return render_template("admin/location_form.html", form=form, title="Новая локация")


# ---------------------------------------------------------------- rooms
@bp.route("/rooms")
@login_required
@staff_required
def rooms():
    q = Room.query.join(Location)
    q = branch_scoped_query(q, Location.branch_id)
    return render_template("admin/rooms.html", items=q.order_by(Room.name).all())


@bp.route("/rooms/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def room_new():
    form = RoomForm()
    locs = Location.query
    locs = branch_scoped_query(locs, Location.branch_id)
    form.location_id.choices = [(l.id, l.name) for l in locs]
    if form.validate_on_submit():
        room = Room(
            location_id=form.location_id.data, name=form.name.data,
            status=form.status.data, maintenance_note=form.maintenance_note.data,
        )
        db.session.add(room)
        db.session.flush()
        log_action("room_created", "Room", room.id)
        db.session.commit()
        flash("Комната создана", "success")
        return redirect(url_for("admin.rooms"))
    return render_template("admin/room_form.html", form=form, title="Новая комната")


@bp.route("/rooms/<int:room_id>/maintenance", methods=["POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def room_toggle_maintenance(room_id):
    from app.models.room import ROOM_STATUS_OK, ROOM_STATUS_MAINTENANCE
    room_q = branch_scoped_query(Room.query.join(Location).filter(Room.id == room_id), Location.branch_id)
    room = room_q.first()
    if room is None:
        abort(404)
    if room.status == ROOM_STATUS_MAINTENANCE:
        room.status = ROOM_STATUS_OK
        room.maintenance_note = None
    else:
        room.status = ROOM_STATUS_MAINTENANCE
        room.maintenance_note = truncate(request.form.get("note"), MAX_TEXT_FIELD_LENGTH) or "Техническое обслуживание"
    log_action("room_maintenance_toggled", "Room", room.id, room.status)
    db.session.commit()
    flash("Статус комнаты обновлён", "success")
    if room.status == ROOM_STATUS_MAINTENANCE:
        # Новые брони на эту комнату уже не принимаются, но ранее оформленные остаются в силе:
        # сообщаем администратору, скольких клиентов нужно предупредить/перенести.
        pending = (
            Booking.query.join(Slot, Slot.id == Booking.slot_id)
            .filter(Slot.room_id == room.id, Booking.status == BOOKING_CONFIRMED, Slot.start_time > datetime.now())
            .count()
        )
        if pending:
            flash(f"Внимание: на эту комнату уже есть подтверждённые будущие брони ({pending}) — "
                  "свяжитесь с клиентами или отмените/перенесите брони.", "warning")
    return redirect(url_for("admin.rooms"))


# ---------------------------------------------------------------- quests
@bp.route("/quests")
@login_required
@staff_required
def quests():
    q = Quest.query.join(Room).join(Location)
    q = branch_scoped_query(q, Location.branch_id)
    return render_template("admin/quests.html", items=q.order_by(Quest.title).all())


@bp.route("/quests/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def quest_new():
    form = QuestForm()
    rooms_q = Room.query.join(Location)
    rooms_q = branch_scoped_query(rooms_q, Location.branch_id)
    form.room_id.choices = [(r.id, f"{r.location.name} / {r.name}") for r in rooms_q]
    if form.validate_on_submit():
        if form.min_players.data > form.max_players.data:
            flash("Минимум игроков не может быть больше максимума", "danger")
            return render_template("admin/quest_form.html", form=form, title="Новый квест")
        quest = Quest(
            room_id=form.room_id.data, title=form.title.data, description=form.description.data,
            difficulty=form.difficulty.data, duration_minutes=form.duration_minutes.data,
            min_players=form.min_players.data, max_players=form.max_players.data,
            min_age=form.min_age.data or 0, is_horror=form.is_horror.data,
        )
        db.session.add(quest)
        db.session.flush()
        log_action("quest_created", "Quest", quest.id)
        db.session.commit()
        flash("Квест создан", "success")
        return redirect(url_for("admin.quests"))
    return render_template("admin/quest_form.html", form=form, title="Новый квест")


# ---------------------------------------------------------------- tariffs
@bp.route("/tariffs")
@login_required
@staff_required
def tariffs():
    q = Tariff.query.join(Quest).join(Room).join(Location)
    q = branch_scoped_query(q, Location.branch_id)
    return render_template("admin/tariffs.html", items=q.all())


@bp.route("/tariffs/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def tariff_new():
    form = TariffForm()
    quests_q = Quest.query.join(Room).join(Location)
    quests_q = branch_scoped_query(quests_q, Location.branch_id)
    form.quest_id.choices = [(q.id, q.title) for q in quests_q]
    if request.method == "POST" and form.validate_on_submit():
        valid_days = {str(i) for i, _ in WEEKDAY_CHOICES}
        weekdays = sorted({d for d in request.form.getlist("weekday") if d in valid_days}, key=int)
        if request.form.getlist("weekday") and not weekdays:
            flash("Некорректные дни недели", "danger")
            return render_template("admin/tariff_form.html", form=form, title="Новый тариф", weekday_choices=WEEKDAY_CHOICES)
        tariff = Tariff(
            quest_id=form.quest_id.data, name=form.name.data,
            weekday_mask=",".join(weekdays) if weekdays else "0,1,2,3,4,5,6",
            time_from=form.time_from.data, time_to=form.time_to.data,
            price_per_slot=form.price_per_slot.data,
            price_per_extra_player=form.price_per_extra_player.data or 0,
            priority=form.priority.data or 0,
        )
        db.session.add(tariff)
        db.session.flush()
        log_action("tariff_created", "Tariff", tariff.id)
        db.session.commit()
        flash("Тариф создан", "success")
        return redirect(url_for("admin.tariffs"))
    return render_template("admin/tariff_form.html", form=form, title="Новый тариф", weekday_choices=WEEKDAY_CHOICES)


# ---------------------------------------------------------------- users
@bp.route("/users")
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def users():
    q = User.query.filter(User.role.in_(STAFF_ROLES))
    q = branch_scoped_query(q, User.branch_id)
    return render_template(
        "admin/users.html", items=q.order_by(User.full_name).all(), role_labels=ROLE_LABELS,
        manageable_roles=_manageable_roles(),
    )


@bp.route("/users/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def user_new():
    form = StaffUserForm()
    form.role.choices = [(r, ROLE_LABELS[r]) for r in _manageable_roles()]
    form.branch_id.choices = [(b.id, b.name) for b in Branch.query.order_by(Branch.name)]
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        phone = (form.phone.data or "").strip() or None
        if User.query.filter(User.email == email).first():
            flash("Email уже используется", "danger")
            return render_template("admin/user_form.html", form=form, title="Новый сотрудник")
        if _phone_taken(phone):
            flash("Телефон уже используется другим пользователем", "danger")
            return render_template("admin/user_form.html", form=form, title="Новый сотрудник")
        branch_id = form.branch_id.data
        if current_user.role != ROLE_SUPERADMIN:
            branch_id = current_user.branch_id
        if not branch_id and form.role.data != ROLE_SUPERADMIN:
            flash("Для сотрудника необходимо указать филиал", "danger")
            return render_template("admin/user_form.html", form=form, title="Новый сотрудник")
        user = User(
            full_name=form.full_name.data.strip(), email=email,
            phone=phone, role=form.role.data, branch_id=branch_id,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        log_action("staff_user_created", "User", user.id, f"role={user.role}")
        db.session.commit()
        flash("Сотрудник добавлен", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, title="Новый сотрудник")


def _staff_user_or_404(user_id):
    """Сотрудник, доступный для управления текущим админом.

    Суперадминистратор управляет всеми. Администратор локации — только линейным персоналом
    (ведущий/менеджер/бухгалтер) СВОЕГО филиала: другие администраторы и суперадмины для него
    «не существуют» (404), поэтому админ не может ни заблокировать коллегу, ни сменить ему
    пароль (а через него — захватить учётную запись).
    """
    user = db.get_or_404(User, user_id)
    if current_user.role != ROLE_SUPERADMIN:
        if user.branch_id != current_user.branch_id or user.role not in LOCATION_ADMIN_MANAGEABLE_ROLES:
            abort(404)
    return user


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def user_edit(user_id):
    user = _staff_user_or_404(user_id)
    form = StaffUserEditForm(obj=user)
    form.role.choices = [(r, ROLE_LABELS[r]) for r in _manageable_roles()]
    form.branch_id.choices = [(b.id, b.name) for b in Branch.query.order_by(Branch.name)]
    if request.method == "GET":
        form.branch_id.data = user.branch_id

    if form.validate_on_submit():
        conflict = User.query.filter(User.email == form.email.data.lower().strip(), User.id != user.id).first()
        if conflict:
            flash("Email уже используется", "danger")
            return render_template("admin/user_form.html", form=form, title=f"Сотрудник: {user.full_name}", is_edit=True)

        phone = (form.phone.data or "").strip() or None
        if _phone_taken(phone, exclude_user_id=user.id):
            flash("Телефон уже используется другим пользователем", "danger")
            return render_template("admin/user_form.html", form=form, title=f"Сотрудник: {user.full_name}", is_edit=True)

        new_role = form.role.data
        new_branch = form.branch_id.data if current_user.role == ROLE_SUPERADMIN else current_user.branch_id
        if user.id == current_user.id:
            # Свою роль и филиал через форму менять нельзя (иначе можно случайно потерять доступ)
            new_role, new_branch = user.role, user.branch_id
        if user.role == ROLE_SUPERADMIN and new_role != ROLE_SUPERADMIN and _count_active_superadmins(user.id) == 0:
            flash("Нельзя изменить роль последнего активного суперадминистратора", "danger")
            return render_template("admin/user_form.html", form=form, title=f"Сотрудник: {user.full_name}", is_edit=True)
        if not new_branch and new_role != ROLE_SUPERADMIN:
            flash("Для сотрудника необходимо указать филиал", "danger")
            return render_template("admin/user_form.html", form=form, title=f"Сотрудник: {user.full_name}", is_edit=True)

        old_role = user.role
        user.full_name = form.full_name.data.strip()
        user.email = form.email.data.lower().strip()
        user.phone = phone
        user.role = new_role
        user.branch_id = new_branch
        password_changed = bool(form.password.data)
        if password_changed:
            user.set_password(form.password.data)
            user.reset_failed_logins()
        log_action("staff_user_updated", "User", user.id,
                   f"role={old_role}->{user.role} password_changed={password_changed}")
        db.session.commit()
        flash("Данные сотрудника обновлены", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, title=f"Сотрудник: {user.full_name}", is_edit=True)


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def user_toggle_active(user_id):
    if user_id == current_user.id:
        flash("Нельзя заблокировать собственную учётную запись", "danger")
        return redirect(url_for("admin.users"))
    user = _staff_user_or_404(user_id)
    if user.role == ROLE_SUPERADMIN and user.is_active_flag and _count_active_superadmins(user.id) == 0:
        flash("Нельзя заблокировать последнего активного суперадминистратора", "danger")
        return redirect(url_for("admin.users"))
    user.is_active_flag = not user.is_active_flag
    log_action("staff_user_activity_toggled", "User", user.id, "active" if user.is_active_flag else "blocked")
    db.session.commit()
    flash("Сотрудник разблокирован" if user.is_active_flag else "Сотрудник заблокирован", "success")
    return redirect(url_for("admin.users"))


@bp.route("/audit-log")
@login_required
@roles_required(ROLE_SUPERADMIN, "admin")
def audit_log():
    page = request.args.get("page", 1, type=int)
    q = AuditLog.query
    if current_user.role != ROLE_SUPERADMIN and current_user.branch_id:
        q = q.join(User, User.id == AuditLog.user_id).filter(User.branch_id == current_user.branch_id)
    pagination = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template("admin/audit_log.html", pagination=pagination)
