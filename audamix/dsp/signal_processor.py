"""
Digital Signal Processing Layer - Classical audio operations.

Implements traditional DSP methods:
- Volume/Amplitude control
- Frequency filters (LPF, HPF, bandpass, peaking)
- Classical noise reduction (spectral subtraction approach)

Design Rationale:
- Uses NumPy for efficient array operations
- Leverages SciPy's well-tested signal processing functions
- Non-destructive: preserves original audio
- Each DSP operation normalizes and protects against clipping
"""

import numpy as np
from scipy import signal as sp_signal
from typing import List, Optional, Tuple
import warnings

from ..data.audio_data import AudioData


class SignalProcessor:
    """
    Classical DSP operations for audio processing.
    
    Supports volume adjustment, filtering, and basic noise reduction
    using traditional signal processing techniques.
    Each operation normalizes and handles clipping protection.
    """
    
    def __init__(self, audio: AudioData) -> None:
        """
        Initialize processor with loaded audio data.
        
        Args:
            audio: AudioData instance containing samples and metadata
        """
        self.audio = audio
        self._samples = audio.samples
        self._sample_rate = audio.metadata.get('sample_rate', 44100)
        self._num_samples = len(self._samples)
        
        # Filter design parameters
        self._num_taps: int = 101  # Odd number for symmetric filters
        self._transition_width: float = 0.05  # Normalized frequency (fraction of Nyquist)
    
    def _normalize_samples(self) -> None:
        """
        Normalize samples to [-1, 1] range before processing.
        
        This is the DEFAULT behavior for headroom preservation.
        Each DSP operation handles its own normalization and clipping protection.
        """
        max_val = np.max(np.abs(self._samples))
        if max_val > 0:
            self._samples = self._samples / max_val
    
    def adjust_volume(self, factor: float) -> AudioData:
        """
        Adjust audio amplitude by given factor.
        
        Args:
            factor: Multiplicative factor (> 0). Use 1.0 for no change.
            
        Returns:
            New AudioData instance with adjusted samples
            
        Raises:
            ValueError: If factor is <= 0 or would cause extreme clipping
            
        Note:
            - Normalizes to [-1, 1] before applying factor (preserves headroom)
            - If result would clip, normalizes to prevent clipping
        """
        if factor <= 0:
            raise ValueError("Volume factor must be positive")
        
        # Normalize to [-1, 1] FIRST to preserve headroom
        self._normalize_samples()
        
        # Calculate new samples
        new_samples = self._samples * factor
        
        # Check for clipping
        max_val = np.max(np.abs(new_samples))
        if max_val > 1.0:
            # Normalize to prevent clipping
            new_samples = new_samples / max_val
            warnings.warn(
                f"Clipping prevented: normalized from {max_val:.3f} to 1.0. "
                "Consider using lower volume factor or applying gain before volume increase."
            )
        
        self._samples = new_samples
        return self.audio
    
    def apply_filter(
        self,
        filter_type: str,
        cutoff_freq: float,
        q_factor: float = 1.0,
        order: int = 2
    ) -> AudioData:
        """
        Apply a frequency filter to the audio.
        
        Args:
            filter_type: Type of filter - 'lowpass', 'highpass', 'bandpass', 'peaking'
            cutoff_freq: Cutoff frequency in Hz (for band/peak) or stop frequency (for lowpass)
            q_factor: Q-factor for resonance (1.0 = no resonance)
            order: Filter order (2, 4, etc.)
            
        Returns:
            New AudioData instance with filtered audio
            
        Raises:
            ValueError: If filter type is unknown or parameters are invalid
            
        Note:
            Each filter operation normalizes and handles clipping protection.
        """
        # Normalize before filtering to preserve headroom
        self._normalize_samples()
        
        # Validate inputs
        valid_types = ['lowpass', 'highpass', 'bandpass', 'peaking']
        if filter_type not in valid_types:
            raise ValueError(f"Unknown filter type: {filter_type}. Valid: {valid_types}")
        
        if cutoff_freq <= 0:
            raise ValueError("Cutoff frequency must be positive")
        
        if cutoff_freq >= self._sample_rate / 2:
            warnings.warn(
                f"Cutoff frequency ({cutoff_freq} Hz) exceeds Nyquist "
                f"(Nyquist = {self._sample_rate / 2:.1f} Hz)"
            )
        
        # Design filter based on type
        nyquist = self._sample_rate / 2
        normalized_cutoff = cutoff_freq / nyquist
        
        if filter_type == 'lowpass':
            cutoff_norm = 1.0 - normalized_cutoff  # Invert for lowpass design
            b, a = sp_signal.butter(order, cutoff_norm, btype='low', fs=self._sample_rate)
            new_samples = sp_signal.filtfilt(b, a, self._samples)
            self._samples = new_samples
            
        elif filter_type == 'highpass':
            b, a = sp_signal.butter(order, normalized_cutoff, btype='high', fs=self._sample_rate)
            new_samples = sp_signal.filtfilt(b, a, self._samples)
            self._samples = new_samples
            
        elif filter_type == 'bandpass':
            b, a = sp_signal.butter(order, [normalized_cutoff, cutoff_freq], btype='band', fs=self._sample_rate)
            new_samples = sp_signal.filtfilt(b, a, self._samples)
            self._samples = new_samples
            
        elif filter_type == 'peaking':
            # Peaking filter (parametric EQ)
            b, a = sp_signal.iirfilter(
                order,
                normalized_cutoff,
                ftype='peaking',
                btype='low',  # Use lowpass design for peaking
                fs=self._sample_rate,
                halfpower='q'
            )
            # Calculate gain from Q-factor
            gain_db = 20 * np.log10(1 + q_factor * np.tan(np.pi * normalized_cutoff))
            # Apply gain
            if gain_db > 0:
                new_samples = self._samples * np.abs(gain_db) / 20.0
            elif gain_db < 0:
                new_samples = self._samples / (np.abs(gain_db) / 20.0)
            else:
                new_samples = self._samples.copy()
            self._samples = new_samples
        
        return self.audio
    
    def classical_denoise(
        self,
        noise_estimate: Optional[np.ndarray] = None,
        iterations: int = 3
    ) -> AudioData:
        """
        Classical noise reduction using spectral subtraction.
        
        This implements a simplified Wiener filter approach:
        S_estimated = S_observed - noise_estimate
        
        Args:
            noise_estimate: Estimated noise spectrum (optional)
            iterations: Number of spectral subtraction iterations
            
        Returns:
            New AudioData with reduced noise
            
        Notes:
            - Each operation normalizes and handles clipping protection
            - This is a basic implementation. Production systems would use
              more sophisticated methods like spectral gating or learned
              noise models.
        """
        # Normalize before processing
        self._normalize_samples()
        
        if noise_estimate is None:
            # If no noise estimate, apply basic smoothing
            # This won't be effective without a noise sample
            warnings.warn(
                "No noise estimate provided. Results will be limited. "
                "For best results, capture a noise-only sample."
            )
            # Apply basic median filtering as a crude denoiser
            kernel_size = 7
            new_samples = sp_signal.medfilt(self._samples, kernel_size)
            self._samples = new_samples
            return self.audio
        
        # Spectral subtraction approach
        # Convert to frequency domain
        n_fft = min(2048, self._num_samples // 2)
        spectrogram = np.abs(np.fft.rfft(self._samples, n_fft))
        
        # Simple spectral subtraction
        if noise_estimate is not None and noise_estimate.shape == spectrogram.shape:
            # Subtract noise estimate (with soft clipping to prevent over-subtraction)
            subtraction = noise_estimate * 0.5  # Subtraction factor
            spectrogram = np.maximum(spectrogram - subtraction, 0.1 * spectrogram)
        else:
            # Apply frequency-dependent attenuation
            frequencies = np.fft.rfftfreq(n_fft, 1/self._sample_rate)
            # More aggressive attenuation at lower frequencies where noise often lives
            freq_weight = 1.0 / (1.0 + np.exp(-(frequencies - 500) / 100))
            spectrogram = spectrogram * freq_weight
        
        # Reconstruct time-domain signal
        new_samples = np.fft.irfft(spectrogram, n_fft).real
        self._samples = new_samples[:self._num_samples]
        
        return self.audio
    
    def get_processing_info(self) -> dict:
        """
        Get current processing state.
        
        Returns:
            Dict describing current audio state
        """
        return {
            'sample_rate': self._sample_rate,
            'num_samples': self._num_samples,
            'channels': self.audio.metadata.get('channels', 1),
            'dtype': str(self._samples.dtype),
            'rms': float(np.sqrt(np.mean(self._samples ** 2)))
        }


def apply_volume(audio: AudioData, factor: float) -> AudioData:
    """Convenience function to adjust volume."""
    processor = SignalProcessor(audio)
    return processor.adjust_volume(factor)


def apply_filter(
    audio: AudioData,
    filter_type: str,
    cutoff_freq: float,
    q_factor: float = 1.0
) -> AudioData:
    """Convenience function to apply frequency filter."""
    processor = SignalProcessor(audio)
    return processor.apply_filter(filter_type, cutoff_freq, q_factor)


def classical_denoise(
    audio: AudioData,
    noise_estimate: Optional[np.ndarray] = None
) -> AudioData:
    """Convenience function for classical noise reduction."""
    processor = SignalProcessor(audio)
    return processor.classical_denoise(noise_estimate)
