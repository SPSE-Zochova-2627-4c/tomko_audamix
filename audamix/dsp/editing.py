"""Sample-level editing helpers: cut, insert, silence, fades, generators, statistics.

All functions are pure: they take and return NumPy arrays shaped ``(frames,)`` for
mono or ``(frames, channels)`` for multichannel audio and never modify the input.
"""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy import signal


def to_index(seconds: float, sample_rate: int, frames: int) -> int:
    """Convert a time in seconds to a sample index clamped to ``[0, frames]``."""
    return max(0, min(frames, int(round(seconds * sample_rate))))


def delete_range(samples: np.ndarray, start: int, end: int) -> np.ndarray:
    if end <= start:
        return samples.copy()
    return np.concatenate((samples[:start], samples[end:]), axis=0)


def keep_range(samples: np.ndarray, start: int, end: int) -> np.ndarray:
    return samples[start:end].copy()


def insert_clip(samples: np.ndarray, at: int, clip: np.ndarray) -> np.ndarray:
    return np.concatenate((samples[:at], clip, samples[at:]), axis=0)


def silence_range(samples: np.ndarray, start: int, end: int) -> np.ndarray:
    result = samples.copy()
    result[start:end] = 0.0
    return result


def fade_range(samples: np.ndarray, start: int, end: int, direction: str) -> np.ndarray:
    """Apply a linear fade over ``[start, end)``; ``direction`` is ``in`` or ``out``."""
    if direction not in {"in", "out"}:
        raise ValueError("Fade direction must be 'in' or 'out'")
    length = end - start
    if length < 2:
        raise ValueError("Select a region of at least two samples to fade")
    ramp = np.linspace(0.0, 1.0, length)
    if direction == "out":
        ramp = ramp[::-1]
    result = np.array(samples, dtype=np.float64, copy=True)
    shape = (length,) + (1,) * (result.ndim - 1)
    result[start:end] *= ramp.reshape(shape)
    return result


def smooth_join(samples: np.ndarray, index: int, sample_rate: int, milliseconds: float = 3.0) -> np.ndarray:
    """Remove the click at an edit point by dipping the signal to zero across ``index``.

    Splicing (delete, paste) or zeroing (silence) leaves a sudden step in the waveform at the
    seam, which is heard as a click. The samples just before ``index`` ramp down to zero and
    the samples from ``index`` on ramp up from zero, so the seam is continuous. The length is
    unchanged and only ``milliseconds`` of audio on each side is touched.
    """
    frames = samples.shape[0]
    ramp = max(2, round(sample_rate * milliseconds / 1000))
    before, after = min(ramp, index), min(ramp, frames - index)
    if before < 2 and after < 2:
        return samples.copy()
    result = np.array(samples, dtype=np.float64, copy=True)
    shape = (-1,) + (1,) * (result.ndim - 1)
    if before >= 2:
        result[index - before:index] *= np.linspace(1.0, 0.0, before).reshape(shape)
    if after >= 2:
        result[index:index + after] *= np.linspace(0.0, 1.0, after).reshape(shape)
    return result


def match_clip(clip: np.ndarray, clip_rate: int, rate: int, channels: int) -> np.ndarray:
    """Convert a clip to the target sample rate and channel count."""
    result = np.asarray(clip, dtype=np.float64)
    if clip_rate != rate:
        divisor = gcd(clip_rate, rate)
        result = signal.resample_poly(result, rate // divisor, clip_rate // divisor, axis=0)
    source_channels = 1 if result.ndim == 1 else result.shape[1]
    if source_channels != channels:
        if channels == 1:
            result = result.mean(axis=1) if result.ndim == 2 else result
        else:
            column = result if result.ndim == 1 else result.mean(axis=1)
            result = np.repeat(column[:, None], channels, axis=1)
    return np.clip(result, -1.0, 1.0) if np.max(np.abs(result), initial=0.0) > 1.0 else result


def generate(kind: str, sample_rate: int, channels: int, duration: float,
             frequency: float = 440.0, amplitude: float = 0.5) -> np.ndarray:
    """Create a sine tone, silence, or white noise."""
    if kind not in {"tone", "silence", "noise"}:
        raise ValueError(f"Unknown generator: {kind}")
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be positive")
    if not np.isfinite(amplitude) or not 0 < amplitude <= 1:
        raise ValueError("Amplitude must be between 0 and 1")
    frames = int(round(duration * sample_rate))
    if frames < 1:
        raise ValueError("Duration is too short")
    if kind == "silence":
        data = np.zeros(frames)
    elif kind == "tone":
        if not np.isfinite(frequency) or not 0 < frequency < sample_rate / 2:
            raise ValueError(f"Frequency must be between 0 and {sample_rate / 2:g} Hz")
        data = amplitude * np.sin(2 * np.pi * frequency * np.arange(frames) / sample_rate)
    else:
        data = amplitude * np.random.default_rng().uniform(-1.0, 1.0, frames)
    return data if channels == 1 else np.repeat(data[:, None], channels, axis=1)


def analyze(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    """Return basic level statistics and the dominant frequency."""
    data = np.asarray(samples, dtype=np.float64)
    if not data.size:
        raise ValueError("Nothing to analyze")
    peak = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(np.square(data))))

    def db(value: float) -> float:
        return float(20 * np.log10(value)) if value > 0 else float("-inf")

    mono = data if data.ndim == 1 else data.mean(axis=1)
    dominant = 0.0
    if mono.size >= 2:
        spectrum = np.abs(np.fft.rfft(mono * np.hanning(mono.size)))
        spectrum[0] = 0.0
        dominant = float(np.argmax(spectrum) * sample_rate / mono.size)
    return {
        "duration": data.shape[0] / sample_rate,
        "peak": peak, "peak_db": db(peak),
        "rms": rms, "rms_db": db(rms),
        "crest_db": db(peak) - db(rms) if rms > 0 else 0.0,
        "dc_offset": float(np.mean(data)),
        "clipped_samples": float(np.count_nonzero(np.abs(data) >= 0.999)),
        "dominant_hz": dominant,
    }


def spectrogram_image(samples: np.ndarray, sample_rate: int, columns: int = 1500,
                      window: int = 1024, floor_db: float = 90.0) -> np.ndarray:
    """Magnitude spectrogram scaled to ``uint8`` with shape ``(bins, columns)``.

    Row 0 is the highest frequency so the array can be shown as an image directly.
    """
    del sample_rate  # the axes are linear; the rate only matters for labelling
    data = np.asarray(samples, dtype=np.float64)
    mono = data if data.ndim == 1 else data.mean(axis=1)
    if mono.size < window:
        mono = np.pad(mono, (0, window - mono.size))
    columns = max(1, min(columns, mono.size - window + 1))
    starts = np.linspace(0, mono.size - window, columns).astype(np.int64)
    taper = np.hanning(window)
    image = np.empty((window // 2 + 1, columns), dtype=np.float64)
    for index in range(0, columns, 256):
        chunk = starts[index:index + 256]
        frames = mono[chunk[:, None] + np.arange(window)] * taper
        image[:, index:index + 256] = np.abs(np.fft.rfft(frames, axis=1)).T
    decibels = 20 * np.log10(image / (window / 4) + 1e-9)
    scaled = np.clip((decibels + floor_db) / floor_db, 0.0, 1.0)
    return np.ascontiguousarray((scaled[::-1] * 255).astype(np.uint8))
