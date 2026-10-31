"""
Turn a text prompt into a spoken answer from local LLM.
    text -> ollama_client.ask_llm() -> wyoming-piper service (TTS) -> sox - Sound eXchange (pad + stereo) -> aplay
The answer is streamed: each sentence goes to piper as soon as the LLM finishes it.
Call different services for context if the prompt mentions calendar, weather, etc.
"""

import os
import re
import socket
import subprocess
import sys
from collections.abc import Iterable, Iterator
from urllib.parse import urlparse

import requests
from caldav.lib.error import DAVError
from wyoming.audio import AudioChunk, AudioStop
from wyoming.event import read_event, write_event
from wyoming.tts import Synthesize

from ollama_client import ask_llm
from services.calendar_service import fetch_upcoming_events
from services.weather_service import fetch_weather, match_city_from_prompt

# External tools / audio config (override via env if paths differ).
PIPER_URI = urlparse(os.environ["PIPER_URI"])
SOX_BIN = os.environ.get("SOX_BIN", "/usr/bin/sox")
APLAY_BIN = os.environ.get("APLAY_BIN", "/usr/bin/aplay")
PLAYBACK_DEVICE = os.environ["AUDIO_DEVICE"]
LEAD_SILENCE_SECONDS = 0.2
FALLBACK_TEXT = "Sorry, something went wrong fetching the answer."

CALENDAR_RE = re.compile(r"\b(calendar|appointment|meeting|schedule|event)\b", re.IGNORECASE)
WEATHER_RE = re.compile(r"\b(weather|temperature|forecast|rain|sunny|cold|hot)\b", re.IGNORECASE)


def _synthesize(text: str) -> Iterator[AudioChunk]:
    """Yield the raw audio chunks the wyoming-piper service synthesizes for `text`."""
    with socket.create_connection((PIPER_URI.hostname, PIPER_URI.port)) as sock, sock.makefile("rwb") as conn:
        write_event(Synthesize(text=text).event(), conn)
        # the reply is AudioStart, then AudioChunks, then AudioStop
        while (event := read_event(conn)) is not None and not AudioStop.is_type(event.type):
            if AudioChunk.is_type(event.type):
                yield AudioChunk.from_event(event)


def _start_playback(rate: int) -> tuple[subprocess.Popen, subprocess.Popen]:
    """Start sox | aplay for raw 16-bit mono audio at `rate` Hz, written to sox's stdin."""
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
            str(rate),
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
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    # aplay: ALSA playback utility. Reads audio and sends it to a sound device
    # match what the device wants.
    #   --buffer-time - 0.5s playback buffer. The PowerConf goes idle while the LLM
    #                   is thinking and stalls when playback starts, which drains
    #                   the default buffer and makes aplay report "underrun!!!".
    aplay = subprocess.Popen(
        [APLAY_BIN, "-q", "--buffer-time=500000", "-D", PLAYBACK_DEVICE, "-"],
        stdin=sox.stdout,
    )
    sox.stdout.close()

    return sox, aplay


def _speak(sentences: Iterable[str]) -> str:
    """Synthesize `sentences` as they arrive and play them through the configured output device.
    Pipeline: wyoming-piper service | sox (pad + stereo) | aplay.
    Returns everything that was spoken.
    """
    # sox and aplay start only with the first audio: sox emits the lead silence immediately
    sox = aplay = None
    spoken = []
    try:
        for sentence in sentences:
            print(f"[assistant] LLM says: {sentence}")
            for chunk in _synthesize(sentence):
                if sox is None:
                    sox, aplay = _start_playback(chunk.rate)
                sox.stdin.write(chunk.audio)
            spoken.append(sentence)
    except OSError as exc:
        print(f"[assistant] piper service failed: {exc}", file=sys.stderr)
    finally:
        if sox is not None:
            # closing stdin tells sox the audio is finished, even if the sentences stopped with an error
            sox.stdin.close()

            # wait for playback to finish, and report any errors
            for process, tool_name in ((sox, "sox"), (aplay, "aplay")):
                if process.wait() != 0:
                    print(f"[assistant] {tool_name} exited {process.returncode}", file=sys.stderr)

    return " ".join(spoken)


def _build_prompt(question: str) -> str:
    """Assemble the full LLM prompt for `question`."""
    parts = []

    context = ""
    # If the prompt mentions calendar-related keywords, fetch events and include them in the prompt.
    if CALENDAR_RE.search(question):
        events = fetch_upcoming_events(7)
        context = f"The user's calendar for the next 7 days:\n{events}\nAnswer the user's question based on this calendar."

    # If the prompt mentions weather-related keywords, fetch weather
    # report and include it in the prompt.
    elif WEATHER_RE.search(question):
        city = match_city_from_prompt(question)
        report = fetch_weather(city)
        context = f"\n{report}\nAnswer the user's question based on this report and add recommendations for appropriate clothing and accessories."
    else:
        context = ""

    if context:
        parts.append(context)

    parts.append(f"User's question: {question}")
    return "\n".join(parts)


def ask_and_speak(question: str) -> str:
    """Answer `question`, speak the reply, and return it."""
    question = question.strip()
    if not question:
        return ""

    try:
        prompt = _build_prompt(question)
    except (requests.RequestException, DAVError, OSError) as exc:
        print(f"[assistant] context lookup failed: {exc}", file=sys.stderr)
        prompt = f"\nUser's question: {question}"

    # print("Asking LLM...", file=sys.stderr)
    return _speak(_yield_sentences(prompt))


def _yield_sentences(prompt: str) -> Iterator[str]:
    """Yield the LLM's answer sentence by sentence, or FALLBACK_TEXT if the request fails before any sentence."""
    answered = False
    try:
        for sentence in ask_llm(prompt):
            answered = True
            yield sentence
    except requests.RequestException as exc:
        print(f"[assistant] ask_llm failed: {exc}", file=sys.stderr)

    if not answered:
        yield FALLBACK_TEXT


# For testing and debugging, run this file directly to speak a prompt from the command line.
# usage: uv run assistant.py "what's on my calendar tomorrow?"
if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:])
    ask_and_speak(prompt)
