"""Optional, locally executed neural audio restoration backends.

The old implementation used randomly initialized PyTorch modules and called
them AI models. This module uses the released pretrained DeepFilterNet3 model
for denoising. Declipping is exposed through optional VoiceFixer weights; it
does not silently fall back to interpolation.
"""

from __future__ import annotations

import importlib
import sys
import types
from math import gcd
from typing import Any, Optional, Tuple

import numpy as np
import torch
from scipy.signal import resample_poly

from ..data.audio_data import AudioData


class AudioAI:
    """Run pretrained local restoration models on :class:`AudioData`."""

    def __init__(self, model_dir: Optional[str] = None, device: str = "cpu") -> None:
        self.device = torch.device(device)
        self.model_dir = model_dir
        self._df_model: Optional[torch.nn.Module] = None
        self._df_state: Any = None
        self._df_enhance: Any = None
        self._df_error: Optional[Exception] = None
        self._voicefixer: Any = None
        self._voicefixer_error: Optional[Exception] = None

    @staticmethod
    def _channels_first(samples: np.ndarray) -> Tuple[np.ndarray, bool]:
        array = np.asarray(samples, dtype=np.float32)
        if array.ndim == 1:
            return array[None, :], True
        if array.ndim == 2:
            return array.T, False
        raise ValueError("Audio samples must be a 1D mono or 2D (frames, channels) array")

    @staticmethod
    def _restore_shape(channels_first: np.ndarray, mono: bool) -> np.ndarray:
        return channels_first[0] if mono else channels_first.T

    @staticmethod
    def _resample(channels: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
        if source_sr == target_sr:
            return channels
        factor = gcd(int(source_sr), int(target_sr))
        up, down = target_sr // factor, source_sr // factor
        return np.stack(
            [resample_poly(channel, up, down).astype(np.float32) for channel in channels], axis=0
        )

    @staticmethod
    def _install_torchaudio_metadata_compat() -> None:
        """Bridge DeepFilterNet 0.5.x's removed torchaudio type module.

        Audamix uses SoundFile for I/O, so this only supplies the annotation
        class expected while importing DeepFilterNet.
        """
        try:
            importlib.import_module("torchaudio.backend.common")
            return
        except (ImportError, ModuleNotFoundError):
            common = types.ModuleType("torchaudio.backend.common")

            class AudioMetaData:
                pass

            common.AudioMetaData = AudioMetaData
            backend = types.ModuleType("torchaudio.backend")
            backend.common = common
            sys.modules.setdefault("torchaudio.backend", backend)
            sys.modules.setdefault("torchaudio.backend.common", common)

    def _load_deepfilter(self) -> None:
        if self._df_model is not None:
            return
        if self._df_error is not None:
            raise RuntimeError(f"DeepFilterNet is unavailable: {self._df_error}") from self._df_error
        try:
            self._install_torchaudio_metadata_compat()
            from df import enhance, init_df
            from df.model import ModelParams

            self._df_model, self._df_state, _ = init_df(
                model_base_dir=self.model_dir,
                default_model="DeepFilterNet3",
                log_file=None,
                log_level="ERROR",
            )
            self._df_enhance = enhance
            self._df_sample_rate = int(ModelParams().sr)
        except Exception as exc:
            self._df_error = exc
            raise RuntimeError(
                "DeepFilterNet is unavailable. Install deepfilternet and its model weights."
            ) from exc

    def _denoise_deepfilter(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        self._load_deepfilter()
        channels, mono = self._channels_first(samples)
        original_length = channels.shape[-1]
        model_input = self._resample(channels, sample_rate, self._df_sample_rate)
        tensor = torch.from_numpy(model_input).to(self.device)
        with torch.inference_mode():
            enhanced = self._df_enhance(self._df_model, self._df_state, tensor, pad=True)
        result = enhanced.detach().cpu().numpy().astype(np.float32)
        result = self._resample(result, self._df_sample_rate, sample_rate)
        result = result[..., :original_length]
        if result.shape[-1] < original_length:
            result = np.pad(result, ((0, 0), (0, original_length - result.shape[-1])))
        return self._restore_shape(np.clip(result, -1.0, 1.0), mono)

    def _load_voicefixer(self) -> Any:
        if self._voicefixer is not None:
            return self._voicefixer
        if self._voicefixer_error is not None:
            raise RuntimeError(f"VoiceFixer is unavailable: {self._voicefixer_error}") from self._voicefixer_error
        try:
            module = importlib.import_module("voicefixer")
            self._voicefixer = module.VoiceFixer()
            return self._voicefixer
        except Exception as exc:
            self._voicefixer_error = exc
            raise RuntimeError(
                "VoiceFixer is unavailable or its weights are not installed; declipping was not performed."
            ) from exc

    def denoise(
        self, audio: AudioData, threshold: float = 0.01, strength: float = 0.5
    ) -> Tuple[AudioData, str]:
        """Denoise with pretrained DeepFilterNet3.

        ``threshold`` and ``strength`` remain for API compatibility; the
        pretrained model controls its own suppression mask.
        """
        del threshold, strength
        if audio.samples is None:
            raise ValueError("No audio data to denoise")
        sample_rate = int(audio.metadata.get("sample_rate", 44100))
        processed = self._denoise_deepfilter(audio.samples, sample_rate)
        result = AudioData()
        result.samples = processed
        result.metadata = audio.metadata.copy()
        result.metadata.update({"denoised": True, "ai_model": "DeepFilterNet3"})
        result.original_samples = np.asarray(audio.samples).copy()
        return result, "Denoising completed with pretrained DeepFilterNet3"

    def declipe(self, audio: AudioData, confidence: float = 0.7) -> Tuple[AudioData, str]:
        """Restore clipped speech with optional pretrained VoiceFixer.

        VoiceFixer is speech-only and expects 44.1 kHz. No interpolation or
        randomly initialized model is used when its package/weights are absent.
        """
        del confidence
        if audio.samples is None:
            raise ValueError("No audio data to declip")
        channels, mono = self._channels_first(audio.samples)
        clipped = np.abs(channels) >= 0.999
        if not np.any(clipped):
            result = AudioData()
            result.samples = np.asarray(audio.samples).copy()
            result.metadata = audio.metadata.copy()
            result.metadata["declipped"] = False
            return result, "No hard clipping detected"

        fixer = self._load_voicefixer()
        sample_rate = int(audio.metadata.get("sample_rate", 44100))
        model_input = self._resample(channels, sample_rate, 44100)
        restored = [fixer.restore_inmem(channel, cuda=self.device.type == "cuda") for channel in model_input]
        output = self._resample(np.stack(restored, axis=0), 44100, sample_rate)
        output = output[..., : channels.shape[-1]]
        result = AudioData()
        result.samples = self._restore_shape(np.clip(output, -1.0, 1.0), mono)
        result.metadata = audio.metadata.copy()
        result.metadata.update({"declipped": True, "ai_model": "VoiceFixer"})
        result.original_samples = np.asarray(audio.samples).copy()
        return result, "Declipping completed with pretrained VoiceFixer; result is an estimate"

    def is_model_available(self, model_type: str) -> bool:
        if model_type == "denoise":
            return self._df_model is not None
        if model_type == "declipe":
            return self._voicefixer is not None
        return False

    def unload_models(self) -> None:
        self._df_model = None
        self._df_state = None
        self._df_enhance = None
        self._voicefixer = None
        if self.device.type == "cuda":
            torch.cuda.empty_cache()


def denoise(audio: AudioData, threshold: float = 0.01) -> Tuple[AudioData, str]:
    return AudioAI().denoise(audio, threshold)


def declipe(audio: AudioData, confidence: float = 0.7) -> Tuple[AudioData, str]:
    return AudioAI().declipe(audio, confidence)
