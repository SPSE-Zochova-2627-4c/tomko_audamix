# Audamix

Audamix je maturitný projekt na úpravu lokálnych zvukových súborov. Repozitár má dnes **dve oddelené časti**:

- `audamix/` — funkčné Python jadro a príkazové rozhranie na čítanie, úpravu a zápis audia;
- `src/audamix_frontend/` — samostatný prototyp desktopového rozhrania v PySide6.

**Frontend ešte nie je napojený na audio jadro.** Po výbere existujúceho súboru s podporovanou príponou zobrazí vygenerovaný priebeh a ukážkové metadáta. Transport nevydáva zvuk, efekty menia iba demo históriu a export nevytvára súbor; rozhranie na to upozorní. Skutočnú úpravu a export vykonáva zatiaľ len CLI.

## Aktuálny stav

| Oblasť | Čo je hotové | Hranica |
|---|---|---|
| Dáta | SoundFile načíta/zapíše audio; `AudioData` uchová vzorky a metadáta, vypočíta trvanie, peak, RMS a pomer peak/RMS | Formáty závisia od libsndfile |
| Klasické DSP | Hlasitosť, low-pass, high-pass, band-pass, rezonančný filter a základné odšumenie; validácia vstupov a ochrana pred peakom nad 1 | Odšumenie bez profilu šumu je jednoduchý mediánový filter; filter `peaking` nie je plnohodnotný parametrický EQ |
| AI | DeepFilterNet3 pre reč; voliteľný VoiceFixer cez `declip`; spracovanie lokálne | DeepFilterNet môže pri prvom použití stiahnuť váhy; VoiceFixer nie je povinná závislosť a nie je tu overený |
| Aplikačná vrstva | `AudioProcessor` koordinuje úpravy, výsledky, históriu a jedno-krokové undo | Nie je pripojená k GUI |
| CLI | `info`, `edit` (výpis informácií), `process`, `batch`, `generate-silence`, `demo` | `edit` nie je interaktívny editor; `demo` vyžaduje vstupný súbor |
| Qt frontend | Tmavá/svetlá téma, menu, pohyblivé panely, časová os, stereo demo priebeh, výber, zoom, demo transport, ovládanie stopy, formuláre úprav a stavové hlásenia | `ProjectModel` a `Transport` sú zatiaľ stuby |

Podrobný opis modulov a dátových tokov je v [ARCHITECTURE.md](docs/ARCHITECTURE.md). Funkčné požiadavky a rozdiel medzi plánom a súčasným stavom sú v [SPEC.md](SPEC.md) a [VERIFICATION.md](VERIFICATION.md). Rozhodnutia o nevyplnených častiach zadania sú v [ASSUMPTIONS.md](ASSUMPTIONS.md); vedome vynechané funkcie v [OMISSIONS.md](OMISSIONS.md).

## Štruktúra

```text
audamix/
  main.py                    CLI vstupný bod
  processor.py               aplikačná vrstva a undo
  data/audio_data.py         načítanie, metadáta, export
  dsp/signal_processor.py    klasické spracovanie
  ai/audio_ai.py             voliteľné AI modely
src/audamix_frontend/
  app.py, __main__.py        Qt vstupné body
  model.py                   protokoly a demo backendy
  window.py                  hlavné okno a akcie
  widgets.py                 časová os, waveform, výber
  theme.py, resources/       paleta a QSS
tests/
  test_audio_workflow.py     testy skutočného CLI/DSP toku
  test_frontend.py           pytest-qt testy GUI
  manual_frontend_smoke.py   offscreen smoke test bez pytest-qt
```

## Spustenie CLI so skutočným audiom

Základné CLI a DSP vyžadujú Python 3.11+ a závislosti v `audamix/requirements.txt`. Na Linuxe:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r audamix/requirements.txt
python -m audamix.main info vstup.wav
python -m audamix.main process vstup.wav --filter lowpass --cutoff 2000 --volume 0.8 --output vystup.wav
python -m audamix.main batch --input-dir ./vstup --output-dir ./vystup --volume 0.8
python -m audamix.main generate-silence --duration 2 --output ticho.wav
```

AI denoise nainštalujte samostatne podľa potreby:

```bash
python -m pip install -r audamix/requirements-ai.txt
python -m audamix.main process vstup.wav --denoise --output odsumene.wav
```

**Windows a chyba `Cargo ... is not installed`:** `DeepFilterLib 0.5.6` má na PyPI hotový wheel pre Windows x64 a CPython 3.11, ale nie pre Python 3.14. Na Python 3.14 sa preto pip pokúša zostaviť Rust rozšírenie zo zdrojov. Pre AI denoise je najjednoduchšie vytvoriť samostatné prostredie s Python 3.11 (`py -3.11 -m venv .venv-ai`) a potom spustiť `pip install -r audamix/requirements-ai.txt`. Alternatívou je nainštalovať Rust/Cargo a potrebné build nástroje pre kompiláciu; táto cesta tu nie je overená. Základné `requirements.txt` už Rust nevyžaduje. [Zoznam wheelov DeepFilterLib 0.5.6](https://pypi.org/project/deepfilterlib/0.5.6/).

`--declip` vyžaduje samostatne dostupný VoiceFixer s váhami a nie je súčasťou `requirements-ai.txt`. Neexistujúci model alebo chybný vstup spôsobí chybový návratový kód. `process` odmietne rovnakú vstupnú a výstupnú cestu. Pri pokuse prekročiť amplitúdu 1.0 DSP zníži gain výsledku a vydá varovanie. Výstupný formát sa odvodzuje od prípony súboru.

## Spustenie frontend prototypu

Na Linuxe z koreňa repozitára:

```bash
python3 -m venv .venv-frontend
. .venv-frontend/bin/activate
python -m pip install -e '.[dev]'
python -m audamix_frontend
# alternatíva: audamix-frontend
```

Balík `audamix-frontend` vyžaduje len PySide6. Voliteľné `dev` závislosti slúžia na testy a statické kontroly. Frontend neimportuje `audamix/` ani NumPy. Na Windows aktivujte prostredie cez `.venv-frontend\Scripts\activate`; na macOS platí unixový príkaz. Pre obidve platformy je potrebný kompatibilný Python 3.11+ a Qt 6 dostupné cez PySide6.

Vo frontende zvoľte **File → Open**. Po otvorení ukážkového súboru možno kliknúť alebo ťahať výber v priebehu, zoomovať nástrojom Zoom alebo cez Ctrl + koliesko, spustiť demo transport a skúsiť formuláre efektov. **File → Export** pravdivo oznámi, že audio backend nie je pripojený.

## Testy a overenie

```bash
python -m unittest discover -s tests -p 'test_audio_workflow.py' -v
QT_QPA_PLATFORM=offscreen python tests/manual_frontend_smoke.py
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_frontend.py -q
ruff check src tests/test_frontend.py
mypy --strict src/audamix_frontend
```

Pri poslednom miestnom overení prešlo 5 audio testov, offscreen smoke test, `compileall` a `git diff --check`. `pytest-qt`, `ruff` a `mypy` nebolo možné spustiť, pretože balíky neboli dostupné a prístup k indexu balíkov zlyhal. Tieto kontroly **nie sú potvrdené ako zelené**.

## Čo zostáva

Najbližší integračný krok je implementovať `ProjectModel` a `Transport` nad skutočným audio jadrom, nahradiť generovaný priebeh dátami zo súboru, zmeniť demo efekty na reálne operácie a zapojiť export. Potom treba doplniť testy celého toku podľa `SPEC.md`. Aktuálny stav nie je splnením jej akceptačného kritéria pre desktopovú aplikáciu.
