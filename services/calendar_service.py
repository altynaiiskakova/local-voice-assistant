import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import caldav
from dotenv import load_dotenv

TZ = ZoneInfo("Europe/Berlin")

load_dotenv()

CAL_DAV_URL = os.environ["CAL_DAV_URL"]
CALENDAR_AGENT_USER = os.environ["CALENDAR_AGENT_USER"]
CALENDAR_AGENT_PASSWORD = os.environ["CALENDAR_AGENT_PASSWORD"]


def format_time(dt):
    # 14:30 -> "2:30 PM", 13:00 -> "1 PM"
    hour = dt.strftime("%I").lstrip("0")
    suffix = dt.strftime("%p")
    if dt.minute == 0:
        return f"{hour} {suffix}"
    return f"{hour}:{dt.minute:02d} {suffix}"


def day_prefix(d: date, today: date) -> str:
    labels = {0: "Today", 1: "Tomorrow"}
    label = labels.get((d - today).days)
    return f"{label}, " if label else ""


def to_local(start):
    """Return (local date, spoken time) for a timed or all-day event."""
    if isinstance(start, datetime):
        if start.tzinfo is None:
            start = start.replace(tzinfo=TZ)
        start = start.astimezone(TZ)
        return start.date(), format_time(start), start
    # all-day event:
    return start, "all day", datetime.combine(start, datetime.min.time(), TZ)


def get_calendar_text(caldav_client, days: int = 7) -> str:
    now = datetime.now(TZ)
    end = now + timedelta(days=days)
    today = now.date()

    events = []
    for calendar in caldav_client.principal().calendars():
        for event in calendar.search(start=now, end=end, event=True, expand=True):
            event_component = event.icalendar_component
            event_start = event_component.get("dtstart").dt
            summary = str(event_component.get("summary", "Untitled event"))

            event_date, event_time, sort_key = to_local(event_start)
            events.append((sort_key, event_date, event_time, summary))

    if not events:
        return "No events in the next 7 days."

    events.sort(key=lambda e: e[0])
    lines = [f"{day_prefix(event_date, today)}{event_date:%A %-d %B}, {event_time}: {summary}" for _, event_date, event_time, summary in events]
    return "\n".join(lines)


def fetch_upcoming_events(days: int = 7) -> str:
    caldav_client = caldav.DAVClient(
        url=CAL_DAV_URL,
        username=CALENDAR_AGENT_USER,
        password=CALENDAR_AGENT_PASSWORD,
    )
    return get_calendar_text(caldav_client, days)


# for testing and debugging, run this file directly
# usage: uv run calendar_service.py
if __name__ == "__main__":
    print(fetch_upcoming_events())
