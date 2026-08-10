"""Built-in alarm ringtones (generated WAV, no external assets required).
All sounds are mathematically generated — zero copyright issues.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


RINGTONES = [
    ("beep",      "经典哔哔"),
    ("chime",     "清脆钟声"),
    ("urgent",    "急促提醒"),
    ("soft",      "柔和提示"),
    ("digital",   "电子音"),
    ("piano",     "钢琴叮咚"),
    ("xylophone", "木琴轻快"),
    ("bell",      "圆润铃声"),
    ("morning",   "晨间悠扬"),
    ("notify",    "轻柔通知"),
    ("alarm2",    "双音警报"),
    ("zen",       "禅意钟"),
]


def sounds_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent / "assets" / "sounds"
    else:
        base = Path(__file__).resolve().parent / "assets" / "sounds"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _write_wav(path: Path, samples: list[float], rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for s in samples:
            v = max(-1.0, min(1.0, s))
            w.writeframes(struct.pack("<h", int(v * 30000)))


def _tone(freq: float, dur: float, rate: int = 22050, vol: float = 0.5,
          attack: float = 0.02, decay: float = 0.08) -> list[float]:
    """Sine wave tone with attack/decay envelope."""
    n = int(rate * dur)
    out = []
    for i in range(n):
        t = i / rate
        env = min(1.0, t / attack) * min(1.0, (dur - t) / decay)
        out.append(math.sin(2 * math.pi * freq * t) * vol * env)
    return out


def _overtone(freq: float, dur: float, rate: int = 22050, vol: float = 0.5) -> list[float]:
    """Richer tone with harmonics — piano-like."""
    n = int(rate * dur)
    out = []
    for i in range(n):
        t = i / rate
        # Exponential decay envelope
        env = math.exp(-3.5 * t / dur)
        s = (
            math.sin(2 * math.pi * freq * t) * 0.6
            + math.sin(2 * math.pi * freq * 2 * t) * 0.2
            + math.sin(2 * math.pi * freq * 3 * t) * 0.1
            + math.sin(2 * math.pi * freq * 4 * t) * 0.05
        )
        out.append(s * vol * env)
    return out


def _silence(ms: int, rate: int = 22050) -> list[float]:
    return [0.0] * int(rate * ms / 1000)


def ensure_ringtones() -> dict[str, Path]:
    """Generate all ringtones if missing. Returns id -> path."""
    d = sounds_dir()
    paths: dict[str, Path] = {}
    specs = {
        # Original 5
        "beep": lambda: (
            _tone(880, 0.18) + _silence(90) + _tone(880, 0.18) + _silence(90) + _tone(880, 0.28)
        ),
        "chime": lambda: (
            _tone(523, 0.25, vol=0.45) + _tone(659, 0.25, vol=0.4)
            + _tone(784, 0.35, vol=0.35) + _tone(1046, 0.55, vol=0.3)
        ),
        "urgent": lambda: sum(
            (_tone(1200, 0.1, vol=0.55) + _silence(80) for _ in range(5)), []
        ),
        "soft": lambda: (
            _tone(440, 0.4, vol=0.25) + _tone(554, 0.5, vol=0.2) + _tone(659, 0.65, vol=0.18)
        ),
        "digital": lambda: sum(
            (_tone(f, 0.12, vol=0.4) + _silence(60) for f in (600, 800, 1000, 800, 600)), []
        ),

        # New pleasant ringtones
        "piano": lambda: (
            # C-E-G-C arpeggio with rich harmonics
            _overtone(261.6, 0.5, vol=0.45) + _silence(30)
            + _overtone(329.6, 0.5, vol=0.45) + _silence(30)
            + _overtone(392.0, 0.5, vol=0.45) + _silence(30)
            + _overtone(523.3, 0.8, vol=0.5)
        ),
        "xylophone": lambda: (
            # Pentatonic scale, bright and cheerful
            _overtone(783.99, 0.22, vol=0.5) + _silence(25)
            + _overtone(698.46, 0.22, vol=0.5) + _silence(25)
            + _overtone(587.33, 0.22, vol=0.5) + _silence(25)
            + _overtone(523.25, 0.22, vol=0.5) + _silence(25)
            + _overtone(392.00, 0.22, vol=0.5) + _silence(25)
            + _overtone(523.25, 0.45, vol=0.5)
        ),
        "bell": lambda: (
            # Deep resonant bell with long decay
            _overtone(440, 1.2, vol=0.55) + _silence(80)
            + _overtone(554, 1.2, vol=0.45) + _silence(80)
            + _overtone(659, 1.5, vol=0.4)
        ),
        "morning": lambda: (
            # Gentle ascending melody — G A B D E
            _tone(392.0, 0.3, vol=0.3, decay=0.15) + _silence(40)
            + _tone(440.0, 0.3, vol=0.3, decay=0.15) + _silence(40)
            + _tone(493.9, 0.3, vol=0.32, decay=0.15) + _silence(40)
            + _tone(587.3, 0.35, vol=0.33, decay=0.2) + _silence(40)
            + _tone(659.3, 0.6, vol=0.35, decay=0.25)
        ),
        "notify": lambda: (
            # Two soft chimes — like iPhone notification
            _overtone(1174.66, 0.15, vol=0.38) + _silence(60)
            + _overtone(987.77, 0.35, vol=0.35)
        ),
        "alarm2": lambda: sum(
            (
                _tone(880, 0.15, vol=0.5) + _tone(1100, 0.15, vol=0.5) + _silence(60)
                for _ in range(4)
            ), []
        ),
        "zen": lambda: (
            # Deep temple bell — 432 Hz
            _overtone(432, 0.8, vol=0.4) + _silence(200)
            + _overtone(288, 0.8, vol=0.3) + _silence(200)
            + _overtone(216, 1.2, vol=0.25)
        ),
    }
    for rid, gen in specs.items():
        p = d / f"{rid}.wav"
        if not p.exists() or p.stat().st_size < 100:
            _write_wav(p, gen())
        paths[rid] = p
    return paths


def play_ringtone(ringtone_id: str = "beep", *, async_play: bool = True, loop: bool = False) -> None:
    paths = ensure_ringtones()
    path = paths.get(ringtone_id) or paths.get("beep")
    if path is None or not path.exists():
        return
    try:
        import winsound
        flags = winsound.SND_FILENAME
        if async_play or loop:
            flags |= winsound.SND_ASYNC
        if loop:
            flags |= winsound.SND_LOOP
        winsound.PlaySound(str(path), flags)
    except Exception as exc:
        try:
            import sys as _sys
            if _sys.stderr:
                _sys.stderr.write(f"ringtone play failed: {exc}\n")
        except Exception:
            pass


def stop_ringtone() -> None:
    try:
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
