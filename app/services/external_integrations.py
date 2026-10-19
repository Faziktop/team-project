from datetime import timezone
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo

def google_calendar_url(booking):
    tz = ZoneInfo(booking.slot.room.location.timezone or "Europe/Moscow")
    start = booking.slot.start_time.replace(tzinfo=tz).astimezone(timezone.utc)
    end = booking.slot.end_time.replace(tzinfo=tz).astimezone(timezone.utc)
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action":"TEMPLATE", "text":booking.slot.quest.title,
        "dates":f"{start:%Y%m%dT%H%M%SZ}/{end:%Y%m%dT%H%M%SZ}",
        "location":booking.slot.room.location.address,
        "details":"QuestEvent booking"
    })

def yandex_route_url(booking):
    return "https://yandex.ru/maps/?" + urlencode({
        "rtext":"~" + booking.slot.room.location.address,"rtt":"auto"})

def sheets_export(bookings, spreadsheet_id, credentials_path):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(creds)
    base = "https://sheets.googleapis.com/v4/spreadsheets/" + quote(spreadsheet_id, safe="")
    response = session.get(base, timeout=15)
    response.raise_for_status()
    if "QuestEvent" not in [x["properties"]["title"] for x in response.json().get("sheets",[])]:
        response = session.post(base + ":batchUpdate", json={"requests":[
            {"addSheet":{"properties":{"title":"QuestEvent"}}}]}, timeout=15)
        response.raise_for_status()
    rows = [["ID","Code","Quest","Location","Date","Client","Status","Players","Price"]]
    rows.extend([[str(b.id),b.confirmation_code,b.slot.quest.title,
        b.slot.room.location.name,b.slot.start_time.strftime("%Y-%m-%d %H:%M"),
        b.client.full_name,b.status,str(b.players_count),str(b.final_price)] for b in bookings])
    tab = quote("'QuestEvent'!A:Z",safe="")
    response = session.post(base + "/values/" + tab + ":clear",json={},timeout=15)
    response.raise_for_status()
    response = session.put(base + "/values/" + tab,params={"valueInputOption":"RAW"},
        json={"range":"'QuestEvent'!A1","majorDimension":"ROWS","values":rows},timeout=20)
    response.raise_for_status()
    return len(bookings)
