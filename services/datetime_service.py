from datetime import datetime


def current_date() -> str:
    """Return the system date from the `date` CLI, without the tz name."""
    return datetime.now().strftime("%A, %-d %B %Y")


# for testing and debugging, run this file directly to see the current date/time printed to stdout
# usage: uv run datetime_service.py
if __name__ == "__main__":
    print(current_date())
