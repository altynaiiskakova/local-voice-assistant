import sys
from datetime import datetime
import requests
import time
import os

from calendar_service import fetch_upcoming_events
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.environ["OLLAMA_URL"]

question = " ".join(sys.argv[1:]) or "What are my upcoming appointments?"

t0 = time.perf_counter()
events = fetch_upcoming_events()
t1 = time.perf_counter()
print(f"[timing] CalDAV fetch: {t1-t0:.2f}s", file=sys.stderr)

prompt = f"""Today is {datetime.now():%A, %d %B %Y, %H:%M}.
The user's calendar for the next 7 days:
{events}
Answer the user's question based on this calendar. Be brief and conversational, the answer will be spoken aloud. Do not use lists, markdown, or symbols; speak in plain sentences.
User's question: {question}"""

t2 = time.perf_counter()
resp = requests.post(OLLAMA_URL, json={
    "model": "qwen2.5:1.5b",
    "prompt": prompt,
    "stream": False,
    "options": {
        "num_predict": 80,
    },
}, timeout=120)
t3 = time.perf_counter()

print(f"[timing] Ollama request: {t3-t2:.2f}s", file=sys.stderr)

resp.raise_for_status()

print(resp.json()["response"])