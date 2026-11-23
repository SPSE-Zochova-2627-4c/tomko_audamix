"""Audacity-style effects that keep the length of the audio unchanged.

Every effect is a pure function ``f(samples, sample_rate, **parameters) -> samples`` on arrays
shaped ``(frames,)`` or ``(frames, channels)``. :data:`SPECS` describes each effect (title,
menu group, parameters with ranges/defaults) so a UI can build its menus and dialogs from it,
and :func:`apply_effect` validates parameters and runs one effect by name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    default: float
    minimum: float
    maximum: float
    decimals: int = 1
    suffix: str = ""
    kind: str = "float"  # "float" or "bool" (stored as 0.0 / 1.0)


@dataclass(frozen=True)
class EffectSpec:
    title: str
    group: str
    params: tuple[Param, ...]
    func: Callable[..., np.ndarray]


def _as2d(samples: np.ndarray) -> tuple[np.ndarray, Callable[[np.ndarray], np.ndarray]]:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        return data[:, None], lambda out: out[:, 0]
    return data, lambda out: out


def _check_frequency(frequency: float, rate: int) -> None:
    if not 0 < frequency < rate / 2:
        raise ValueError(f"Frequency must be between 0 and {rate / 2:g} Hz")


def _db(value: float) -> float:
    return 10 ** (value / 20)


def _level(data: np.ndarray) -> np.ndarray:
    """Linked (loudest-channel) absolute level of every frame."""
    return np.max(np.abs(data), axis=1)


def _smooth(values: np.ndarray, rate: int, milliseconds: float) -> np.ndarray:
    """One-pole low-pass of a control signal, starting from its first value."""
    if milliseconds <= 0 or not values.size:
        return values
    pole = float(np.exp(-1.0 / (milliseconds / 1000 * rate)))
    b, a = [1 - pole], [1.0, -pole]
    out, _ = signal.lfilter(b, a, values, zi=signal.lfilter_zi(b, a) * values[0])
    return out


def _samples(rate: int, milliseconds: float) -> int:
    return max(1, round(rate * milliseconds / 1000))


# --- level -----------------------------------------------------------------------------------

def normalize(samples: np.ndarray, rate: int, target_db: float = -1.0,
              remove_dc: float = 1.0) -> np.ndarray:
    del rate
    data, restore = _as2d(samples)
    if remove_dc:
        data = data - np.mean(data, axis=0, keepdims=True)
    peak = float(np.max(np.abs(data), initial=0.0))
    if peak <= 1e-12:
        return restore(data)
    return restore(data * (_db(target_db) / peak))  # one gain for all channels keeps the balance


def compressor(samples: np.ndarray, rate: int, threshold_db: float = -18.0, ratio: float = 2.0,
               attack_ms: float = 10.0, release_ms: float = 100.0, makeup_db: float = 0.0) -> np.ndarray:
    data, restore = _as2d(samples)
    level_db = 20 * np.log10(np.maximum(_level(data), 1e-9))
    reduction = -np.maximum(level_db - threshold_db, 0.0) * (1 - 1 / ratio)  # dB, never positive
    # Look ahead by the attack time (running minimum), then ease the gain back up over the release.
    reduction = _smooth(minimum_filter1d(reduction, _samples(rate, attack_ms)), rate, release_ms / 4)
    return restore(data * (10 ** ((reduction + makeup_db) / 20))[:, None])


def limiter(samples: np.ndarray, rate: int, limit_db: float = -1.0, release_ms: float = 50.0) -> np.ndarray:
    data, restore = _as2d(samples)
    limit = _db(limit_db)
    needed = np.minimum(1.0, limit / np.maximum(_level(data), 1e-9))
    anticipated = minimum_filter1d(needed, _samples(rate, 5.0))  # 5 ms look-ahead
    gain = np.minimum(anticipated, _smooth(anticipated, rate, release_ms / 4))
    return restore(np.clip(data * gain[:, None], -limit, limit))


def noise_gate(samples: np.ndarray, rate: int, threshold_db: float = -40.0, release_ms: float = 100.0,
               floor_db: float = -60.0) -> np.ndarray:
    data, restore = _as2d(samples)
    envelope = uniform_filter1d(_level(data), _samples(rate, 10.0))
    is_open = (envelope >= _db(threshold_db)).astype(np.float64)
    held = maximum_filter1d(is_open, _samples(rate, release_ms))  # stays open through short dips
    target = np.where(held > 0, 1.0, _db(floor_db))
    return restore(data * _smooth(target, rate, 5.0)[:, None])


# --- EQ and filters --------------------------------------------------------------------------

def _biquad(b0: float, b1: float, b2: float, a0: float, a1: float, a2: float) -> np.ndarray:
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _shelf(rate: int, frequency: float, gain_db: float, high: bool) -> np.ndarray:
    """RBJ cookbook shelving filter with slope S = 1."""
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * frequency / rate
    cw, sw = np.cos(w0), np.sin(w0)
    two_root_a_alpha = 2 * np.sqrt(a) * (sw / 2 * np.sqrt(2))
    if high:
        return _biquad(a * ((a + 1) + (a - 1) * cw + two_root_a_alpha),
                       -2 * a * ((a - 1) + (a + 1) * cw),
                       a * ((a + 1) + (a - 1) * cw - two_root_a_alpha),
                       (a + 1) - (a - 1) * cw + two_root_a_alpha,
                       2 * ((a - 1) - (a + 1) * cw),
                       (a + 1) - (a - 1) * cw - two_root_a_alpha)
    return _biquad(a * ((a + 1) - (a - 1) * cw + two_root_a_alpha),
                   2 * a * ((a - 1) - (a + 1) * cw),
                   a * ((a + 1) - (a - 1) * cw - two_root_a_alpha),
                   (a + 1) + (a - 1) * cw + two_root_a_alpha,
                   -2 * ((a - 1) + (a + 1) * cw),
                   (a + 1) + (a - 1) * cw - two_root_a_alpha)


def bass_treble(samples: np.ndarray, rate: int, bass_db: float = 6.0, treble_db: float = 0.0) -> np.ndarray:
    data, restore = _as2d(samples)
    sections = np.vstack((_shelf(rate, min(250.0, rate * 0.1), bass_db, high=False),
                          _shelf(rate, min(4000.0, rate * 0.4), treble_db, high=True)))
    return restore(signal.sosfilt(sections, data, axis=0))


def parametric_eq(samples: np.ndarray, rate: int, frequency: float = 1000.0, gain_db: float = 6.0,
                  q: float = 1.0) -> np.ndarray:
    _check_frequency(frequency, rate)
    data, restore = _as2d(samples)
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * frequency / rate
    alpha = np.sin(w0) / (2 * q)
    sos = _biquad(1 + alpha * a, -2 * np.cos(w0), 1 - alpha * a, 1 + alpha / a, -2 * np.cos(w0), 1 - alpha / a)
    return restore(signal.sosfilt(sos, data, axis=0))


def notch(samples: np.ndarray, rate: int, frequency: float = 60.0, q: float = 10.0) -> np.ndarray:
    _check_frequency(frequency, rate)
    data, restore = _as2d(samples)
    sos = signal.tf2sos(*signal.iirnotch(frequency, q, fs=rate))
    return restore(signal.sosfilt(sos, data, axis=0))


# --- time based and modulation ---------------------------------------------------------------

def echo(samples: np.ndarray, rate: int, delay: float = 0.5, decay: float = 0.5) -> np.ndarray:
    """Repeating echoes. The tail is cut at the end of the audio (the length is preserved)."""
    data, restore = _as2d(samples)
    step = max(1, round(delay * rate))
    out = data.copy()
    repeat = 1
    while repeat * step < data.shape[0] and decay**repeat > 1e-3 and repeat <= 80:
        out[repeat * step:] += decay**repeat * data[:-repeat * step]
        repeat += 1
    return restore(out)


def _sweep(count: int, rate: int, rate_hz: float, depth: float) -> np.ndarray:
    """LFO position in [0, 1] for every frame, centred on 0.5 and swinging ± depth/2."""
    return 0.5 + 0.5 * depth * np.sin(2 * np.pi * rate_hz * np.arange(count) / rate)


def _mix_bank(data: np.ndarray, outputs: Callable[[int], np.ndarray], size: int,
              position: np.ndarray) -> np.ndarray:
    """Cross-fade between ``size`` fixed filters according to ``position`` (0‥1).

    Filtering through a bank of *fixed* filters and fading between their outputs avoids the
    clicks that changing filter coefficients mid-stream would cause.
    """
    scaled = position * (size - 1)
    result = np.zeros_like(data)
    for index in range(size):
        weight = np.clip(1.0 - np.abs(scaled - index), 0.0, 1.0)
        if weight.any():
            result += outputs(index) * weight[:, None]
    return result


def phaser(samples: np.ndarray, rate: int, stages: float = 4.0, rate_hz: float = 0.4, depth: float = 0.8,
           mix: float = 0.5) -> np.ndarray:
    data, restore = _as2d(samples)
    count = max(2, int(stages))
    size = 12
    breaks = np.geomspace(200.0, min(4000.0, rate * 0.4), size)

    def chain(index: int) -> np.ndarray:
        tangent = np.tan(np.pi * breaks[index] / rate)
        coefficient = (tangent - 1) / (tangent + 1)
        sos = np.tile([coefficient, 1.0, 0.0, 1.0, coefficient, 0.0], (count, 1))
        return signal.sosfilt(sos, data, axis=0)

    swept = _mix_bank(data, chain, size, _sweep(data.shape[0], rate, rate_hz, depth))
    return restore((1 - mix) * data + mix * swept)


def wahwah(samples: np.ndarray, rate: int, rate_hz: float = 1.5, depth: float = 0.8,
           resonance: float = 2.5, mix: float = 0.8) -> np.ndarray:
    data, restore = _as2d(samples)
    size = 20
    centres = np.geomspace(350.0, min(2500.0, rate * 0.35), size)

    def band(index: int) -> np.ndarray:
        w0 = 2 * np.pi * centres[index] / rate
        alpha = np.sin(w0) / (2 * resonance)
        sos = _biquad(alpha, 0.0, -alpha, 1 + alpha, -2 * np.cos(w0), 1 - alpha)
        return signal.sosfilt(sos, data, axis=0)

    swept = _mix_bank(data, band, size, _sweep(data.shape[0], rate, rate_hz, depth))
    return restore((1 - mix) * data + mix * swept * 2.0)


def tremolo(samples: np.ndarray, rate: int, frequency: float = 4.0, depth: float = 0.5) -> np.ndarray:
    data, restore = _as2d(samples)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * frequency * np.arange(data.shape[0]) / rate)
    return restore(data * (1.0 - depth * lfo)[:, None])


def distortion(samples: np.ndarray, rate: int, drive: float = 4.0) -> np.ndarray:
    del rate
    data, restore = _as2d(samples)
    return restore(np.tanh(drive * data) / np.tanh(drive))  # soft clipping, full scale stays full scale


# --- simple utilities ------------------------------------------------------------------------

def invert(samples: np.ndarray, rate: int) -> np.ndarray:
    del rate
    return -np.asarray(samples, dtype=np.float64)


def reverse(samples: np.ndarray, rate: int) -> np.ndarray:
    del rate
    return np.asarray(samples, dtype=np.float64)[::-1].copy()


SPECS: dict[str, EffectSpec] = {
    "normalize": EffectSpec("Normalize", "Volume and Compression", (
        Param("target_db", "Peak level", -1.0, -60.0, 0.0, 1, " dBFS"),
        Param("remove_dc", "Remove DC offset", 1.0, 0.0, 1.0, kind="bool"),
    ), normalize),
    "compressor": EffectSpec("Compressor", "Volume and Compression", (
        Param("threshold_db", "Threshold", -18.0, -60.0, 0.0, 1, " dB"),
        Param("ratio", "Ratio", 2.0, 1.0, 20.0, 1, ":1"),
        Param("attack_ms", "Attack", 10.0, 1.0, 200.0, 0, " ms"),
        Param("release_ms", "Release", 100.0, 10.0, 2000.0, 0, " ms"),
        Param("makeup_db", "Make-up gain", 0.0, 0.0, 24.0, 1, " dB"),
    ), compressor),
    "limiter": EffectSpec("Limiter", "Volume and Compression", (
        Param("limit_db", "Limit", -1.0, -24.0, 0.0, 1, " dBFS"),
        Param("release_ms", "Release", 50.0, 5.0, 1000.0, 0, " ms"),
    ), limiter),
    "noise_gate": EffectSpec("Noise Gate", "Volume and Compression", (
        Param("threshold_db", "Threshold", -40.0, -96.0, 0.0, 1, " dB"),
        Param("release_ms", "Hold / release", 100.0, 5.0, 2000.0, 0, " ms"),
        Param("floor_db", "Level when closed", -60.0, -96.0, 0.0, 1, " dB"),
    ), noise_gate),
    "bass_treble": EffectSpec("Bass and Treble", "EQ and Filters", (
        Param("bass_db", "Bass", 6.0, -24.0, 24.0, 1, " dB"),
        Param("treble_db", "Treble", 0.0, -24.0, 24.0, 1, " dB"),
    ), bass_treble),
    "parametric_eq": EffectSpec("Parametric EQ", "EQ and Filters", (
        Param("frequency", "Centre frequency", 1000.0, 20.0, 20000.0, 0, " Hz"),
        Param("gain_db", "Gain", 6.0, -24.0, 24.0, 1, " dB"),
        Param("q", "Q", 1.0, 0.1, 20.0, 2),
    ), parametric_eq),
    "notch": EffectSpec("Notch Filter", "EQ and Filters", (
        Param("frequency", "Frequency", 60.0, 20.0, 20000.0, 0, " Hz"),
        Param("q", "Q", 10.0, 0.5, 100.0, 1),
    ), notch),
    "echo": EffectSpec("Echo", "Delay and Modulation", (
        Param("delay", "Delay", 0.5, 0.01, 5.0, 2, " s"),
        Param("decay", "Decay", 0.5, 0.0, 0.95, 2),
    ), echo),
    "phaser": EffectSpec("Phaser", "Delay and Modulation", (
        Param("stages", "Stages", 4.0, 2.0, 12.0, 0),
        Param("rate_hz", "LFO rate", 0.4, 0.05, 10.0, 2, " Hz"),
        Param("depth", "Depth", 0.8, 0.0, 1.0, 2),
        Param("mix", "Wet amount", 0.5, 0.0, 1.0, 2),
    ), phaser),
    "wahwah": EffectSpec("Wahwah", "Delay and Modulation", (
        Param("rate_hz", "LFO rate", 1.5, 0.05, 10.0, 2, " Hz"),
        Param("depth", "Depth", 0.8, 0.0, 1.0, 2),
        Param("resonance", "Resonance", 2.5, 0.5, 10.0, 1),
        Param("mix", "Wet amount", 0.8, 0.0, 1.0, 2),
    ), wahwah),
    "tremolo": EffectSpec("Tremolo", "Delay and Modulation", (
        Param("frequency", "Rate", 4.0, 0.1, 40.0, 1, " Hz"),
        Param("depth", "Depth", 0.5, 0.0, 1.0, 2),
    ), tremolo),
    "distortion": EffectSpec("Distortion", "Distortion", (
        Param("drive", "Drive", 4.0, 1.0, 50.0, 1),
    ), distortion),
    "invert": EffectSpec("Invert", "Special", (), invert),
    "reverse": EffectSpec("Reverse", "Special", (), reverse),
}


def apply_effect(name: str, samples: np.ndarray, rate: int, parameters: dict[str, float]) -> np.ndarray:
    """Validate ``parameters`` against the spec of ``name`` and run it. Extra keys are ignored."""
    spec = SPECS[name]
    values: dict[str, float] = {}
    for param in spec.params:
        value = float(parameters.get(param.key, param.default))
        if not np.isfinite(value) or not param.minimum <= value <= param.maximum:
            raise ValueError(f"{param.label} must be between {param.minimum:g} and {param.maximum:g}")
        values[param.key] = value
    result = spec.func(np.asarray(samples, dtype=np.float64), int(rate), **values)
    if result.shape != np.asarray(samples).shape:
        raise ValueError(f"{spec.title} changed the length of the audio")
    return result
