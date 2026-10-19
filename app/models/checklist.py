from app.extensions import db


class ChecklistTemplate(db.Model):
    """Шаблон чек-листа подготовки комнаты к сеансу. ТЗ п.4.2.2."""

    __tablename__ = "checklist_templates"

    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey("quests.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False, default="Подготовка комнаты")

    quest = db.relationship("Quest", back_populates="checklist_templates")
    items = db.relationship("ChecklistItem", back_populates="template", cascade="all, delete-orphan")


class ChecklistItem(db.Model):
    __tablename__ = "checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("checklist_templates.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    order = db.Column(db.Integer, default=0)

    template = db.relationship("ChecklistTemplate", back_populates="items")


class SlotChecklistMark(db.Model):
    """Отметка выполнения пункта чек-листа для конкретного сеанса (Slot)."""

    __tablename__ = "slot_checklist_marks"

    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slots.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("checklist_items.id"), nullable=False)
    is_done = db.Column(db.Boolean, default=False, nullable=False)
    marked_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    __table_args__ = (db.UniqueConstraint("slot_id", "item_id", name="uq_slot_checklist_item"),)
