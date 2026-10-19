from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from app.services.external_integrations import google_calendar_url, yandex_route_url


def test_external_links(demo_data):
    from app.services import booking_service
    b = booking_service.create_booking(demo_data['client_user'], demo_data['slots'][0].id, 2)
    calendar = urlparse(google_calendar_url(b))
    assert calendar.netloc == 'calendar.google.com'
    params = parse_qs(calendar.query)
    assert params['action'] == ['TEMPLATE']
    assert '/' in params['dates'][0]
    route = urlparse(yandex_route_url(b))
    assert route.netloc == 'yandex.ru'
    assert parse_qs(route.query)['rtt'] == ['auto']
