"""Command-line workflows for Audamix. Run with ``python -m audamix.main``."""

import argparse
import os
import sys

import numpy as np

from audamix.data.audio_data import AudioData, SUPPORTED_AUDIO_EXTENSIONS
from audamix.dsp.signal_processor import SignalProcessor


def command_info(filepath: str) -> None:
    audio = AudioData.load(filepath)
    info = audio.get_info()
    for key in ("filename", "duration", "sample_rate", "channels", "sample_count", "bits_per_sample", "format"):
        print(f"{key}: {info.get(key, 'N/A')}")
    print(f"peak: {audio.get_peak():.4f}")
    print(f"RMS: {audio.get_rms():.4f}")
    print(f"peak/RMS: {audio.get_dr():.1f} dB")


def command_process(filepath: str, output: str | None = None, *, denoise: bool = False,
                    filter_type: str | None = None, cutoff: float = 2000,
                    volume: float = 1.0, declip: bool = False) -> None:
    if output and os.path.abspath(filepath) == os.path.abspath(output):
        raise ValueError("Output must differ from the input file")
    audio = AudioData.load(filepath)
    if denoise or declip:
        try:
            from audamix.ai.audio_ai import AudioAI
        except ImportError as exc:
            raise RuntimeError(
                "AI dependencies are missing. Install audamix/requirements-ai.txt."
            ) from exc
    if denoise:
        audio, status = AudioAI().denoise(audio)
        print(status)
    if declip:
        audio, status = AudioAI().declip(audio)
        print(status)
    if filter_type:
        audio = SignalProcessor(audio).apply_filter(filter_type, cutoff)
    if volume != 1.0:
        audio = SignalProcessor(audio).adjust_volume(volume)
    if output:
        audio.save(output)
        print(f"Saved to: {output}")
    else:
        print("No output file specified; result was not saved.")


def command_batch(input_dir: str, output_dir: str, **options) -> None:
    if os.path.abspath(input_dir) == os.path.abspath(output_dir):
        raise ValueError("Input and output directories must differ")
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for filename in sorted(os.listdir(input_dir)):
        if filename.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS):
            command_process(os.path.join(input_dir, filename),
                            os.path.join(output_dir, filename), **options)
            count += 1
    print(f"Processed {count} file(s).")


def command_generate_silence(output: str, duration: int = 10, sample_rate: int = 44100) -> None:
    if duration <= 0 or sample_rate <= 0:
        raise ValueError("Duration and sample rate must be positive")
    audio = AudioData()
    audio.samples = np.zeros((duration * sample_rate, 2), dtype=np.float32)
    audio.metadata = {"sample_rate": sample_rate, "channels": 2, "duration": duration}
    audio.save(output)
    print(f"Generated: {output}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Audamix audio editor")
    parser.add_argument("command", choices=("edit", "info", "process", "batch", "generate-silence", "demo"))
    parser.add_argument("filepath", nargs="?", help="Input audio file, or demo audio file")
    parser.add_argument("--input-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--output")
    parser.add_argument("--denoise", action="store_true")
    parser.add_argument("--declip", action="store_true")
    parser.add_argument("--filter", choices=("lowpass", "highpass", "bandpass", "peaking"))
    parser.add_argument("--cutoff", type=float, default=2000, help="Filter frequency in Hz")
    parser.add_argument("--volume", type=float, default=1.0)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--sample-rate", type=int, default=44100)
    args = parser.parse_args(argv)
    options = dict(denoise=args.denoise, declip=args.declip, filter_type=args.filter,
                   cutoff=args.cutoff, volume=args.volume)
    if args.command in ("edit", "info", "process") and not args.filepath:
        parser.error("This command requires an audio filepath")
    if args.command == "batch" and (not args.input_dir or not args.output_dir):
        parser.error("batch requires --input-dir and --output-dir")
    if args.command == "generate-silence" and not args.output:
        parser.error("generate-silence requires --output")
    try:
        if args.command in ("edit", "info"):
            command_info(args.filepath)
        elif args.command == "process":
            command_process(args.filepath, args.output, **options)
        elif args.command == "batch":
            command_batch(args.input_dir, args.output_dir, **options)
        elif args.command == "generate-silence":
            command_generate_silence(args.output, args.duration, args.sample_rate)
        else:
            if not args.filepath:
                parser.error("demo requires an audio filepath")
            command_process(args.filepath, args.output or "demo_output.wav", volume=1.5)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Audamix: {exc}\n")


if __name__ == "__main__":
    main()
