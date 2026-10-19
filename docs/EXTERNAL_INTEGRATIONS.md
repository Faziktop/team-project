# QuestEvent external integrations

Google Calendar: customer opens My Bookings and selects Google Calendar. A prefilled event is shown for approval. Time is converted from the location timezone.

Yandex Maps: customer selects Route in My Bookings; Yandex Maps opens directions to the address of the booked location.

Google Sheets: enable Google Sheets API in Google Cloud; create a service account and share the target spreadsheet with its account email as Editor. Save JSON key outside the Git repository. Configure environment variables GOOGLE_SHEETS_ID (spreadsheet ID) and GOOGLE_SHEETS_CREDENTIALS (absolute JSON key path). Install requirements and restart the Flask server. Only superadmin can trigger export on Reports. Latest 5000 bookings created over the past 90 days are written into QuestEvent sheet. Existing contents of that tab are replaced. It exports customer names, so handle personal information appropriately.

External providers need internet access. No messaging services are used.
