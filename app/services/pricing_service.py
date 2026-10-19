"""Расчёт стоимости бронирования. ТЗ п.4.2.1 (математическое обеспечение):
стандартные алгоритмы расчёта тарифов со скидками.
"""
from datetime import date
from decimal import Decimal

from app.models.tariff import Tariff
from app.models.quest import Quest
from app.models.promocode import PromoCode
from app.models.certificate import Certificate
from app.services.exceptions import ValidationError


def find_applicable_tariff(quest: Quest, on_date: date, on_time: str) -> Tariff | None:
    """Находит наиболее приоритетный активный тариф, покрывающий дату/время/день недели."""
    candidates = [t for t in quest.tariffs if t.is_active]
    weekday = on_date.weekday()
    matching = []
    for t in candidates:
        if weekday not in t.weekdays():
            continue
        if t.valid_from and on_date < t.valid_from:
            continue
        if t.valid_to and on_date > t.valid_to:
            continue
        if not (t.time_from <= on_time <= t.time_to):
            continue
        matching.append(t)
    if not matching:
        return None
    matching.sort(key=lambda t: t.priority, reverse=True)
    return matching[0]


def calculate_base_price(quest: Quest, tariff: Tariff, players_count: int) -> Decimal:
    if players_count < quest.min_players or players_count > quest.max_players:
        raise ValidationError(
            f"Число игроков должно быть от {quest.min_players} до {quest.max_players}"
        )
    price = Decimal(tariff.price_per_slot)
    extra_players = max(0, players_count - quest.min_players)
    price += Decimal(tariff.price_per_extra_player) * extra_players
    return price


def apply_promocode(base_price: Decimal, promo: PromoCode | None) -> Decimal:
    if promo is None:
        return Decimal("0")
    discount = Decimal("0")
    if promo.discount_percent:
        discount += base_price * Decimal(promo.discount_percent) / Decimal(100)
    if promo.discount_amount:
        discount += Decimal(promo.discount_amount)
    return min(discount, base_price)


def calculate_price(quest: Quest, on_date: date, on_time: str, players_count: int,
                     promo: PromoCode | None = None):
    """Возвращает словарь с разбивкой стоимости бронирования.

    Raises:
        ValidationError: если не найден подходящий тариф или нарушены лимиты игроков.
    """
    tariff = find_applicable_tariff(quest, on_date, on_time)
    if tariff is None:
        raise ValidationError("Для выбранной даты/времени не настроен тариф")

    base_price = calculate_base_price(quest, tariff, players_count)
    discount = apply_promocode(base_price, promo)
    final_price = base_price - discount

    return {
        "tariff": tariff,
        "base_price": base_price,
        "discount_amount": discount,
        "final_price": final_price,
    }


def apply_certificate(final_price: Decimal, certificate: Certificate | None):
    """Возвращает (сумма_к_списанию_с_сертификата, остаток_к_оплате)."""
    if certificate is None or not certificate.is_valid():
        return Decimal("0"), final_price
    usable = min(Decimal(certificate.balance), final_price)
    remainder = final_price - usable
    return usable, remainder
