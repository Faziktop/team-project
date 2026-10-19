from flask import Blueprint

bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../../templates/admin")

from app.blueprints.admin import routes  # noqa: E402,F401

from app.blueprints.admin import performance  # noqa: E402,F401
