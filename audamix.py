"""Run the Audamix desktop app directly: python audamix.py."""

from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    try:
        from audamix_frontend.app import main
    except ModuleNotFoundError as exc:
        if exc.name in {"PySide6", "numpy", "scipy", "soundfile"}:
            raise SystemExit(
                f"Missing dependency {exc.name}. Install with: "
                "python -m pip install -r audamix/requirements.txt"
            ) from exc
        raise
    raise SystemExit(main())
