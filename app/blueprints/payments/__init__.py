from flask import Blueprint

bp = Blueprint("payments", __name__, url_prefix="/payments", template_folder="../../templates/payments")

from app.blueprints.payments import routes  # noqa: E402,F401
