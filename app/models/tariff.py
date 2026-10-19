from app.extensions import db

WEEKDAY_CHOICES = [
    (0, "Понедельник"), (1, "Вторник"), (2, "Среда"), (3, "Четверг"),
    (4, "Пятница"), (5, "Суббота"), (6, "Воскресенье"),
]


class Tariff(db.Model):
    """Тариф на квест. ТЗ п.4.2.1: гибкая настройка тарифов по дню недели/времени.

    Версионирование: тарифы не удаляются физически при истечении срока действия
    (valid_to), чтобы сохранить историю расчётов по завершённым бронированиям
    (ТЗ п.4.3.2 — версионирование справочников без потери исторических данных).
    """

    __tablename__ = "tariffs"

    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey("quests.id"), nullable=False)

    name = db.Column(db.String(100), nullable=False, default="Базовый")
    weekday_mask = db.Column(db.String(20), default="0,1,2,3,4,5,6")  # CSV дней недели 0-6
    time_from = db.Column(db.String(5), default="00:00")  # HH:MM
    time_to = db.Column(db.String(5), default="23:59")

    price_per_slot = db.Column(db.Numeric(10, 2), nullable=False)  # базовая цена за сеанс
    price_per_extra_player = db.Column(db.Numeric(10, 2), default=0)  # доплата за игрока сверх min_players
    priority = db.Column(db.Integer, default=0)  # чем больше — тем выше приоритет при пересечении правил

    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    quest = db.relationship("Quest", back_populates="tariffs")

    def weekdays(self):
        """Дни недели тарифа (0=Пн … 6=Вс). Некорректные токены игнорируются, чтобы испорченная
        маска не приводила к исключению при расчёте цены (500 на странице бронирования)."""
        days = set()
        for token in (self.weekday_mask or "").split(","):
            token = token.strip()
            if token.isdigit() and 0 <= int(token) <= 6:
                days.add(int(token))
        return days

    def __repr__(self):
        return f"<Tariff {self.name} quest={self.quest_id}>"
