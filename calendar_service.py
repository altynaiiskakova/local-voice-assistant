import os
from datetime import date, datetime, time, timedelta, timezone

import caldav
from dotenv import load_dotenv

load_dotenv()

CAL_DAV_URL = os.environ["CAL_DAV_URL"]
CALENDAR_AGENT_USER = os.environ["CALENDAR_AGENT_USER"]
CALENDAR_AGENT_PASSWORD = os.environ["CALENDAR_AGENT_PASSWORD"]


def normalize(dt):
    # all-day events come through as date -> promote to datetime at midnight
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)
    # naive datetime -> attach a timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fmt_time(dt):
    if dt.minute == 0:
        return f"{dt:%H}"
    return f"{dt:%H:%M}"


def fetch_upcoming_events(days: int = 7) -> str:
    client = caldav.DAVClient(
        url=CAL_DAV_URL,
        username=CALENDAR_AGENT_USER,
        password=CALENDAR_AGENT_PASSWORD,
    )
    now = datetime.now(timezone.utc)
    events = []
    calendars = client.principal().calendars()
    for cal in calendars:
        for ev in cal.search(
            start=now, end=now + timedelta(days=days), event=True, expand=True
        ):
            v = ev.icalendar_component
            start = v.get("dtstart").dt
            if hasattr(start, "hour"):
                events.append(
                    (start, f"{start:%A %d %B}, {fmt_time(start)} — {v.get('summary')}")
                )
            else:
                events.append(
                    (
                        normalize(start),
                        f"{start:%A %d %B} (all day) — {v.get('summary')}",
                    )
                )

    if not events:
        return f"No upcoming events in the next {days} days."

    sorted_events = ",\n".join(line for _, line in sorted(events))
    # print(sorted_events)
    return sorted_events


if __name__ == "__main__":
    print(fetch_upcoming_events())
