# Audamix

Audamix je jednoduchý desktopový editor lokálnych audio súborov. Hlavné okno sa spúšťa **priamo cez `python audamix.py`** z koreňa repozitára. Rozhranie používa PySide6, audio načítava a zapisuje cez SoundFile, klasické úpravy vykonáva pomocou NumPy/SciPy a prehráva cez Qt Multimedia.

## Spustenie

Linux (Python 3.11+):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r audamix/requirements.txt
python audamix.py
```

Windows (PowerShell):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r audamix\requirements.txt
python audamix.py
```

Na macOS použite linuxové príkazy; Python môžete spustiť ako `python3`. Príkazy spúšťajte v priečinku, kde leží `audamix.py`. Pre AI odšumenie nainštalujte navyše `python -m pip install -r audamix/requirements-ai.txt`. DeepFilterNet na Windows s Pythonom 3.14 môže vyžadovať Rust/Cargo, preto je pre túto voliteľnú funkciu odporúčaný Python 3.11. AI declip potrebuje zvlášť nainštalovaný VoiceFixer a jeho model; ak chýba, rozhranie zobrazí chybu bez zmeny audia.

## Použitie

1. **File → Open** otvorí WAV, FLAC, OGG/Opus, AIFF, AU, CAF alebo MP3;
   priebeh a metadáta pochádzajú zo skutočného súboru. Súbor možno do okna
   aj pretiahnuť (drag-and-drop); pri viacerých súboroch sa otvorí prvý
   podporovaný.
2. Kliknutím do priebehu umiestnite kurzor, ťahaním označíte úsek. Ak je úsek
   označený, **Play** prehrá iba tento výber a po jeho konci sa
   automaticky zastaví; bez výberu prehrávanie pokračuje cez celú stopu. Ctrl
   + koliesko alebo tlačidlá Zoom menia mierku, koliesko posúva čas.
3. **Transport → Play** spustí audio a **Stop** ho zastaví cez systémový výstup. Stopa má Mute, Solo, Gain a Pan. Pri jednej stope Solo nemení výsledný zvuk.
4. **Effects** ponúka gain, low-pass, high-pass, band-pass, základné odšumenie a voliteľné AI operácie. Efekty momentálne spracujú celú stopu aj keď je označený úsek; **Edit → Undo** vracia poslednú úpravu.
5. **File → Export** uloží výsledok do nového audio súboru. Export zohľadní Mute, Gain a Pan. Pôvodný vstupný súbor sa nedá prepísať cez Export.

Podporované formáty čítania a zápisu sú WAV, FLAC, OGG/Opus, AIFF, AU, CAF a
MP3; konkrétne kodeky závisia od nainštalovaného `libsndfile`. Dialóg exportu
ponúka voľbu formátu podľa prípony. Náhľadové WAV súbory vznikajú v dočasnom
adresári.

## Projekt

- `audamix.py` — priamy štart desktopovej aplikácie.
- `src/audamix_frontend/` — Qt okno, widgety, téma, protokoly a reálne adaptéry na audio jadro.
- `audamix/data/`, `audamix/dsp/`, `audamix/ai/` — načítanie, klasické DSP a voliteľné AI.
- `audamix/main.py` — samostatné príkazové rozhranie, napr. `python -m audamix.main info vstup.wav`.
- `tests/` — testy GUI a audio toku.

Rozhodnutia a hranice implementácie sú v [ASSUMPTIONS.md](ASSUMPTIONS.md), [OMISSIONS.md](OMISSIONS.md) a [VERIFICATION.md](VERIFICATION.md).

## Testy

```bash
python -m pip install pytest pytest-qt ruff mypy
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_frontend.py -q
python -m unittest discover -s tests -p test_audio_workflow.py -v
QT_QPA_PLATFORM=offscreen python tests/manual_frontend_smoke.py
ruff check src tests/test_frontend.py
mypy --strict src/audamix_frontend
```

Bez zobrazovača použite `QT_QPA_PLATFORM=offscreen`; skutočné prehrávanie potom neoveríte, pretože chýba audio zariadenie. Pri `classical_denoise` stavový riadok upozorní, že bez profilu šumu jadro používa jednoduchý mediánový filter.
