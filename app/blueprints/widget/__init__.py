from flask import Blueprint

bp = Blueprint("widget", __name__, url_prefix="/", template_folder="../../templates/widget")

from app.blueprints.widget import routes  # noqa: E402,F401
