#!/usr/bin/env python3
"""Generate 5 identical 50ms 880 Hz 16-bit mono PCM WAV files.

These are placeholder sound assets for Bellbird's notification system.
All 5 files are identical — a short beep that confirms sound playback
works. Users on Windows can replace individual files with custom sounds.

Uses only the Python stdlib (``wave``, ``struct``, ``math``, ``array``).
Re-runnable: existing files are overwritten silently.

Output directory: ``bellbird/data/sounds/default/``
"""

import math
import sys
from pathlib import Path

# ─── WAV parameters ──────────────────────────────────────────────────────────

SAMPLE_RATE = 22050  # 22.05 kHz (good enough for a beep)
DURATION_SEC = 0.050  # 50 ms
FREQUENCY = 880  # Hz (A5 — a crisp beep)
AMPLITUDE = 0.85  # 16-bit range: 0..65535, so 0.85 * 32767

EVENTS = [
    "generation_complete",
    "server_ready",
    "error",
    "tool_request",
    "model_loaded",
]

# ─── Output directory ────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "bellbird" / "data" / "sounds" / "default"


def _generate_wav_data() -> bytes:
    """Generate 50 ms of 880 Hz 16-bit signed mono PCM audio as raw bytes.

    Returns:
        Raw PCM sample data ready for a WAV file body.
    """
    import array

    num_samples = int(SAMPLE_RATE * DURATION_SEC)
    samples = array.array("h")  # signed 16-bit

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        # Sine wave
        value = int(AMPLITUDE * 32767 * math.sin(2 * math.pi * FREQUENCY * t))
        samples.append(value)

    return samples.tobytes()


def write_wav(path: Path, pcm_data: bytes) -> None:
    """Write a WAV file with the given PCM data.

    Args:
        path: Destination path.
        pcm_data: Raw 16-bit signed mono PCM bytes.
    """
    import struct
    import wave

    num_samples = len(pcm_data) // 2  # 16-bit = 2 bytes per sample
    data_size = len(pcm_data)
    fmt_size = 16
    audio_format = 1  # PCM
    num_channels = 1  # mono
    byte_rate = SAMPLE_RATE * num_channels * 2  # 16-bit = 2 bytes
    block_align = num_channels * 2

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)


def main() -> None:
    """Generate all 5 WAV files. Overwrites existing files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pcm_data = _generate_wav_data()

    for event in EVENTS:
        path = OUTPUT_DIR / f"{event}.wav"
        write_wav(path, pcm_data)
        size = path.stat().st_size
        print(f"  Created: {path.relative_to(OUTPUT_DIR.parent.parent.parent)} ({size} bytes)")

    print(f"\nDone — {len(EVENTS)} files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
