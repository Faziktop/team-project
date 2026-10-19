from app.extensions import db


class Location(db.Model):
    """Локация (квест-клуб/адрес). ТЗ п.4.2.2."""

    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    timezone = db.Column(db.String(64), default="Europe/Moscow")
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    branch = db.relationship("Branch", back_populates="locations")
    rooms = db.relationship("Room", back_populates="location", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Location {self.name}>"
