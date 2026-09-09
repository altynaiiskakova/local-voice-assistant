# local-voice-assistant

A local, LLM-powered voice assistant. You speak a wake word, ask a question, and
it answers out loud, running a local SLM (via [Ollama](https://ollama.com/))
as the brain, with local speech-to-text and text-to-speech. It can pull in your
calendar and the weather as context when the question calls for it.

## How it works

```
mic ──▶ openWakeWord ──▶ Whisper (STT) ──▶ prompt builder ──▶ Ollama (LLM) ──▶ Piper (TTS) ──▶ speaker
```

| Stage | Component | Runs |
|-------|-----------|------|
| Wake word | [openWakeWord](https://github.com/dscripka/openWakeWord) via Wyoming | local (Docker) |
| STT | [Whisper](https://github.com/rhasspy/wyoming-faster-whisper) via Wyoming | local (Docker) |
| Language model | [Ollama](https://ollama.com/) (`gemma2:2b` by default) | local |
| TTS | [Piper](https://github.com/rhasspy/piper) | local |
| Calendar context | CalDAV (e.g. Nextcloud) | network - your server |
| Weather context | [wttr.in](https://wttr.in) | network - external |

The voice pipeline is fully local. The two context lookups are optional and only
run when the question mentions a calendar event or the weather.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com/) running locally with a model pulled (`ollama pull gemma2:2b`)
- [Piper](https://github.com/rhasspy/piper) binary and a voice model
- `sox`, `alsa-utils` (`arecord` / `aplay`)
- Docker (for the wake-word and Whisper services)
- A microphone and speaker

## Setup

```bash
git clone <this-repo>

cd local-voice-assistant

cp .env.example .env   # then set the values

docker compose up -d   # starts openWakeWord + Whisper services
```

## Usage

Run the voice loop:

```bash
uv sync
uv run voice_loop.py
```
Say the open wake word, ask your question, then either say the close wake word or just pause.
