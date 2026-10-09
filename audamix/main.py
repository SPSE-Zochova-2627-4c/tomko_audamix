#!/usr/bin/env python3
"""
Audamix - Audio Editor for Desktop Linux

A cross-platform audio editor focused on:
- Non-destructive editing
- Classical and AI-based processing
- Clean, responsive UI

Usage:
    python main.py <command> [options]
    
Commands:
    edit <filepath>           Open audio file in editor
    info <filepath>           Show file metadata
    process <filepath>        Apply processing pipeline
    batch <input_dir> <output_dir>    Process directory of files
    generate-silence         Create silence file
    demo                      Run demonstration mode
    
Examples:
    python main.py edit audio.wav
    python main.py process audio.wav --denoise --filter lowpass 2000
    python main.py info audio.wav
    python main.py batch ./input ./output --denoise
"""

import sys
import os
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import tempfile
import traceback

from audamix.processor import AudioProcessor, create_processor
from audamix.data.audio_data import AudioData
from audamix.dsp.signal_processor import SignalProcessor
from audamix.ai.audio_ai import AudioAI


def command_edit(filepath: str, normalize: bool = False) -> None:
    """Open audio file for editing."""
    try:
        print(f"Loading: {filepath}")
        audio = AudioData.load(filepath, normalize=normalize)
        
        print(f"Loaded successfully!")
        print(f"  Sample rate: {audio.metadata.get('sample_rate', 'N/A')} Hz")
        print(f"  Channels: {audio.metadata.get('channels', 'N/A')}")
        print(f"  Duration: {audio.metadata.get('duration', 'N/A')} s")
        
        processor = create_processor(audio)
        
        # Show audio info
        print(f"\nAudio Properties:")
        print(f"  Peak: {audio.get_peak():.4f}")
        print(f"  RMS: {audio.get_rms():.4f}")
        print(f"  DR: {audio.get_dr():.1f} dB")
        print(f"  Headroom: {(1 - audio.get_peak()) * 100:.1f} dB")
        
    except Exception:
        print("Error loading file.")
        traceback.print_exc()


def command_info(filepath: str) -> None:
    """Show file metadata."""
    try:
        audio = AudioData.load(filepath)
        
        print(f"Metadata:")
        print(f"  Sample rate: {audio.metadata.get('sample_rate', 'N/A')} Hz")
        print(f"  Channels: {audio.metadata.get('channels', 'N/A')}")
        print(f"  Duration: {audio.metadata.get('duration', 'N/A')} s")
        print(f"  Bit depth: {audio.metadata.get('bits_per_sample', 'N/A')} bits")
        print(f"  Format: {audio.metadata.get('format', 'N/A')}")
        
    except Exception:
        print("Error reading file.")
        traceback.print_exc()


def command_process(filepath: str, denoise: bool = False, filter: str = None, 
                    volume: float = 1.0, output: str = None) -> None:
    """Apply processing pipeline."""
    try:
        audio = AudioData.load(filepath)
        processor = create_processor(audio)
        
        print(f"Processing: {filepath}")
        
        # Denoise
        if denoise:
            print("Applying AI denoising...")
            audio, status = AudioAI().denoise(audio, threshold=0.01)
            print(f"  Status: {status}")
        
        # Filter
        if filter:
            print(f"Applying filter: {filter}")
            processor = SignalProcessor(audio)
            audio = processor.apply_filter(filter, cutoff_freq=2000)
        
        # Volume
        if volume != 1.0:
            print(f"Adjusting volume to {volume}x")
            processor = SignalProcessor(audio)
            audio = processor.adjust_volume(volume)
        
        # Save
        if output:
            audio.save(output)
            print(f"Saved to: {output}")
        else:
            print("No output file specified.")
            
    except Exception:
        print("Error processing file.")
        traceback.print_exc()


def command_batch(input_dir: str, output_dir: str, denoise: bool = False,
                  filter: str = None, volume: float = 1.0) -> None:
    """Batch process directory of files."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        for filename in os.listdir(input_dir):
            if filename.endswith(('.wav', '.flac', '.mp3')):
                filepath = os.path.join(input_dir, filename)
                output_path = os.path.join(output_dir, filename)
                command_process(filepath, denoise, filter, volume, output_path)
        
        print(f"Batch processing complete.")
            
    except Exception:
        print("Error in batch processing.")
        traceback.print_exc()


def command_generate_silence(output: str, duration: int = 10, 
                              sample_rate: int = 44100) -> None:
    """Generate silence file."""
    try:
        # Create silence samples
        n_samples = sample_rate * duration
        samples = np.zeros(n_samples, dtype=np.float32)
        metadata = {'sample_rate': sample_rate, 'channels': 2, 'duration': duration}
        
        audio = AudioData(samples, metadata)
        audio.save(output)
        
        print(f"Generated: {output}")
        print(f"  Duration: {duration} s")
        print(f"  Sample rate: {sample_rate} Hz")
            
    except Exception:
        print("Error generating silence file.")
        traceback.print_exc()


def command_demo() -> None:
    """Run demonstration mode."""
    print("\n" + "=" * 50)
    print("AUDAMIX DEMO MODE")
    print("=" * 50)
    
    print("\n1. Loading sample audio...")
    audio = AudioData.load("demo_audio.wav")
    
    print("\n2. Audio properties:")
    print(f"   Peak: {audio.get_peak():.4f}")
    print(f"   RMS: {audio.get_rms():.4f}")
    print(f"   Headroom: {(1 - audio.get_peak()) * 100:.1f} dB")
    
    print("\n3. Applying denoising...")
    audio, status = AudioAI.denoise(audio)
    print(f"   Status: {status}")
    
    print("\n4. Applying volume increase...")
    processor = SignalProcessor(audio)
    audio = processor.adjust_volume(1.5)
    print(f"   Volume increased to 1.5x")
    
    print("\n5. Saving processed audio...")
    audio.save("demo_output.wav")
    print("   Saved: demo_output.wav")
    
    print("\n" + "=" * 50)
    print("Demo complete!")
    print("=" * 50 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Audamix - Audio Editor for Desktop Linux"
    )
    
    parser.add_argument("command", choices=["edit", "info", "process", "batch", 
                                            "generate-silence", "demo"],
                        help="Command to run")
    
    parser.add_argument("filepath", nargs="?", help="Input audio file path")
    
    parser.add_argument("--denoise", action="store_true",
                        help="Apply AI denoising")
    
    parser.add_argument("--filter", type=str,
                        help="Filter type (e.g., lowpass, highpass)")
    
    parser.add_argument("--volume", type=float, default=1.0,
                        help="Volume adjustment (default: 1.0)")
    
    parser.add_argument("--output", type=str,
                        help="Output file path")
    
    parser.add_argument("--input-dir", type=str,
                        help="Input directory for batch processing")
    
    parser.add_argument("--output-dir", type=str,
                        help="Output directory for batch processing")
    
    parser.add_argument("--duration", type=int, default=10,
                        help="Duration for silence generation (seconds)")
    
    parser.add_argument("--sample-rate", type=int, default=44100,
                        help="Sample rate for silence generation")
    
    args = parser.parse_args()
    
    # Route to appropriate command
    if args.command == "edit":
        command_edit(args.filepath, normalize=True)
    
    elif args.command == "info":
        command_info(args.filepath)
    
    elif args.command == "process":
        command_process(
            args.filepath,
            denoise=args.denoise,
            filter=args.filter,
            volume=args.volume,
            output=args.output
        )
    
    elif args.command == "batch":
        command_batch(
            args.input_dir,
            args.output_dir,
            denoise=args.denoise,
            filter=args.filter,
            volume=args.volume
        )
    
    elif args.command == "generate-silence":
        command_generate_silence(
            args.output,
            duration=args.duration,
            sample_rate=args.sample_rate
        )
    
    elif args.command == "demo":
        command_demo()


if __name__ == "__main__":
    main()
