import json
import os
import re
import sys
import time
from collections.abc import Iterator

import requests
from dotenv import load_dotenv

from services.datetime_service import current_date

load_dotenv()

OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL_NAME = os.environ["OLLAMA_MODEL"]

SYSTEM_PROMPT = "You are a voice assistant. Speak simply and directly, in plain sentences without lists or symbols. Start with a very short first sentence of at most eight words, then give details."

# a sentence ends at . ! ? or ; followed by whitespace, so "3.5" or "e.g." mid-word isn't split
SENTENCE_END_RE = re.compile(r"(?<=[.!?;])\s+|\s*\n\s*")    


def ask_llm(prompt: str) -> Iterator[str]:
    """
    Answer a user prompt via Ollama, yielding the reply one sentence at a time, to improve responsiveness.
    Ollama streams the reply token by token; each sentence is yielded as soon as it is complete,
    so it can be spoken while the rest is still being generated.
    """
    print(f"Prompt to LLM...\n{prompt} \nUsing {MODEL_NAME}")
    prompt = prompt.strip()

    t2 = time.perf_counter()  # measure time for the request to Ollama
    with requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "system": f"{SYSTEM_PROMPT} Today is {current_date()}.",
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": 200,
            },
        },
        stream=True,
        timeout=120,
    ) as response:
        response.raise_for_status()

        # each streamed line is a JSON object carrying the next few characters in "response"
        pending = ""
        for line in response.iter_lines():
            if not line:
                continue
            pending += json.loads(line).get("response", "")
            # everything before the last sentence end is complete; keep the rest for the next tokens
            *sentences, pending = SENTENCE_END_RE.split(pending)
            for sentence in sentences:
                if not sentence.strip():
                    continue
                print(f"[timing] Ollama sentence ready: {time.perf_counter() - t2:.2f}s")
                yield sentence

    # if there's any leftover text after the last sentence end, yield it as a final sentence
    if pending.strip():
        yield pending.strip()
    print(f"[timing] Ollama request total time: {time.perf_counter() - t2:.2f}s")


# for debugging, allow this file to be run standalone to test the LLM connection
# usage: uv run ollama_client.py "Who are you?"
if __name__ == "__main__":
    for sentence in ask_llm(" ".join(sys.argv[1:])):
        print(sentence)
