class DomainError(Exception):
    """Базовое исключение бизнес-логики (переводится в понятное сообщение UI)."""


class SlotConflictError(DomainError):
    """Попытка забронировать уже занятый/недоступный слот."""


class ValidationError(DomainError):
    """Ошибка валидации бизнес-правил (например, число игроков вне диапазона)."""
