"""Pure NumPy tests for sample-level editing helpers."""

from __future__ import annotations

import numpy as np
import pytest

from audamix.dsp import editing


def test_delete_keep_insert_silence_do_not_mutate_input() -> None:
    data = np.arange(10, dtype=np.float64) / 10
    original = data.copy()
    assert editing.delete_range(data, 2, 5).tolist() == [0.0, 0.1, 0.5, 0.6, 0.7, 0.8, 0.9]
    assert editing.keep_range(data, 2, 5).tolist() == [0.2, 0.3, 0.4]
    assert editing.insert_clip(data, 1, np.array([9.0, 9.0])).shape == (12,)
    assert not editing.silence_range(data, 2, 5)[2:5].any()
    assert np.array_equal(data, original)


def test_fade_is_linear_and_rejects_bad_input() -> None:
    faded = editing.fade_range(np.ones((5, 2)), 0, 5, "in")
    assert faded[0].tolist() == [0.0, 0.0] and faded[-1].tolist() == [1.0, 1.0]
    out = editing.fade_range(np.ones(5), 0, 5, "out")
    assert out[0] == 1.0 and out[-1] == 0.0
    with pytest.raises(ValueError):
        editing.fade_range(np.ones(5), 0, 1, "in")
    with pytest.raises(ValueError):
        editing.fade_range(np.ones(5), 0, 5, "sideways")


def test_match_clip_converts_rate_and_channels() -> None:
    mono = np.sin(np.linspace(0, 20, 4000))
    stereo = editing.match_clip(mono, 8000, 16000, 2)
    assert stereo.shape == (8000, 2)
    assert editing.match_clip(stereo, 16000, 16000, 1).shape == (8000,)


def test_generate_and_validation() -> None:
    tone = editing.generate("tone", 8000, 2, 0.5, 1000, 0.5)
    assert tone.shape == (4000, 2) and abs(np.max(tone) - 0.5) < 0.01
    assert not editing.generate("silence", 8000, 1, 0.1).any()
    assert np.max(np.abs(editing.generate("noise", 8000, 1, 0.1, amplitude=0.2))) <= 0.2
    for bad in ({"duration": 0}, {"duration": 1, "amplitude": 2}, {"duration": 1, "frequency": 5000}):
        with pytest.raises(ValueError):
            editing.generate("tone", 8000, 1, **bad)
    with pytest.raises(ValueError):
        editing.generate("saw", 8000, 1, 1)


def test_analyze_reports_level_and_frequency() -> None:
    rate = 8000
    tone = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(rate) / rate)
    stats = editing.analyze(tone, rate)
    assert abs(stats["peak"] - 0.5) < 1e-3
    assert abs(stats["rms"] - 0.5 / np.sqrt(2)) < 1e-3
    assert abs(stats["dominant_hz"] - 1000) < 2
    assert editing.analyze(np.ones(100), rate)["clipped_samples"] == 100
    with pytest.raises(ValueError):
        editing.analyze(np.zeros(0), rate)


def test_spectrogram_image_shape_and_peak_row() -> None:
    rate = 8000
    tone = 0.5 * np.sin(2 * np.pi * 2000 * np.arange(rate * 2) / rate)
    image = editing.spectrogram_image(tone, rate, columns=100)
    assert image.dtype == np.uint8 and image.shape == (513, 100)
    brightest_row = int(np.argmax(image[:, 50]))
    frequency = (512 - brightest_row) * rate / 1024  # row 0 is Nyquist
    assert abs(frequency - 2000) < 20
    assert editing.spectrogram_image(np.ones(10), rate).shape[1] >= 1


def test_smooth_join_removes_the_click_without_changing_length() -> None:
    rate = 8000
    tone = 0.25 * np.sin(2 * np.pi * 440 * np.arange(rate * 2) / rate)
    normal_step = float(np.max(np.abs(np.diff(tone))))
    spliced = editing.delete_range(tone, 800, 805)
    assert abs(spliced[800] - spliced[799]) > 2 * normal_step  # the raw splice clicks
    smoothed = editing.smooth_join(spliced, 800, rate)
    assert smoothed.shape == spliced.shape
    assert np.max(np.abs(np.diff(smoothed))) <= normal_step * 1.05  # no step bigger than the tone's own
    assert smoothed[799] == 0.0 or abs(smoothed[799]) < normal_step
    assert np.array_equal(smoothed[:700], spliced[:700]) and np.array_equal(smoothed[900:], spliced[900:])
    stereo = editing.smooth_join(np.ones((100, 2)), 50, rate)
    assert stereo.shape == (100, 2) and stereo[50].tolist() == [0.0, 0.0]
    assert editing.smooth_join(np.ones(10), 0, rate).shape == (10,)  # edges of the track are fine
