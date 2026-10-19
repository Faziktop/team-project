from flask import Blueprint

bp = Blueprint("schedule", __name__, url_prefix="/schedule", template_folder="../../templates/schedule")

from app.blueprints.schedule import routes  # noqa: E402,F401
