from app.extensions import db


class Quest(db.Model):
    """Квест/ивент. ТЗ п.4.2.2: справочник квестов/ивентов."""

    __tablename__ = "quests"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    difficulty = db.Column(db.String(30), default="средний")  # легкий/средний/сложный
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    min_players = db.Column(db.Integer, nullable=False, default=2)
    max_players = db.Column(db.Integer, nullable=False, default=6)
    min_age = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_horror = db.Column(db.Boolean, default=False, nullable=False)  # хоррор-квест 18+ — усиленная атмосфера в виджете

    room = db.relationship("Room", back_populates="quests")
    tariffs = db.relationship("Tariff", back_populates="quest", cascade="all, delete-orphan")
    slots = db.relationship("Slot", back_populates="quest")
    checklist_templates = db.relationship(
        "ChecklistTemplate", back_populates="quest", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Quest {self.title}>"
