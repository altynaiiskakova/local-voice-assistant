import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL_NAME = os.environ["OLLAMA_MODEL"]


def ask_llm(prompt: str) -> str:
    """Answer a user prompt via Ollama and return the reply."""
    print("Prompt to LLM...\n" + prompt)
    prompt = prompt.strip()

    t2 = time.perf_counter()  # measure time for the request to Ollama
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 100,
            },
        },
        timeout=120,
    )
    t3 = time.perf_counter()
    print(f"[timing] Ollama request: {t3 - t2:.2f}s", file=sys.stderr)

    resp.raise_for_status()
    return resp.json()["response"].strip()


# for debugging, allow this file to be run standalone to test the LLM connection
# usage: python ai_agent.py "Who are you?"
if __name__ == "__main__":
    print(ask_llm(" ".join(sys.argv[1:])))
