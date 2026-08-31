import subprocess

# `date` output minus the timezone name: "Mon 31 Aug 16:46:12 2026"
DATE_FORMAT = "+%a %d %b %H:%M:%S %Y"


def current_datetime() -> str:
    """Return the system date and time from the `date` CLI, without the tz name."""
    result = subprocess.run(
        ["date", DATE_FORMAT],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# for testing and debugging, run this file directly to see the current date/time printed to stdout
# usage: python3 datetime_service.py
if __name__ == "__main__":
    print(current_datetime())
