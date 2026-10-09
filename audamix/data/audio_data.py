"""
Audio Data Layer - Core audio I/O and metadata management.

This module handles loading, storing, and managing audio samples
with their associated metadata (sample rate, channels, etc.).

Design Rationale:
- Separates I/O concerns from processing logic
- Maintains original data alongside processed data for non-destructive editing
- Provides consistent interface for all audio operations
- DEFAULT: Normalize audio to [-1, 1] to preserve headroom
"""

import numpy as np
from soundfile import SoundFile, read as sf_read, write as sf_write
from typing import Dict, Tuple, Optional, Union
import os

AudioMetadata = Dict[str, Union[str, int, float]]


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
    def load(cls, filepath: str, normalize: bool = True) -> 'AudioData':
        """
        Load audio from file and return AudioData instance.
        
        Args:
            filepath: Path to audio file
            normalize: If True, normalize samples to [-1, 1] range (DEFAULT)
            
        Returns:
            Loaded AudioData instance
            
        Raises:
            ValueError: If file is invalid or unsupported
            
        Note:
            Normalization is now DEFAULT to preserve headroom for DSP operations.
            Each DSP operation handles its own normalization and clipping protection.
        """
        audio = cls()
        
        # Load audio with soundfile
        with SoundFile(filepath) as sf:
            audio.samples, sample_rate = sf_read(filepath)
            
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
            
            # Normalize to [-1, 1] by DEFAULT to preserve headroom
            # This prevents clipping issues in subsequent DSP operations
            # Each DSP layer handles its own normalization and clipping protection
            if normalize:
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
        
        # Use original sample rate and channels
        sr = self.metadata.get('sample_rate', 44100)
        channels = self.metadata.get('channels', 1)
        
        # Create SoundFile for writing
        with SoundFile(filepath, 'w', samplerate=sr, channels=channels, 
                      format=format or self.metadata.get('format', None)) as sf:
            sf.write(self.samples)
        
        # Update filename metadata
        self.metadata['filename'] = os.path.basename(filepath)
    
    def get_sample_count(self) -> int:
        """Return number of samples."""
        return len(self.samples) if self.samples is not None else 0
    
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


def load_audio(filepath: str, normalize: bool = True) -> AudioData:
    """Convenience function to load audio from file."""
    return AudioData.load(filepath, normalize=normalize)


def save_audio(audio: AudioData, filepath: str) -> None:
    """Convenience function to save audio to file."""
    audio.save(filepath)
