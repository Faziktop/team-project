from flask import Blueprint

bp = Blueprint("crm", __name__, url_prefix="/crm", template_folder="../../templates/crm")

from app.blueprints.crm import routes  # noqa: E402,F401
