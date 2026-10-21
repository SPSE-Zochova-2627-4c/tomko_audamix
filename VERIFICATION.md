# Overenie

Aktuálne GUI sa spúšťa priamo príkazom `python audamix.py` a používa skutočné audio adaptéry. `ProjectModel` a `Transport` zostávajú protokolmi; demo implementácie zostali pre izolované použitie.

Overené lokálne na Linuxe s Python 3.14, PySide6 6.12, NumPy 2.5.4, SciPy 1.18.1 a SoundFile 0.14:

- `QT_QPA_PLATFORM=offscreen timeout 2s .venv/bin/python audamix.py`: okno sa inicializovalo bez chýb a bez runtime výpisu; proces skončil iba kvôli testovaciemu timeoutu.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_frontend.py -q`: 6 testov, vrátane načítania platného WAV, gain efektu, undo, exportu, zoomu, pauzy a nastavení.
- `.venv/bin/python -m unittest discover -s tests -p test_audio_workflow.py -q`: 5 testov jadra a CLI.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python tests/manual_frontend_smoke.py`: prešiel bez výpisu varovaní; upozornenie DSP sa zobrazí v stavovom riadku GUI.
- `.venv/bin/mypy --strict src/audamix_frontend`: bez nálezov. Staršie audio jadro je v tejto kontrole externé cez `follow_imports = skip`.
- `.venv/bin/ruff check src tests/test_frontend.py`: bez nálezov.

Skutočný zvukový výstup a voliteľné AI modely nie sú v offscreen prostredí overené.
