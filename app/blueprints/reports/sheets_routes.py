"""Manual bounded export to a Google spreadsheet; superadmin only."""
from datetime import datetime, date, time, timedelta
from flask import current_app, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.orm import joinedload
from app.blueprints.reports import bp
from app.blueprints.rbac import roles_required
from app.constants import ROLE_SUPERADMIN
from app.extensions import limiter
from app.models import Booking, Slot, Room
from app.services.external_integrations import sheets_export

@bp.route("/export/google-sheets", methods=["POST"])
@login_required
@roles_required(ROLE_SUPERADMIN)
@limiter.limit("5 per minute")
def export_google_sheets():
    spreadsheet_id = current_app.config.get("GOOGLE_SHEETS_ID")
    key = current_app.config.get("GOOGLE_SHEETS_CREDENTIALS")
    if not spreadsheet_id or not key:
        flash("Укажите GOOGLE_SHEETS_ID и GOOGLE_SHEETS_CREDENTIALS в .env", "warning")
        return redirect(url_for("reports.dashboard"))
    since = datetime.combine(date.today() - timedelta(days=89), time.min)
    bookings = (Booking.query.options(
        joinedload(Booking.client),
        joinedload(Booking.slot).joinedload(Slot.quest),
        joinedload(Booking.slot).joinedload(Slot.room).joinedload(Room.location),
    ).filter(Booking.created_at >= since).order_by(Booking.id.desc()).limit(5000).all())
    try:
        count = sheets_export(bookings, spreadsheet_id, key)
    except Exception:
        current_app.logger.exception("Google Sheets export failed")
        flash("Ошибка выгрузки: проверьте настройки и журнал приложения.", "danger")
    else:
        flash(f"Google Sheets: выгружено {count} бронирований", "success")
    return redirect(url_for("reports.dashboard"))
