import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL_NAME = os.environ["OLLAMA_MODEL"]

SYSTEM_PROMPT = "You are a voice assistant. Your reply is spoken aloud, so answer in one or two short plain sentences without lists or symbols."


def ask_llm(prompt: str) -> str:
    """Answer a user prompt via Ollama and return the reply."""
    print("Prompt to LLM...\n" + prompt)
    print(f"Using model: {MODEL_NAME}")
    prompt = prompt.strip()

    t2 = time.perf_counter()  # measure time for the request to Ollama
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 200,
            },
        },
        timeout=120,
    )
    t3 = time.perf_counter()
    print(f"[timing] Ollama request: {t3 - t2:.2f}s", file=sys.stderr)

    resp.raise_for_status()
    print(f"[assistant] LLM raw response: {resp.json()}")
    return resp.json()["response"].strip()


# for debugging, allow this file to be run standalone to test the LLM connection
# usage: uv run ollama_client.py "Who are you?"
if __name__ == "__main__":
    print(ask_llm(" ".join(sys.argv[1:])))
