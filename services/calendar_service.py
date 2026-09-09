import os
from datetime import date, datetime, time, timedelta, timezone

import caldav
from dotenv import load_dotenv

load_dotenv()

CAL_DAV_URL = os.environ["CAL_DAV_URL"]
CALENDAR_AGENT_USER = os.environ["CALENDAR_AGENT_USER"]
CALENDAR_AGENT_PASSWORD = os.environ["CALENDAR_AGENT_PASSWORD"]


def _normalize(dt):
    # all-day events come through as date -> promote to datetime
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)
    # naive datetime -> attach a timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_time(dt):
    # omit minutes if :00, as they might be spoken by Piper
    if dt.minute == 0:
        return f"{dt:%H}"
    return f"{dt:%H:%M}"


def fetch_upcoming_events(days: int = 7) -> str:
    caldav_client = caldav.DAVClient(
        url=CAL_DAV_URL,
        username=CALENDAR_AGENT_USER,
        password=CALENDAR_AGENT_PASSWORD,
    )
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)

    events = []
    for calendar in caldav_client.principal().calendars():
        for event in calendar.search(start=now, end=end, event=True, expand=True):
            event_component = event.icalendar_component
            event_start = event_component.get("dtstart").dt
            event_summary = event_component.get("summary")

            normalized_start = _normalize(event_start)
            day = f"{event_start:%A %d %B}"
            if isinstance(event_start, datetime):
                line = f"{day}, {_fmt_time(event_start)} - {event_summary}"
            else:
                line = f"{day} (all day) - {event_summary}"
            events.append((normalized_start, line))

    if not events:
        return f"No upcoming events in the next {days} days."

    sorted_events = ",\n".join(line for _, line in sorted(events))
    return sorted_events


# for testing and debugging, run this file directly
# usgage: python3 calendar_service.py
if __name__ == "__main__":
    print(fetch_upcoming_events())
