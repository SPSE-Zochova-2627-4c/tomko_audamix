"""Behavioural tests for the Audacity-style effects in audamix.dsp.effects."""

from __future__ import annotations

import numpy as np
import pytest

from audamix.dsp import effects

RATE = 16000


def tone(frequency: float, seconds: float = 1.0, amplitude: float = 0.5) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * frequency * np.arange(int(RATE * seconds)) / RATE)


def rms(x: np.ndarray, skip: int = 2000) -> float:
    return float(np.sqrt(np.mean(np.square(x[skip:]))))


def run(name: str, x: np.ndarray, **parameters: float) -> np.ndarray:
    return effects.apply_effect(name, x, RATE, parameters)


def test_every_effect_keeps_shape_and_is_finite_on_mono_and_stereo() -> None:
    mono = tone(440, 0.5)
    stereo = np.stack((mono, 0.5 * mono[::-1]), axis=1)
    for name in effects.SPECS:
        for data in (mono, stereo):
            out = run(name, data)
            assert out.shape == data.shape, name
            assert np.all(np.isfinite(out)), name
            assert np.array_equal(data, mono if data.ndim == 1 else stereo)  # input untouched


def test_normalize_peaks_at_target_and_removes_dc() -> None:
    x = tone(300, amplitude=0.1) + 0.05
    out = run("normalize", x, target_db=-6.0)
    assert abs(np.max(np.abs(out)) - 10 ** (-6 / 20)) < 1e-6
    assert abs(np.mean(out)) < 1e-3
    assert np.max(np.abs(run("normalize", x, remove_dc=0.0))) == pytest.approx(10 ** (-1 / 20))
    assert not run("normalize", np.zeros(100)).any()  # silence stays silence
    stereo = np.stack((tone(300, amplitude=0.1), tone(300, amplitude=0.05)), axis=1)
    out = run("normalize", stereo)
    assert abs(rms(out[:, 1]) / rms(out[:, 0]) - 0.5) < 0.01  # channel balance is kept


def test_invert_and_reverse_round_trip() -> None:
    x = tone(220, 0.1)
    assert np.array_equal(run("invert", run("invert", x)), x)
    assert np.array_equal(run("reverse", run("reverse", x)), x)
    assert run("reverse", np.arange(5.0))[0] == 4.0


def test_bass_and_treble_shelves_change_the_right_band() -> None:
    low, high = tone(60, 2.0, 0.2), tone(6000, 2.0, 0.2)
    boosted_low = rms(run("bass_treble", low, bass_db=12.0, treble_db=0.0)) / rms(low)
    untouched_high = rms(run("bass_treble", high, bass_db=12.0, treble_db=0.0)) / rms(high)
    assert 10 ** (10 / 20) < boosted_low < 10 ** (14 / 20)  # about +12 dB
    assert 0.9 < untouched_high < 1.1
    cut_high = rms(run("bass_treble", high, bass_db=0.0, treble_db=-12.0)) / rms(high)
    assert 10 ** (-14 / 20) < cut_high < 10 ** (-10 / 20)


def test_parametric_eq_and_notch() -> None:
    f = tone(1000, 2.0, 0.2)
    boosted = rms(run("parametric_eq", f, frequency=1000.0, gain_db=9.0, q=2.0)) / rms(f)
    assert abs(20 * np.log10(boosted) - 9.0) < 0.5
    far = tone(100, 2.0, 0.2)
    assert abs(rms(run("parametric_eq", far, frequency=4000.0, gain_db=9.0, q=2.0)) / rms(far) - 1) < 0.05
    hum = tone(60, 2.0, 0.3)
    assert rms(run("notch", hum, frequency=60.0, q=10.0)) < 0.02 * rms(hum)
    assert rms(run("notch", tone(1000, 1.0), frequency=60.0)) > 0.95 * rms(tone(1000, 1.0))
    with pytest.raises(ValueError):
        run("notch", hum, frequency=9000.0)  # above Nyquist for 16 kHz audio


def test_compressor_reduces_loud_parts_only() -> None:
    quiet, loud = tone(300, 1.0, 0.02), tone(300, 1.0, 0.8)
    x = np.concatenate((quiet, loud, quiet))
    out = run("compressor", x, threshold_db=-20.0, ratio=4.0, attack_ms=5.0, release_ms=50.0)
    n = len(quiet)
    assert abs(rms(out[:n], 4000) / rms(x[:n], 4000) - 1) < 0.1  # below threshold: unchanged
    assert rms(out[n + 4000:2 * n], 0) < 0.6 * rms(x[n + 4000:2 * n], 0)  # loud part pulled down
    assert rms(run("compressor", loud, threshold_db=-20.0, ratio=4.0, makeup_db=12.0)) > rms(
        run("compressor", loud, threshold_db=-20.0, ratio=4.0))


def test_limiter_never_exceeds_the_limit() -> None:
    x = np.concatenate((tone(200, 0.5, 0.1), tone(200, 0.5, 1.0), tone(200, 0.5, 0.1)))
    out = run("limiter", x, limit_db=-6.0)
    assert np.max(np.abs(out)) <= 10 ** (-6 / 20) + 1e-9
    assert abs(rms(out[:4000], 0) / rms(x[:4000], 0) - 1) < 0.05  # quiet start is left alone


def test_noise_gate_mutes_hiss_and_keeps_signal() -> None:
    rng = np.random.default_rng(1)
    hiss = 0.003 * rng.standard_normal(RATE)
    burst = tone(500, 0.5, 0.5)
    x = np.concatenate((hiss, burst, hiss))
    out = run("noise_gate", x, threshold_db=-35.0, release_ms=50.0, floor_db=-60.0)
    # The gate opens ~25 ms early on purpose (look-ahead), so measure well before the burst.
    assert rms(out[2000:RATE - 2000], 0) < 0.1 * rms(x[2000:RATE - 2000], 0)
    middle = out[RATE + 800:RATE + len(burst) - 800]
    assert rms(middle, 0) > 0.95 * rms(burst[800:-800], 0)


def test_echo_adds_decaying_repeats() -> None:
    impulse = np.zeros(RATE * 2)
    impulse[0] = 1.0
    out = run("echo", impulse, delay=0.25, decay=0.5)
    step = RATE // 4
    assert out[0] == 1.0 and out[step] == pytest.approx(0.5) and out[2 * step] == pytest.approx(0.25)
    assert out[step + 1] == 0.0 and out.shape == impulse.shape


def test_modulation_effects_change_the_sound_without_blowing_up() -> None:
    x = tone(440, 2.0, 0.4) + tone(1320, 2.0, 0.2)
    for name in ("phaser", "wahwah"):
        out = run(name, x)
        assert not np.allclose(out, x) and np.max(np.abs(out)) < 2.0, name
        assert np.max(np.abs(np.diff(out))) < 0.5, f"{name} produced clicks"
    assert np.allclose(run("phaser", x, mix=0.0), x)
    assert np.allclose(run("wahwah", x, mix=0.0), x)
    trem = run("tremolo", tone(440, 2.0, 0.5), frequency=2.0, depth=1.0)
    gain_swing = np.abs(trem).reshape(-1, 400).max(axis=1)  # loudness per 25 ms block
    assert gain_swing.min() < 0.1 and gain_swing.max() > 0.45


def test_distortion_soft_clips_and_keeps_full_scale() -> None:
    x = tone(100, 0.5, 0.2)
    out = run("distortion", x, drive=10.0)
    assert np.max(np.abs(out)) > 0.9  # quiet input is driven hard
    assert np.max(np.abs(run("distortion", tone(100, 0.5, 1.0), drive=10.0))) <= 1.0 + 1e-9
    assert np.allclose(run("distortion", x, drive=1.0), np.tanh(x) / np.tanh(1.0))


def test_parameter_validation_and_defaults() -> None:
    x = tone(440, 0.1)
    for name, bad in (("compressor", {"ratio": 0.5}), ("limiter", {"limit_db": 6.0}),
                      ("echo", {"decay": 1.0}), ("normalize", {"target_db": float("nan")})):
        with pytest.raises(ValueError):
            run(name, x, **bad)
    assert run("echo", x, unknown_key=3.0).shape == x.shape  # extra keys (e.g. start/end) are ignored
    for spec in effects.SPECS.values():
        for p in spec.params:
            assert p.minimum <= p.default <= p.maximum, p.key
