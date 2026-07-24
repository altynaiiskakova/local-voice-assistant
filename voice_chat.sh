#!/bin/bash

echo "Recording for 5 seconds... speak now."
arecord -D plughw:1,0 -f S16_LE -c 1 -r 16000 -d 5 /tmp/input.wav

echo "Transcribing..."
TEXT=$(~/whisper.cpp/build/bin/whisper-cli -m ~/whisper.cpp/models/ggml-base.en.bin -f /tmp/input.wav --no-timestamps 2>/dev/null | tail -n 1)

echo "You said: $TEXT"
echo "Asking Qwen..."

RESPONSE=$(~/nextcloud-agent/venv/bin/python ~/nextcloud-agent/calendar_agent.py "$TEXT")
if [ -z "$RESPONSE" ]; then
    RESPONSE="Sorry, something went wrong fetching the answer."
fi
echo "Qwen says: $RESPONSE"
echo "Speaking response..."
echo "$RESPONSE" | ~/piper/piper/piper --model ~/piper/en_US-lessac-medium.onnx --output_file /tmp/output.wav
sox /tmp/output.wav /tmp/output_padded.wav pad 1 0
sox /tmp/output_padded.wav /tmp/output_stereo.wav channels 2
aplay -D plughw:1,0 /tmp/output_stereo.wav
