"""
Turn a text prompt into a spoken answer from local LLM.
    text -> ollama_client.answer() -> piper (TTS) -> sox - Sound eXchange (pad + stereo) -> aplay
Call different services for context if the prompt mentions calendar, weather, etc.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from caldav.lib.error import DAVError

from ollama_client import ask_llm
from services.calendar_service import fetch_upcoming_events
from services.datetime_service import current_datetime
from services.weather_service import fetch_weather, match_city_from_prompt

HOME = Path.home()
# External tools / audio config (override via env if paths differ).
PIPER_BIN = os.environ.get("PIPER_BIN", str(HOME / "piper/piper/piper"))
PIPER_MODEL = os.environ.get("PIPER_MODEL", str(HOME / "piper/en_US-lessac-medium.onnx"))
SOX_BIN = os.environ.get("SOX_BIN", "/usr/bin/sox")
APLAY_BIN = os.environ.get("APLAY_BIN", "/usr/bin/aplay")
PIPER_RATE = int(
    os.environ.get("PIPER_RATE", "22050")
)  # 22050 Hz is the sample rate of the audio Piper produces.
PLAYBACK_DEVICE = os.environ["AUDIO_DEVICE"]
LEAD_SILENCE_SECONDS = float(os.environ.get("LEAD_SILENCE_SECONDS", "1"))
FALLBACK_TEXT = "Sorry, something went wrong fetching the answer."

CALENDAR_RE = re.compile(r"\b(calendar|appointment|meeting|schedule|event)\b", re.IGNORECASE)
WEATHER_RE = re.compile(r"\b(weather|temperature|forecast|rain|sunny|cold|hot)\b", re.IGNORECASE)
STYLE_INSTRUCTIONS = (
    "Do not use any emojis, smilies or asterisks for emphasis. "
    "The answer will not be seen by a human, it will be spoken aloud. "
    "Be brief and conversational. Do not use lists, markdown, or symbols. "
    "Speak in plain sentences."
)


def _speak(text: str) -> None:
    """Synthesize `text` and play it through the configured output device.
    Pipeline: piper | sox (pad + stereo) | aplay.
    """
    text = text.strip()
    if not text:
        return

    piper = subprocess.Popen(
        [PIPER_BIN, "--model", PIPER_MODEL, "--output_raw"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    # sox ("Sound eXchange") converts and applies effects:
    #   pad 1 0    - one second of leading silence. The PowerConf takes a moment
    #                to wake up when audio starts, and without this it swallows
    #                the first syllable.
    #   channels 2 - mono to stereo; the S3 plays stereo/48kHz even though it
    #                captures mono/16kHz.
    sox = subprocess.Popen(
        [
            SOX_BIN,
            "-t",
            "raw",
            "-r",
            str(PIPER_RATE),
            "-e",
            "signed",
            "-b",
            "16",
            "-c",
            "1",
            "-",
            "-t",
            "wav",
            "-",
            "pad",
            str(LEAD_SILENCE_SECONDS),
            "0",
            "channels",
            "2",
        ],
        stdin=piper.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    # aplay: ALSA playback utility. Reads audio and sends it to a sound device
    # match what the device wants.
    aplay = subprocess.Popen(
        [APLAY_BIN, "-q", "-D", PLAYBACK_DEVICE, "-"],
        stdin=sox.stdout,
    )

    piper.stdout.close()
    sox.stdout.close()

    # feed the text to Piper
    piper.communicate(input=text.encode())
    if piper.returncode != 0:
        print(f"[assistant] piper exited {piper.returncode}", file=sys.stderr)

    # wait for sox and aplay to finish, and report any errors
    for process, tool_name in ((sox, "sox"), (aplay, "aplay")):
        if process.wait() != 0:
            print(f"[assistant] {tool_name} exited {process.returncode}", file=sys.stderr)


def _build_prompt(question: str) -> str:
    """Assemble the full LLM prompt for `question`."""
    parts = [f"The current date and time is {current_datetime()}."]

    context = ""
    # If the prompt mentions calendar-related keywords, fetch events and include them in the prompt.
    if CALENDAR_RE.search(question):
        events = fetch_upcoming_events(7)
        context = (
            f"The user's calendar for the next 7 days:\n{events}\n"
            "Answer the user's question based on this calendar."
        )

    # If the prompt mentions weather-related keywords, fetch weather
    # report and include it in the prompt.
    elif WEATHER_RE.search(question):
        city = match_city_from_prompt(question)
        report = fetch_weather(city)
        context = (
            f"\n{report}\n"
            "Answer the user's question based on this report and add "
            "recommendations for appropriate clothing and accessories."
        )
    else:
        context = ""

    if context:
        parts.append(context)

    parts.append(STYLE_INSTRUCTIONS)
    parts.append(f"User's question: {question}")
    return "\n\n".join(parts)


def ask_and_speak(question: str) -> str:
    """Answer `question`, speak the reply, and return it."""
    question = question.strip()
    if not question:
        return ""

    try:
        prompt = _build_prompt(question)
    except (requests.RequestException, DAVError, OSError) as exc:
        print(f"[assistant] context lookup failed: {exc}", file=sys.stderr)
        prompt = f"{STYLE_INSTRUCTIONS}\n\nUser's question: {question}"

    print("Asking LLM...", file=sys.stderr)
    try:
        response = ask_llm(prompt) or FALLBACK_TEXT
    except requests.RequestException as exc:
        print(f"[assistant] ask_llm failed: {exc}", file=sys.stderr)
        response = FALLBACK_TEXT

    print(f"[assistant] LLM says: {response}", file=sys.stderr)
    _speak(response)
    return response


# For testing and debugging, run this file directly to speak a prompt from the command line.
# usage: python3 assistant.py "what's on my calendar tomorrow?"
if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:])
    ask_and_speak(prompt)
