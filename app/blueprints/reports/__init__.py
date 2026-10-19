from flask import Blueprint

bp = Blueprint("reports", __name__, url_prefix="/reports", template_folder="../../templates/reports")

from app.blueprints.reports import routes  # noqa: E402,F401

from app.blueprints.reports import sheets_routes  # noqa: E402,F401
