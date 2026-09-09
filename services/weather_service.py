import os
import re
import sys
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL_NAME = os.environ["OLLAMA_MODEL"]

DEFAULT_CITY = os.environ["DEFAULT_CITY"]
WTTR_URL = "https://wttr.in"

# Weather city extraction
_CITY_RE = re.compile(r"\b(?:in|for|at|around)\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,2})")


def match_city_from_prompt(prompt: str) -> str:
    """Pull a city name out of the prompt"""
    match = _CITY_RE.search(prompt)
    return match.group(1).strip() if match else DEFAULT_CITY


def fetch_weather(city: str = DEFAULT_CITY) -> str:
    """Return wttr.in's plain-text report for `city` (default Berlin)."""
    city = (city or DEFAULT_CITY).strip()

    # ?T drop ANSI colour codes so the model sees clean text, nothing else
    # 0 drop the "1/2/3 day forecast" header so the model sees only the current report
    response = requests.get(
        f"{WTTR_URL}/{quote(city)}",
        params={"T": "", "0": ""},
        headers={"User-Agent": "curl/8"},
        timeout=15,
    )
    response.raise_for_status()
    return response.text.strip()


# for testing and debugging, run this file directly to see the current weather report
# usage: python3 weather_service.py [city]
if __name__ == "__main__":
    print(fetch_weather(" ".join(sys.argv[1:]) or DEFAULT_CITY))
