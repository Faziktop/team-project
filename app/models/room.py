from app.extensions import db

ROOM_STATUS_OK = "ok"
ROOM_STATUS_MAINTENANCE = "maintenance"


class Room(db.Model):
    """Игровая комната. ТЗ п.4.2.2: учёт технического состояния комнат."""

    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), default=ROOM_STATUS_OK, nullable=False)
    maintenance_note = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    location = db.relationship("Location", back_populates="rooms")
    quests = db.relationship("Quest", back_populates="room")
    slots = db.relationship("Slot", back_populates="room")

    def __repr__(self):
        return f"<Room {self.name}>"
