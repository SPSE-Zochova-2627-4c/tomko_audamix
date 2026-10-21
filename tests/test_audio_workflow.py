"""Focused checks for real audio state changes and export."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from audamix.data.audio_data import AudioData
from audamix.dsp.signal_processor import SignalProcessor
from audamix.main import command_process
from audamix.processor import create_processor


def make_audio(samples, sample_rate=8000):
    audio = AudioData()
    audio.samples = np.asarray(samples, dtype=np.float64)
    audio.metadata = {"sample_rate": sample_rate, "channels": 1 if audio.samples.ndim == 1 else audio.samples.shape[1]}
    audio.original_samples = audio.samples.copy()
    return audio


class AudioWorkflowTests(unittest.TestCase):
    def test_volume_changes_samples_without_changing_source_and_undo_restores(self):
        source = make_audio(np.full(128, 0.25))
        processor = create_processor(source)
        self.assertTrue(processor.adjust_volume(0.5).success)
        self.assertAlmostEqual(processor.current_audio.get_peak(), 0.125)
        self.assertAlmostEqual(source.get_peak(), 0.25)
        self.assertTrue(processor.undo().success)
        self.assertAlmostEqual(processor.current_audio.get_peak(), 0.25)
        self.assertFalse(processor.undo().success)

    def test_filters_use_hz_and_keep_stereo_channels_separate(self):
        rate = 8000
        t = np.arange(rate) / rate
        samples = np.column_stack((0.5 * np.sin(2 * np.pi * 200 * t),
                                   0.5 * np.sin(2 * np.pi * 2400 * t)))
        audio = make_audio(samples)
        low = SignalProcessor(audio).apply_filter("lowpass", 500)
        high = SignalProcessor(audio).apply_filter("highpass", 1000)
        self.assertEqual(low.samples.shape, samples.shape)
        self.assertGreater(np.std(low.samples[:, 0]), 10 * np.std(low.samples[:, 1]))
        self.assertGreater(np.std(high.samples[:, 1]), 10 * np.std(high.samples[:, 0]))
        np.testing.assert_array_equal(audio.samples, samples)
        with self.assertRaises(ValueError):
            SignalProcessor(audio).apply_filter("lowpass", 5000)

    def test_classical_denoise_keeps_duration(self):
        rng = np.random.default_rng(1)
        audio = make_audio(rng.normal(0, 0.1, size=(2048, 2)))
        noise = make_audio(rng.normal(0, 0.03, size=(2048, 2)))
        result = SignalProcessor(audio).classical_denoise(noise.samples)
        self.assertEqual(result.samples.shape, audio.samples.shape)
        self.assertTrue(np.all(np.isfinite(result.samples)))

    def test_cli_pipeline_exports_changed_audio_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            target = Path(directory) / "result.wav"
            sf.write(source, np.full(1024, 0.25), 8000)
            command_process(str(source), str(target), volume=0.5)
            original, _ = sf.read(source)
            changed, _ = sf.read(target)
            self.assertAlmostEqual(float(np.max(changed)), 0.125, places=4)
            self.assertAlmostEqual(float(np.max(original)), 0.25, places=4)
            with self.assertRaises(ValueError):
                command_process(str(source), str(source), volume=0.5)

    def test_declip_uses_correct_ai_method_and_can_be_undone(self):
        source = make_audio(np.array([1.0, 1.0, 0.25]))
        processor = create_processor(source)
        restored = make_audio(np.array([0.7, 0.8, 0.25]))
        restored.metadata["declipped"] = True
        with patch("audamix.processor._create_audio_ai") as ai_class:
            ai_class.return_value.declip.return_value = (restored, "Restored estimate")
            result = processor.declip()
            ai_class.return_value.declip.assert_called_once()
        self.assertTrue(result.success)
        self.assertEqual(processor.processing_history[-1]["type"], "ai_declip")
        self.assertTrue(processor.undo().success)
        np.testing.assert_array_equal(processor.current_audio.samples, source.samples)


if __name__ == "__main__":
    unittest.main()
