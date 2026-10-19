def test_index_lists_active_quests(client, demo_data):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Тестовый квест".encode("utf-8") in resp.data


def test_available_slots_api(client, demo_data):
    quest = demo_data["quest"]
    slot = demo_data["slots"][0]
    day = slot.start_time.date().isoformat()
    resp = client.get(f"/schedule/api/available-slots?quest_id={quest.id}&date_from={day}&date_to={day}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(s["id"] == slot.id for s in data)


def test_full_public_booking_flow(client, demo_data):
    slot = demo_data["slots"][0]
    resp = client.post(
        f"/booking/step2/{slot.id}",
        data={
            "slot_id": slot.id, "full_name": "Иван Иванов", "phone": "+79995551234",
            "email": "ivan@example.com", "players_count": 2, "promo_code": "", "certificate_code": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "confirmation" in resp.request.path

    from app.models import Booking
    booking = Booking.query.filter_by(source="widget").first()
    assert booking is not None
    assert booking.status == "confirmed"


def test_booking_conflict_shows_available_alternative(client, demo_data):
    slot = demo_data["slots"][0]
    # Первое бронирование занимает слот
    client.post(
        f"/booking/step2/{slot.id}",
        data={"slot_id": slot.id, "full_name": "A", "phone": "+79990000011", "players_count": 2},
        follow_redirects=True,
    )
    # Повторный переход на форму этого же слота должен вернуть на страницу квеста с предупреждением
    resp = client.get(f"/booking/step2/{slot.id}", follow_redirects=True)
    assert resp.status_code == 200
    assert "уже занят".encode("utf-8") in resp.data
