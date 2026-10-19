from datetime import date
import pytest

from app.services import pricing_service
from app.services.exceptions import ValidationError


def test_calculate_price_basic(demo_data):
    quest = demo_data["quest"]
    result = pricing_service.calculate_price(quest, date.today(), "12:00", players_count=2)
    assert float(result["base_price"]) == 1000
    assert float(result["final_price"]) == 1000


def test_calculate_price_extra_players(demo_data):
    quest = demo_data["quest"]
    result = pricing_service.calculate_price(quest, date.today(), "12:00", players_count=4)
    # 2 extra players over min_players=2, at 100 each
    assert float(result["base_price"]) == 1200


def test_calculate_price_out_of_range_players(demo_data):
    quest = demo_data["quest"]
    with pytest.raises(ValidationError):
        pricing_service.calculate_price(quest, date.today(), "12:00", players_count=99)


def test_calculate_price_no_tariff_found(demo_data, db):
    quest = demo_data["quest"]
    # Деактивируем единственный тариф — расчёт должен упасть с понятной ошибкой
    demo_data["tariff"].is_active = False
    db.session.commit()
    with pytest.raises(ValidationError):
        pricing_service.calculate_price(quest, date.today(), "12:00", players_count=2)
