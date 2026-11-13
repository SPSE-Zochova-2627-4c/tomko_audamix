"""
Audio Data Layer - Core audio I/O and metadata management.

This module handles loading, storing, and managing audio samples
with their associated metadata (sample rate, channels, etc.).

Design Rationale:
- Separates I/O concerns from processing logic
- Maintains original data alongside processed data for non-destructive editing
- Provides consistent interface for all audio operations
    - Preserve the source level unless normalization is requested
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np
from soundfile import SoundFile

AudioMetadata = Dict[str, Union[str, int, float]]

# Formats exposed by the file dialogs and accepted by libsndfile in the
# supported runtime. MP3 is included because current libsndfile builds expose
# MPEG Layer III; loading/saving still reports a useful error if a platform
# build lacks that codec.
SUPPORTED_AUDIO_EXTENSIONS = (
    ".wav", ".wave", ".flac", ".ogg", ".oga", ".opus", ".aiff", ".aif",
    ".au", ".snd", ".caf", ".mp3",
)

OUTPUT_FORMATS = {
    ".wav": ("WAV", None), ".wave": ("WAV", None),
    ".flac": ("FLAC", None), ".ogg": ("OGG", None),
    ".oga": ("OGG", None), ".opus": ("OGG", "OPUS"),
    ".aiff": ("AIFF", None), ".aif": ("AIFF", None),
    ".au": ("AU", None), ".snd": ("AU", None),
    ".caf": ("CAF", None), ".mp3": ("MP3", "MPEG_LAYER_III"),
}


def is_supported_audio_path(filepath: str) -> bool:
    """Return whether *filepath* has a supported audio extension."""
    return os.path.splitext(filepath)[1].lower() in SUPPORTED_AUDIO_EXTENSIONS


class AudioData:
    """
    Represents an audio file with its samples and metadata.
    
    Supports stereo and mono audio, maintains original data
    separately from processed data for non-destructive editing.
    
    Attributes:
        samples: numpy array of audio samples
        metadata: dict with sample_rate, channels, duration, filename, etc.
        original_samples: copy of original samples (for undo/redo)
        current_operation: description of last applied operation
    """
    
    def __init__(self) -> None:
        self.samples: Optional[np.ndarray] = None
        self.metadata: AudioMetadata = {}
        self.original_samples: Optional[np.ndarray] = None
        self.current_operation: Optional[str] = None
    
    @classmethod
    def load(cls, filepath: str, normalize: bool = False) -> 'AudioData':
        """
        Load audio from file and return AudioData instance.
        
        Args:
            filepath: Path to audio file
            normalize: If True, normalize peak amplitude to 1.0
            
        Returns:
            Loaded AudioData instance
            
        Raises:
            ValueError: If file is invalid or unsupported
            
        Note:
            The default preserves source amplitude for predictable gain changes.
        """
        audio = cls()
        if not is_supported_audio_path(filepath):
            raise ValueError(
                "Unsupported audio extension. Supported formats: "
                + ", ".join(SUPPORTED_AUDIO_EXTENSIONS)
            )
        
        # Read samples and metadata through the same open file handle.
        with SoundFile(filepath) as sf:
            audio.samples = sf.read()
            sample_rate = sf.samplerate
            
            # Preserve metadata
            audio.metadata['filename'] = os.path.basename(filepath)
            audio.metadata['sample_rate'] = sample_rate
            audio.metadata['channels'] = 1 if audio.samples.ndim == 1 else audio.samples.shape[1]
            audio.metadata['channels_count'] = audio.metadata['channels']
            audio.metadata['format'] = sf.format
            audio.metadata['subtype'] = sf.subtype
            subtype_bits = {
                'PCM_S8': 8,
                'PCM_16': 16,
                'PCM_24': 24,
                'PCM_32': 32,
                'FLOAT': 32,
                'DOUBLE': 64,
            }
            audio.metadata['bits_per_sample'] = subtype_bits.get(sf.subtype)
            
            # Calculate duration
            audio.metadata['duration'] = audio.samples.shape[0] / sample_rate
            
            # Get bit depth if available
            audio.metadata['dtype'] = str(audio.samples.dtype)
            
            # Normalize only when the caller explicitly requests it.
            if normalize and audio.samples.size:
                max_val = np.max(np.abs(audio.samples))
                if max_val > 0:
                    audio.samples = audio.samples / max_val
            
            # Store original normalized for non-destructive editing
            audio.original_samples = audio.samples.copy()
            
        return audio
    
    def save(self, filepath: str, format: Optional[str] = None) -> None:
        """
        Save audio samples to file.
        
        Args:
            filepath: Output file path
            format: Audio format (default inferred from extension)
        """
        if self.samples is None:
            raise ValueError("No audio data to save")
        if not format and not is_supported_audio_path(filepath):
            raise ValueError(
                "Unsupported output extension. Choose WAV, FLAC, OGG/Opus, "
                "AIFF, AU, CAF or MP3."
            )
        
        # Use original sample rate and channels
        sr = self.metadata.get('sample_rate', 44100)
        channels = self.metadata.get('channels', 1)
        
        suffix = os.path.splitext(filepath)[1].lower()
        mapped_format, mapped_subtype = OUTPUT_FORMATS.get(suffix, (None, None))
        output_format = format or mapped_format
        output_subtype = None if format else mapped_subtype
        # Write beside the destination, then replace it only after encoding
        # completes. Keeping the suffix preserves format inference for codecs.
        destination = Path(filepath)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                suffix=destination.suffix,
                prefix=f".{destination.stem}.",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
            with SoundFile(
                temporary_path,
                "w",
                samplerate=sr,
                channels=channels,
                format=output_format,
                subtype=output_subtype,
            ) as sound_file:
                sound_file.write(self.samples)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)

        self.metadata["filename"] = destination.name
    
    def get_sample_count(self) -> int:
        """Return number of samples."""
        return len(self.samples) if self.samples is not None else 0

    def get_peak(self) -> float:
        """Return the largest absolute sample amplitude."""
        return float(np.max(np.abs(self.samples))) if self.samples is not None and self.samples.size else 0.0

    def get_rms(self) -> float:
        """Return root mean square amplitude over all channels."""
        return float(np.sqrt(np.mean(np.square(self.samples)))) if self.samples is not None and self.samples.size else 0.0

    def get_dr(self) -> float:
        """Return peak to RMS ratio in decibels."""
        rms = self.get_rms()
        return float(20 * np.log10(self.get_peak() / rms)) if rms else 0.0
    
    def get_duration(self) -> float:
        """Return duration in seconds."""
        if self.metadata.get('sample_rate'):
            return self.get_sample_count() / self.metadata['sample_rate']
        return 0.0
    
    def get_info(self) -> AudioMetadata:
        """
        Get human-readable audio information.
        
        Returns:
            Dict with file name, duration, sample rate, channels, etc.
        """
        info = self.metadata.copy()
        info['sample_count'] = self.get_sample_count()
        info['duration'] = self.get_duration()
        info['sample_format'] = self.metadata.get('dtype', 'unknown')
        return info
    
    def undo_last_operation(self) -> Optional['AudioData']:
        """
        Restore original samples, undoing last operation.
        
        Returns:
            Self for method chaining, or None if no undo available
        """
        if self.original_samples is not None:
            self.samples = self.original_samples.copy()
            self.current_operation = None
            return self
        return None
    
    def apply_operation(self, operation: str, description: Optional[str] = None) -> 'AudioData':
        """
        Mark current operation for later undo.
        
        Args:
            operation: Operation name (e.g., 'volume_increase', 'filter_apply')
            description: Human-readable description
            
        Returns:
            Self for method chaining
        """
        if self.samples is not None:
            self.original_samples = self.samples.copy()
        self.current_operation = f"{operation}: {description or ''}"
        return self


def load_audio(filepath: str, normalize: bool = False) -> AudioData:
    """Convenience function to load audio from file."""
    return AudioData.load(filepath, normalize=normalize)


def save_audio(audio: AudioData, filepath: str) -> None:
    """Convenience function to save audio to file."""
    audio.save(filepath)
