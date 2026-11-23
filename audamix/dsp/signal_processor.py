"""Classical, non-destructive audio processing."""

from typing import Optional
import warnings

import numpy as np
from scipy import signal

from ..data.audio_data import AudioData


class SignalProcessor:
    """Apply DSP operations without changing the input :class:`AudioData`."""

    def __init__(self, audio: AudioData) -> None:
        if audio.samples is None:
            raise ValueError("No audio loaded")
        self.audio = audio
        self._samples = np.asarray(audio.samples, dtype=np.float64)
        self._sample_rate = int(audio.metadata.get("sample_rate", 44100))

    def _result(self, samples: np.ndarray) -> AudioData:
        if samples.shape != self._samples.shape or not np.all(np.isfinite(samples)):
            raise ValueError("Processing produced invalid audio samples")
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak > 1.0:
            warnings.warn("Output peak exceeded 1.0; reducing gain to avoid clipping")
            samples = samples / peak
        result = AudioData()
        result.samples = np.asarray(samples, dtype=np.float64).copy()
        result.metadata = self.audio.metadata.copy()
        result.original_samples = self.audio.original_samples
        return result

    def from_samples(self, samples: np.ndarray) -> AudioData:
        """Wrap externally processed samples, applying the same validity and clipping checks."""
        return self._result(np.asarray(samples, dtype=np.float64))

    def adjust_volume(self, factor: float) -> AudioData:
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError("Volume factor must be finite and positive")
        return self._result(self._samples * factor)

    def apply_filter(
        self, filter_type: str, cutoff_freq: float, q_factor: float = 1.0,
        order: int = 2,
    ) -> AudioData:
        if filter_type not in {"lowpass", "highpass", "bandpass", "peaking"}:
            raise ValueError(f"Unknown filter type: {filter_type}")
        nyquist = self._sample_rate / 2
        if not np.isfinite(cutoff_freq) or not 0 < cutoff_freq < nyquist:
            raise ValueError(f"Cutoff frequency must be between 0 and {nyquist:g} Hz")
        if not np.isfinite(q_factor) or q_factor <= 0:
            raise ValueError("Q factor must be finite and positive")
        if not isinstance(order, int) or order < 1:
            raise ValueError("Filter order must be a positive integer")

        if filter_type == "bandpass":
            bandwidth = cutoff_freq / q_factor
            low, high = cutoff_freq - bandwidth / 2, cutoff_freq + bandwidth / 2
            if low <= 0 or high >= nyquist:
                raise ValueError("Bandpass range must fit between 0 Hz and Nyquist")
            sos = signal.butter(order, (low, high), btype="bandpass", fs=self._sample_rate, output="sos")
        elif filter_type == "peaking":
            b, a = signal.iirpeak(cutoff_freq, q_factor, fs=self._sample_rate)
            sos = signal.tf2sos(b, a)
        else:
            kind = "lowpass" if filter_type == "lowpass" else "highpass"
            sos = signal.butter(order, cutoff_freq, btype=kind, fs=self._sample_rate, output="sos")

        if not self._samples.size:
            return self._result(self._samples)
        filtered = signal.sosfilt(sos, self._samples, axis=0)
        return self._result(filtered)

    def classical_denoise(
        self, noise_estimate: Optional[np.ndarray] = None, iterations: int = 3,
    ) -> AudioData:
        if not isinstance(iterations, int) or iterations < 1:
            raise ValueError("Iterations must be a positive integer")
        if not self._samples.size:
            return self._result(self._samples)
        if noise_estimate is None:
            warnings.warn("No noise estimate provided; using a basic median filter")
            kernel = (7, 1) if self._samples.ndim == 2 else 7
            result = self._samples.copy()
            for _ in range(iterations):
                result = signal.medfilt(result, kernel_size=kernel)
            return self._result(result)

        noise = np.asarray(noise_estimate, dtype=np.float64)
        if noise.shape != self._samples.shape or not np.all(np.isfinite(noise)):
            raise ValueError("Noise estimate must match the audio shape and be finite")
        channels = self._samples[:, None] if self._samples.ndim == 1 else self._samples
        noise_channels = noise[:, None] if noise.ndim == 1 else noise
        outputs = []
        for channel, noise_channel in zip(channels.T, noise_channels.T):
            nperseg = min(1024, len(channel))
            _, _, spectrum = signal.stft(channel, fs=self._sample_rate, nperseg=nperseg)
            _, _, noise_spectrum = signal.stft(noise_channel, fs=self._sample_rate, nperseg=nperseg)
            floor = np.median(np.abs(noise_spectrum), axis=1, keepdims=True)
            magnitude = np.abs(spectrum)
            gain = np.maximum(0.05, 1 - floor / np.maximum(magnitude, 1e-12)) ** iterations
            _, restored = signal.istft(spectrum * gain, fs=self._sample_rate, nperseg=nperseg)
            outputs.append(restored[:len(channel)])
        result = np.stack(outputs, axis=1)
        return self._result(result[:, 0] if self._samples.ndim == 1 else result)

    def get_processing_info(self) -> dict:
        return {
            "sample_rate": self._sample_rate,
            "num_samples": len(self._samples),
            "channels": self.audio.metadata.get("channels", 1),
            "dtype": str(self._samples.dtype),
            "rms": float(np.sqrt(np.mean(self._samples ** 2))) if self._samples.size else 0.0,
        }


def apply_volume(audio: AudioData, factor: float) -> AudioData:
    return SignalProcessor(audio).adjust_volume(factor)


def apply_filter(audio: AudioData, filter_type: str, cutoff_freq: float, q_factor: float = 1.0) -> AudioData:
    return SignalProcessor(audio).apply_filter(filter_type, cutoff_freq, q_factor)


def classical_denoise(audio: AudioData, noise_estimate: Optional[np.ndarray] = None) -> AudioData:
    return SignalProcessor(audio).classical_denoise(noise_estimate)
