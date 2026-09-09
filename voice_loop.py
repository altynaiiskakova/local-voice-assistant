import array
import asyncio
import os
import sys

from dotenv import load_dotenv
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.wake import Detect, Detection

from assistant import ask_and_speak

load_dotenv()


# audio parameters
MIC_DEVICE = os.environ["AUDIO_DEVICE"]
RATE, WIDTH, CHANNELS = 16000, 2, 1
SAMPLES_PER_CHUNK = 1280  # 80ms of audio at 16kHz
BYTES_PER_CHUNK = SAMPLES_PER_CHUNK * WIDTH * CHANNELS

# services
WAKE_WORD_URI = os.environ["WAKE_WORD_URI"]
WHISPER_URI = os.environ["WHISPER_URI"]

OPEN_WAKE_WORD = os.environ["OPEN_WAKE_WORD"]
CLOSE_WAKE_WORD = os.environ["CLOSE_WAKE_WORD"]

# end-of-speech detection: whichever comes first ends the turn
# close wake word firing, or END_SILENCE_SECONDS of trailing silence.
SILENCE_RMS_THRESHOLD = 500  # per-chunk RMS at or below this counts as silence
END_SILENCE_SECONDS = 3.0  # stop capturing after this much trailing silence
CHUNK_SECONDS = SAMPLES_PER_CHUNK / RATE
END_SILENCE_CHUNKS = round(END_SILENCE_SECONDS / CHUNK_SECONDS)

# limits
MAX_UTTERANCE_SECONDS = 60  # safety net if the user never stops
MAX_UTTERANCE_BYTES = MAX_UTTERANCE_SECONDS * RATE * WIDTH * CHANNELS

# tail trimming
WAKE_TAIL_SECONDS = 1.2  # drop the closing wake word itself
WAKE_TAIL_BYTES = int(WAKE_TAIL_SECONDS * RATE) * WIDTH * CHANNELS
PAUSE_TAIL_SECONDS = END_SILENCE_SECONDS - 0.5  # drop most of the trailing pause
PAUSE_TAIL_BYTES = int(PAUSE_TAIL_SECONDS * RATE) * WIDTH * CHANNELS


async def start_mic() -> asyncio.subprocess.Process:
    """Open arecord as a raw PCM stream on stdout (no -d, runs until killed)."""
    print("[start_mic]: opening arecord...")
    return await asyncio.create_subprocess_exec(
        "arecord",
        "-D",
        MIC_DEVICE,
        "-f",
        "S16_LE",
        "-c",
        str(CHANNELS),
        "-r",
        str(RATE),
        "-t",
        "raw",
        "-q",
        stdout=asyncio.subprocess.PIPE,
    )


async def _wake_word_detection(tcp_wake_client: AsyncTcpClient):
    """Read events until a Detection arrives (or the peer hangs up)."""
    while True:
        event = await tcp_wake_client.read_event()
        if event is None:
            return None
        if Detection.is_type(event.type):
            return Detection.from_event(event)


async def listen_for_open_wake_word(local_mic, wake_word: str) -> None:
    """Pump mic audio into openWakeWord until `wake_word` fires. Audio is discarded."""
    print("Stream mic to openwakeword until it detects the wake word.")

    async with AsyncTcpClient.from_uri(WAKE_WORD_URI) as tcp_open_wake_client:
        await tcp_open_wake_client.write_event(Detect(names=[wake_word]).event())

        await tcp_open_wake_client.write_event(
            AudioStart(rate=RATE, width=WIDTH, channels=CHANNELS).event()
        )

        detect_task = asyncio.create_task(_wake_word_detection(tcp_open_wake_client))

        try:
            while not detect_task.done():
                chunk = await local_mic.stdout.readexactly(BYTES_PER_CHUNK)
                await tcp_open_wake_client.write_event(
                    AudioChunk(rate=RATE, width=WIDTH, channels=CHANNELS, audio=chunk).event()
                )

            detection = detect_task.result()
            if detection is None:
                raise RuntimeError("wake service closed the connection")

            print(f"Detected: {detection.name}")
        finally:
            detect_task.cancel()
            try:
                await tcp_open_wake_client.write_event(AudioStop().event())
            except OSError as e:
                print(f"[voice_loop] AudioStop failed: {e}", file=sys.stderr)


def _chunk_rms(chunk: bytes) -> float:
    """Root-mean-square amplitude of a 16-bit little-endian PCM chunk."""
    samples = array.array("h")
    samples.frombytes(chunk)
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5


async def capture_audio(local_mic) -> bytes:
    """
    Buffer mic audio until the user finishes and return it trimmed.

    The turn ends on whichever comes first: the closing wake word or trailing silence.
    Trailing silence only starts counting once speech has been heard.
    The tail (pause) is chopped off the returned audio so whisper doesn't transcribe it.
    """
    print(
        f"Capture until '{CLOSE_WAKE_WORD.replace('_', ' ')}' or a {END_SILENCE_SECONDS:g}s pause."
    )

    audio_buffer = bytearray()
    speech_started = False
    silent_chunks = 0

    async with AsyncTcpClient.from_uri(WAKE_WORD_URI) as tcp_close_wake_client:
        await tcp_close_wake_client.write_event(Detect(names=[CLOSE_WAKE_WORD]).event())
        await tcp_close_wake_client.write_event(
            AudioStart(rate=RATE, width=WIDTH, channels=CHANNELS).event()
        )
        detect_task = asyncio.create_task(_wake_word_detection(tcp_close_wake_client))

        try:
            while True:
                chunk = await local_mic.stdout.readexactly(BYTES_PER_CHUNK)
                audio_buffer.extend(chunk)
                await tcp_close_wake_client.write_event(
                    AudioChunk(rate=RATE, width=WIDTH, channels=CHANNELS, audio=chunk).event()
                )

                # Check for end of speech conditions: close wake word
                if detect_task.done():
                    detection = detect_task.result()
                    if detection is None:
                        raise RuntimeError("wake service closed the connection")
                    print(f"Detected: {detection.name}")
                    return _trim_tail(audio_buffer, WAKE_TAIL_BYTES)

                # Check for end of speech conditions: trailing silence
                if _chunk_rms(chunk) > SILENCE_RMS_THRESHOLD:
                    speech_started = True
                    silent_chunks = 0
                elif speech_started:
                    silent_chunks += 1
                    if silent_chunks >= END_SILENCE_CHUNKS:
                        print("Detected pause, wrapping up.")
                        return _trim_tail(audio_buffer, PAUSE_TAIL_BYTES)

                # Check for end of speech conditions: max time reached
                if len(audio_buffer) >= MAX_UTTERANCE_BYTES:
                    print("Max utterance length reached, cutting off.")
                    return bytes(audio_buffer)
        finally:
            detect_task.cancel()
            try:
                await tcp_close_wake_client.write_event(AudioStop().event())
            except OSError as e:
                print(f"Error occurred while writing AudioStop event: {e}")


def _trim_tail(buffer: bytearray, tail_bytes: int) -> bytes:
    """Drop the last `tail_bytes`."""
    return bytes(buffer[:-tail_bytes]) if len(buffer) > tail_bytes else b""


async def transcribe(audio: bytes) -> str:
    """Send buffered PCM to wyoming-whisper, return the transcript."""
    if not audio:
        return ""

    async with AsyncTcpClient.from_uri(WHISPER_URI) as tcp_whisper_client:
        await tcp_whisper_client.write_event(Transcribe(language="en").event())
        await tcp_whisper_client.write_event(
            AudioStart(rate=RATE, width=WIDTH, channels=CHANNELS).event()
        )
        # send audio in chunks to whisper service
        for i in range(0, len(audio), BYTES_PER_CHUNK):
            chunk = audio[i : i + BYTES_PER_CHUNK]
            await tcp_whisper_client.write_event(
                AudioChunk(rate=RATE, width=WIDTH, channels=CHANNELS, audio=chunk).event()
            )
        # signal end of audio stream
        await tcp_whisper_client.write_event(AudioStop().event())

        # wait for the whisper service to return a transcript
        while True:
            event = await tcp_whisper_client.read_event()
            if event is None:
                return ""
            if Transcript.is_type(event.type):
                return Transcript.from_event(event).text


async def capture_and_transcribe_user_speech() -> str:
    """
    Open mic, wait for wake word, capture speech until a pause, close mic and return the transcript.
    Blocks until the wake word fires.
    The mic is opened for the duration of the turn and closed before returning,
    so the assistant can't hear its own TTS.
    """
    local_mic = await start_mic()
    try:
        await listen_for_open_wake_word(local_mic, OPEN_WAKE_WORD)
        user_audio = await capture_audio(local_mic)
    finally:
        local_mic.terminate()
        await local_mic.wait()

    transcript = (await transcribe(user_audio)).strip()
    return transcript


async def main():
    """Run the voice assistant loop forever."""
    print("Voice assistant running.")
    while True:
        try:
            transribed_user_audio = await capture_and_transcribe_user_speech()
        except asyncio.IncompleteReadError as e:
            print(f"Error during capture_and_transcribe_user_speech: {e}")
            continue
        if not transribed_user_audio:
            print("No speech recognized.")
            continue

        print(f"User said: {transribed_user_audio}")
        # Mic is already closed here, so the assistant can't hear its own TTS.
        ask_and_speak(transribed_user_audio)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting.")
