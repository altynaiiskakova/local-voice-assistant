import caldav
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

CAL_DAV_URL = os.environ["CAL_DAV_URL"]
CALENDAR_AGENT_USER = os.environ["CALENDAR_AGENT_USER"]
CALENDAR_AGENT_PASSWORD = os.environ["CALENDAR_AGENT_PASSWORD"]


def fetch_upcoming_events(days: int = 7) -> str:
    client = caldav.DAVClient(
        url=CAL_DAV_URL,
        username=CALENDAR_AGENT_USER,
        password=CALENDAR_AGENT_PASSWORD,
    )
    now = datetime.now()
    events = []
    calendars = client.principal().calendars()
    for cal in calendars:
        for ev in cal.search(start=now, end=now + timedelta(days=days), event=True, expand=True):
            v = ev.icalendar_component
            start = v.get("dtstart").dt
            if hasattr(start, "hour"):
                events.append((start, f"{start:%A %d %B, %H:%M} — {v.get('summary')}"))
            else:
                events.append((datetime.combine(start, datetime.min.time()), f"{start:%A %d %B} (all day) — {v.get('summary')}"))

    if not events:
        return "No upcoming events in the next 7 days."
    return "\n".join(line for _, line in sorted(events))


if __name__ == "__main__":
    print(fetch_upcoming_events())