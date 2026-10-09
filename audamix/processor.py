"""
Audio Processor - Core orchestration and state management.

This module coordinates between the DSP, AI, and data layers,
managing workflow state and non-destructive processing.

Design Rationale:
- Single source of truth for audio state
- Maintains operation history for undo/redo
- Coordinates multiple processing steps safely
- Provides consistent interface to GUI layer
"""

import numpy as np
from typing import List, Optional, Dict, Any
from enum import Enum

from audamix.data.audio_data import AudioData
from audamix.dsp.signal_processor import SignalProcessor
from audamix.ai.audio_ai import AudioAI


class ProcessingStep(Enum):
    """Types of processing operations."""
    VOLUME_ADJUST = 'volume_adjust'
    FILTER_LOWPASS = 'filter_lowpass'
    FILTER_HIGHPASS = 'filter_highpass'
    FILTER_BANDPASS = 'filter_bandpass'
    CLASSICAL_DENOISE = 'classical_denoise'
    AI_DENOISE = 'ai_denoise'
    AI_DECLIPE = 'ai_declipe'


class ProcessingResult:
    """Result of a processing operation."""
    def __init__(
        self,
        success: bool,
        message: str,
        data: Optional[AudioData] = None,
        error: Optional[str] = None
    ):
        self.success = success
        self.message = message
        self.data = data
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'message': self.message,
            'error': self.error,
            'data': self.data.metadata if self.data else None
        }


class AudioProcessor:
    """
    Main audio processing orchestrator.
    
    Manages:
    - Audio data state
    - Processing history for undo/redo
    - Step tracking and progress reporting
    
    Design Philosophy:
    - Non-destructive: All operations create new AudioData instances
    - Stateful: Tracks current operation for undo
    - Progressive: Reports status for each step
    """
    
    def __init__(self) -> None:
        """Initialize processor with empty state."""
        self._current_audio: Optional[AudioData] = None
        self._history: List[Dict[str, Any]] = []
        self._step_count: int = 0
        self._pending_operations: List[tuple] = []
    
    @property
    def current_audio(self) -> Optional[AudioData]:
        """Get current audio data."""
        return self._current_audio
    
    @property
    def processing_history(self) -> List[Dict[str, Any]]:
        """Get processing history."""
        return self._history
    
    @property
    def step_count(self) -> int:
        """Get number of processing steps performed."""
        return self._step_count
    
    def load_audio(self, filepath: str, normalize: bool = False) -> ProcessingResult:
        """
        Load audio from file.
        
        Args:
            filepath: Path to audio file
            normalize: Whether to normalize to [-1, 1]
            
        Returns:
            ProcessingResult with loaded audio (or error)
        """
        try:
            audio = AudioData.load(filepath, normalize)
            self._current_audio = audio
            self._history.append({
                'step': self._step_count,
                'type': 'load',
                'success': True,
                'message': f"Loaded: {audio.metadata.get('filename', 'unknown')}",
                'sample_rate': audio.metadata.get('sample_rate'),
                'channels': audio.metadata.get('channels'),
                'duration': audio.metadata.get('duration')
            })
            self._step_count += 1
            
            return ProcessingResult(
                success=True,
                message=f"Loaded {audio.metadata.get('filename', 'unknown')}",
                data=audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message="Failed to load audio",
                error=str(e)
            )
    
    def adjust_volume(
        self,
        factor: float,
        description: Optional[str] = None
    ) -> ProcessingResult:
        """
        Adjust audio volume.
        
        Args:
            factor: Volume multiplier (> 0)
            description: Operation description
            
        Returns:
            ProcessingResult with adjusted audio
        """
        if self._current_audio is None:
            return ProcessingResult(
                success=False,
                message="No audio loaded",
                error="Call load_audio() first"
            )
        
        try:
            processor = SignalProcessor(self._current_audio)
            result_audio = processor.adjust_volume(factor)
            
            self._current_audio = result_audio
            self._history.append({
                'step': self._step_count,
                'type': 'volume_adjust',
                'success': True,
                'message': f"Volume: x{factor:.2f}",
                'factor': factor
            })
            
            return ProcessingResult(
                success=True,
                message=f"Volume adjusted to x{factor:.2f}",
                data=self._current_audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message="Volume adjustment failed",
                error=str(e)
            )
    
    def apply_filter(
        self,
        filter_type: str,
        cutoff_freq: float,
        q_factor: float = 1.0
    ) -> ProcessingResult:
        """
        Apply frequency filter.
        
        Args:
            filter_type: 'lowpass', 'highpass', 'bandpass', 'peaking'
            cutoff_freq: Cutoff frequency in Hz
            q_factor: Q-factor for resonance
            
        Returns:
            ProcessingResult with filtered audio
        """
        if self._current_audio is None:
            return ProcessingResult(
                success=False,
                message="No audio loaded",
                error="Call load_audio() first"
            )
        
        try:
            processor = SignalProcessor(self._current_audio)
            result_audio = processor.apply_filter(filter_type, cutoff_freq, q_factor)
            
            self._current_audio = result_audio
            self._history.append({
                'step': self._step_count,
                'type': f'filter_{filter_type}',
                'success': True,
                'message': f"{filter_type.capitalize()} @ {cutoff_freq}Hz",
                'filter_type': filter_type,
                'cutoff_freq': cutoff_freq,
                'q_factor': q_factor
            })
            
            return ProcessingResult(
                success=True,
                message=f"Applied {filter_type} filter @ {cutoff_freq}Hz",
                data=self._current_audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message=f"Filter application failed",
                error=str(e)
            )
    
    def denoise_classical(
        self,
        iterations: int = 3
    ) -> ProcessingResult:
        """
        Apply classical noise reduction.
        
        Args:
            iterations: Number of denoising iterations
            
        Returns:
            ProcessingResult with denoised audio
        """
        if self._current_audio is None:
            return ProcessingResult(
                success=False,
                message="No audio loaded",
                error="Call load_audio() first"
            )
        
        try:
            processor = SignalProcessor(self._current_audio)
            result_audio = processor.classical_denoise(iterations=iterations)
            
            self._current_audio = result_audio
            self._history.append({
                'step': self._step_count,
                'type': 'classical_denoise',
                'success': True,
                'message': f"Classical denoise (iterations={iterations})"
            })
            
            return ProcessingResult(
                success=True,
                message="Classical noise reduction applied",
                data=self._current_audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message="Classical denoise failed",
                error=str(e)
            )
    
    def denoise_ai(
        self,
        threshold: float = 0.01,
        strength: float = 0.5
    ) -> ProcessingResult:
        """
        Apply AI-based noise reduction.
        
        Args:
            threshold: Noise threshold
            strength: Reduction strength
            
        Returns:
            ProcessingResult with AI-denoised audio
        """
        if self._current_audio is None:
            return ProcessingResult(
                success=False,
                message="No audio loaded",
                error="Call load_audio() first"
            )
        
        try:
            ai = AudioAI()
            result_audio, message = ai.denoise(
                self._current_audio,
                threshold=threshold,
                strength=strength
            )
            
            self._current_audio = result_audio
            self._history.append({
                'step': self._step_count,
                'type': 'ai_denoise',
                'success': True,
                'message': message
            })
            
            return ProcessingResult(
                success=result_audio.metadata.get('denoised', False),
                message=message,
                data=self._current_audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message="AI denoise failed",
                error=str(e)
            )
    
    def declipe(
        self,
        confidence: float = 0.7
    ) -> ProcessingResult:
        """
        Apply clipping recovery.
        
        Args:
            confidence: Recovery confidence level
            
        Returns:
            ProcessingResult with recovered audio
        """
        if self._current_audio is None:
            return ProcessingResult(
                success=False,
                message="No audio loaded",
                error="Call load_audio() first"
            )
        
        try:
            ai = AudioAI()
            result_audio, message = ai.declipe(
                self._current_audio,
                confidence=confidence
            )
            
            self._current_audio = result_audio
            self._history.append({
                'step': self._step_count,
                'type': 'ai_declipe',
                'success': True,
                'message': message
            })
            
            return ProcessingResult(
                success=result_audio.metadata.get('declipped', False),
                message=message,
                data=self._current_audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message="Clipping recovery failed",
                error=str(e)
            )
    
    def undo(self) -> ProcessingResult:
        """
        Undo last operation.
        
        Returns:
            ProcessingResult indicating success
        """
        if not self._history:
            return ProcessingResult(
                success=False,
                message="Nothing to undo"
            )
        
        self._history.pop()
        
        if hasattr(self, '_current_audio'):
            prev_result = self._history[-1] if self._history else None
            if prev_result and 'data' in prev_result:
                self._current_audio = prev_result['data']
        
        return ProcessingResult(
            success=True,
            message="Undo completed"
        )
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get current processing state.
        
        Returns:
            Dict with audio info and processing history
        """
        info: Dict[str, Any] = {
            'current_audio': None,
            'history': self._history,
            'step_count': self._step_count
        }
        
        if self._current_audio:
            info['current_audio'] = self._current_audio.get_info()
        
        return info
    
    def save(self, filepath: str, format: Optional[str] = None) -> ProcessingResult:
        """
        Save current audio to file.
        
        Args:
            filepath: Output file path
            format: Output format (optional, inferred from extension)
            
        Returns:
            ProcessingResult with save status
        """
        if self._current_audio is None:
            return ProcessingResult(
                success=False,
                message="No audio to save",
                error="Nothing loaded"
            )
        
        try:
            self._current_audio.save(filepath, format=format)
            self._history.append({
                'step': self._step_count,
                'type': 'save',
                'success': True,
                'message': f"Saved to {filepath}"
            })
            
            return ProcessingResult(
                success=True,
                message=f"Saved to {filepath}",
                data=self._current_audio
            )
            
        except Exception as e:
            return ProcessingResult(
                success=False,
                message="Save failed",
                error=str(e)
            )


def create_processor(audio: Optional[AudioData] = None) -> AudioProcessor:
    """Create a processor, optionally initialized with already loaded audio."""
    processor = AudioProcessor()
    if audio is not None:
        processor._current_audio = audio
    return processor
