#!/usr/bin/env python3
"""Synthesize Bellbird's "default" sound theme — 16 distinct event cues.

Each event gets its OWN timbre, pitch contour and duration (≈80 ms–800 ms)
so a blind user can tell events apart by ear alone. Sounds use a smooth
attack/decay envelope (no hard edges → no clicks, unlike the old 50 ms raw
beep) and a little harmonic content for a warmer, less "PC-speaker" tone.

Stdlib only (``wave``, ``array``, ``math``). Re-runnable: overwrites files.

Output: ``bellbird/data/sounds/default/<event>.wav`` (44.1 kHz, 16-bit mono).
Run after install (the ``bellbird/data`` tree is gitignored / runtime-only):

    uv run python scripts/generate_sound_assets.py
"""

import array
import math
import wave
from pathlib import Path

SAMPLE_RATE = 44100
AMPLITUDE = 0.62  # headroom so summed harmonics never clip

OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "bellbird" / "data" / "sounds" / "default"
)

# Note name → frequency (Hz), a small equal-tempered palette.
_NOTES = {
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99,
    "A5": 880.00, "B5": 987.77, "C6": 1046.50, "E6": 1318.51, "G6": 1567.98,
    "C4": 261.63, "E4": 329.63, "G4": 392.00, "A4": 440.00, "A3": 220.00,
    "E3": 164.81, "C3": 130.81,
}


def _env(i: int, n: int, attack: float = 0.012, release: float = 0.06) -> float:
    """Attack/sustain/release amplitude envelope in [0, 1] for sample i of n."""
    t = i / SAMPLE_RATE
    total = n / SAMPLE_RATE
    if t < attack:
        return t / attack
    if t > total - release:
        return max(0.0, (total - t) / release)
    return 1.0


def _tone(freq: float, dur: float, harmonics=(1.0, 0.28, 0.12),
          attack: float = 0.012, release: float = 0.06) -> array.array:
    """One note: fundamental + a couple of decaying harmonics, enveloped."""
    n = int(SAMPLE_RATE * dur)
    out = array.array("h")
    norm = sum(harmonics)
    for i in range(n):
        t = i / SAMPLE_RATE
        s = 0.0
        for k, amp in enumerate(harmonics, start=1):
            s += amp * math.sin(2 * math.pi * freq * k * t)
        s = (s / norm) * _env(i, n, attack, release) * AMPLITUDE
        out.append(int(max(-1.0, min(1.0, s)) * 32767))
    return out


def _seq(notes, dur: float, gap: float = 0.0, **kw) -> array.array:
    """A melody: each note played for ``dur`` seconds, optional silent gap."""
    out = array.array("h")
    for name in notes:
        out.extend(_tone(_NOTES[name], dur, **kw))
        if gap:
            out.extend(array.array("h", [0] * int(SAMPLE_RATE * gap)))
    return out


def _chord(notes, dur: float, **kw) -> array.array:
    """Several notes sounded together (summed, then normalised)."""
    layers = [_tone(_NOTES[n], dur, **kw) for n in notes]
    length = max(len(l) for l in layers)
    mixed = array.array("h", [0] * length)
    for i in range(length):
        acc = sum(l[i] for l in layers if i < len(l))
        mixed[i] = int(max(-32767, min(32767, acc / len(layers))))
    return mixed


def _connecting_loop(dur: float = 4.0) -> array.array:
    """Warm, deep arpeggiated major chord that loops seamlessly.

    A whole-buffer raised-cosine "swell" brings the amplitude to exactly zero
    at both ends, so when winsound loops it back-to-back there is no click and
    it "breathes" gently — a calm cue that the server is still connecting.
    Notes enter staggered (arpeggio) over the first half, then sustain.
    """
    n = int(SAMPLE_RATE * dur)
    # A-major voiced low for warmth: A2, E3, A3, C#4, E4.
    chord = [110.0, 164.81, 220.0, 277.18, 329.63]
    out = array.array("h")
    for i in range(n):
        t = i / SAMPLE_RATE
        swell = 0.5 - 0.5 * math.cos(2 * math.pi * (i / n))  # 0→1→0 over the loop
        s = 0.0
        for j, f in enumerate(chord):
            start = (j / len(chord)) * (dur * 0.5)  # staggered arpeggio entry
            if t < start:
                continue
            note_env = min(1.0, (t - start) / 0.45)
            s += note_env * (
                math.sin(2 * math.pi * f * t)
                + 0.40 * math.sin(2 * math.pi * 2 * f * t)
                + 0.15 * math.sin(2 * math.pi * 3 * f * t)
            )
        s = (s / len(chord)) * swell * AMPLITUDE * 0.55
        out.append(int(max(-1.0, min(1.0, s)) * 32767))
    return out


def _success() -> array.array:
    """Satisfying "connected" cue: quick rising arpeggio into a ringing chord."""
    out = array.array("h")
    out.extend(_seq(["C5", "E5", "G5"], 0.10))
    out.extend(_chord(["C5", "E5", "G5", "C6"], 0.50, attack=0.008, release=0.30))
    return out


# event name → builder. Distinct contour + duration per event.
def _build() -> dict[str, array.array]:
    return {
        # ── Server / model lifecycle ──────────────────────────────────
        "connecting":           _connecting_loop(4.0),                   # warm loop while loading
        "server_ready":         _success(),                              # rich "connected!" cue
        "server_stopped":       _seq(["G5", "E5", "C5"], 0.13),          # falling, settled
        "model_loaded":         _success(),                              # same satisfying resolve
        "model_loading":        _tone(_NOTES["A4"], 0.18, attack=0.03),  # soft single tone
        # ── Generation flow ───────────────────────────────────────────
        "message_sent":         _tone(_NOTES["G5"], 0.075, harmonics=(1.0,), release=0.04),  # crisp blip
        "generation_started":   _tone(_NOTES["E5"], 0.10),
        "generation_complete":  _seq(["E5", "A5"], 0.13),                # two-note "ta-da"
        "message_received":     _tone(_NOTES["C6"], 0.10, harmonics=(1.0, 0.2)),
        # ── Tools / permission ────────────────────────────────────────
        "tool_request":         _seq(["A5", "A5"], 0.09, gap=0.05),      # attention double-blip
        "tool_blocked":         _tone(_NOTES["E3"], 0.28, harmonics=(1.0, 0.5, 0.3)),  # low thud
        "tool_denied":          _seq(["A4", "E4"], 0.12),                # short descending
        # ── Alerts ────────────────────────────────────────────────────
        "error":                _seq(["E4", "C4"], 0.20, harmonics=(1.0, 0.6, 0.4)),   # somber low
        "warning":              _seq(["A5", "F5"], 0.14),
        # ── Editing / navigation cues ─────────────────────────────────
        "new_conversation":     _chord(["C5", "G5"], 0.22),              # open, neutral
        "copy":                 _tone(_NOTES["C6"], 0.07, harmonics=(1.0,), release=0.03),  # tiny tick
        "attach":               _seq(["E5", "B5"], 0.08),                # soft pop up
    }


def write_wav(path: Path, samples: array.array) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(samples.tobytes())


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events = _build()
    for event, samples in events.items():
        path = OUTPUT_DIR / f"{event}.wav"
        write_wav(path, samples)
        ms = int(len(samples) / SAMPLE_RATE * 1000)
        print(f"  Created: {event}.wav ({ms} ms, {path.stat().st_size} bytes)")
    print(f"\nDone — {len(events)} sounds in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
