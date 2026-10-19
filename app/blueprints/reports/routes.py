from datetime import date, timedelta

from flask import render_template, request, send_file, abort
from flask_login import login_required, current_user

from app.blueprints.reports import bp
from app.blueprints.rbac import staff_required
from app.constants import ROLE_SUPERADMIN, MAX_REPORT_PERIOD_DAYS
from app.extensions import limiter
from app.models import Branch
from app.security import date_arg_or_400
from app.services import report_service


def _parse_period():
    """Период отчёта из query-параметров: мусор → 400 (а не 500), «с» > «по» → 400,
    слишком длинный период → 400 (защита от дорогих запросов к БД)."""
    today = date.today()
    d_from = date_arg_or_400(request.args.get("date_from"), field="date_from") or today.replace(day=1)
    d_to = date_arg_or_400(request.args.get("date_to"), field="date_to") or today
    if d_from > d_to:
        abort(400, description="Дата начала периода позже даты окончания")
    if (d_to - d_from).days + 1 > MAX_REPORT_PERIOD_DAYS:
        abort(400, description=f"Период отчёта не может превышать {MAX_REPORT_PERIOD_DAYS} дн.")
    return d_from, d_to


def _branch_scope():
    """Суперадминистратор может выбрать конкретный филиал (или все сразу);
    остальные роли всегда видят только свой филиал — независимо от параметров запроса."""
    if current_user.role == ROLE_SUPERADMIN:
        return request.args.get("branch_id", type=int)
    return current_user.branch_id


def _period_presets(today: date) -> dict[str, tuple[date, date]]:
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    week_start = today - timedelta(days=today.weekday())
    return {
        "today": (today, today),
        "week": (week_start, today),
        "month": (month_start, today),
        "last_month": (last_month_start, last_month_end),
        "last_30": (today - timedelta(days=29), today),
    }


@bp.route("/")
@login_required
@staff_required
def dashboard():
    d_from, d_to = _parse_period()
    branch = _branch_scope()

    occupancy = report_service.occupancy_report(d_from, d_to, branch)
    revenue = report_service.revenue_report(d_from, d_to, branch)
    quest_eff = report_service.quest_effectiveness_report(d_from, d_to, branch)
    host_eff = report_service.host_effectiveness_report(d_from, d_to, branch)
    trend = report_service.revenue_by_day(d_from, d_to, branch)

    avg_occupancy = round(sum(r["occupancy_pct"] for r in occupancy) / len(occupancy), 1) if occupancy else 0.0
    max_daily_revenue = max((r["revenue"] for r in trend), default=0) or 1
    trend_label_step = max(1, len(trend) // 10)

    max_quest_bookings = max((r["bookings_count"] for r in quest_eff), default=0) or 1
    max_host_bookings = max((r["bookings_count"] for r in host_eff), default=0) or 1

    return render_template(
        "reports/dashboard.html", d_from=d_from, d_to=d_to, occupancy=occupancy,
        revenue=revenue, quest_eff=quest_eff, host_eff=host_eff, trend=trend,
        avg_occupancy=avg_occupancy, max_daily_revenue=max_daily_revenue,
        trend_label_step=trend_label_step, max_quest_bookings=max_quest_bookings,
        max_host_bookings=max_host_bookings, presets=_period_presets(date.today()),
        branches=Branch.query.order_by(Branch.name).all() if current_user.role == ROLE_SUPERADMIN else [],
        selected_branch_id=branch,
    )


@bp.route("/export/<report_name>.<fmt>")
@login_required
@staff_required
@limiter.limit("20 per minute")
def export(report_name, fmt):
    d_from, d_to = _parse_period()
    branch = _branch_scope()

    generators = {
        "occupancy": lambda: report_service.occupancy_report(d_from, d_to, branch),
        "quest-effectiveness": lambda: report_service.quest_effectiveness_report(d_from, d_to, branch),
        "host-effectiveness": lambda: report_service.host_effectiveness_report(d_from, d_to, branch),
        "revenue-by-day": lambda: report_service.revenue_by_day(d_from, d_to, branch),
    }
    if report_name not in generators:
        return "Неизвестный отчёт", 404
    if fmt not in ("csv", "xlsx"):
        return "Формат не поддерживается (доступны csv, xlsx)", 400
    rows = generators[report_name]()

    if fmt == "csv":
        buf = report_service.export_rows_to_csv(rows)
        mimetype = "text/csv"
    elif fmt == "xlsx":
        buf = report_service.export_rows_to_xlsx(rows, sheet_title=report_name)
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        return "Формат не поддерживается (доступны csv, xlsx)", 400

    filename = f"{report_name}_{d_from}_{d_to}.{fmt}"
    return send_file(buf, mimetype=mimetype, as_attachment=True, download_name=filename)
