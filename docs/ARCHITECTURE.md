# Architektúra a implementovaný stav

Tento dokument opisuje aktuálny kód v repozitári, nie cieľový stav zo `SPEC.md`. Audio jadro a Qt rozhranie sú zatiaľ oddelené. Žiadny klik v GUI nespustí reálne DSP ani AI spracovanie.

## Tok skutočného audia: CLI

```text
lokálny súbor
  → AudioData.load (SoundFile + NumPy pole)
  → SignalProcessor alebo AudioAI
  → nový AudioData s metadátami
  → AudioData.save (SoundFile)
```

`audamix/data/audio_data.py` načíta mono ako 1D pole a viackanálové audio ako pole `(frames, channels)`. Uchová názov, frekvenciu, počet kanálov, formát, subtype, dostupnú bitovú hĺbku a trvanie. Bez požiadavky na normalizáciu ponechá pôvodnú úroveň. `get_peak`, `get_rms` a `get_dr` poskytujú základné metriky. `save` zapíše aktuálne vzorky; predvolený formát určuje prípona výstupu.

`audamix/dsp/signal_processor.py` berie `AudioData` a vracia nový objekt bez zmeny vstupu. Gain je násobok amplitúdy. Low-pass a high-pass používajú Hz; band-pass vytvorí interval okolo stredu podľa Q. Vetva `peaking` používa rezonančný `iirpeak`, teda nejde o plnohodnotný parametrický EQ s nastaviteľným gainom. Filtre pracujú po kanáloch. Pri prekročení peaku 1.0 sa výsledok zníži a Python vydá varovanie. Klasické odšumenie bez dodaného profilu šumu používa opakovaný mediánový filter; s profilom používa STFT a frekvenčné potlačenie. Je to jednoduchá implementácia, nie produkčný odšumovač.

`audamix/ai/audio_ai.py` poskytuje `AudioAI.denoise` cez lokálne predtrénovaný DeepFilterNet3 a `AudioAI.declip` cez voliteľný VoiceFixer. Konvertuje rozloženie kanálov, podľa potreby prevzorkuje a po spracovaní obnoví pôvodný počet vzoriek a metadáta. AI denoise je určený najmä na reč. Parametre `threshold`, `strength` a `confidence` zostali v API, ale model ich v súčasnosti nepoužíva. VoiceFixer nie je povinnou závislosťou; bez neho sa declip odmietne. Dostupnosť váh a kvalita výsledku tu nie sú overené. Základné CLI načítava AI modul až pri AI operácii, takže `requirements.txt` nevyžaduje Torch ani Rust; voliteľné závislosti sú v `requirements-ai.txt`.

`audamix/processor.py` koordinuje načítanie, operácie, export a `ProcessingResult` s úspechom, správou a chybou. Uchováva históriu a predchádzajúce objekty pre jedno-krokové návraty cez `undo`. Názov operácie je všade `declip`. GUI túto triedu zatiaľ nepoužíva.

`audamix/main.py` je CLI pre `info`, `edit`, `process`, `batch`, `generate-silence` a `demo`. `edit` vypisuje údaje, nemá interaktívne ovládanie. `process` reťazí AI denoise, declip, filter a hlasitosť v tomto poradí. `--cutoff` je frekvencia v Hz. `batch` prejde podporované prípony v adresári. Chyby sa vypíšu a vrátia nenulový kód. Vstup sa nesmie zapísať na tú istú cestu ako výstup.

## Tok frontend prototypu

```text
QAction / myš / klávesnica
  → MainWindow
  → ProjectModel alebo Transport (typing.Protocol)
  → StubProject / StubTransport
  → TrackSnapshot / stav
  → QWidget + QPainter
```

`src/audamix_frontend/model.py` definuje protokoly a ukážkové implementácie. `StubProject.open_file` kontroluje iba existenciu súboru a príponu WAV/FLAC/OGG/AIFF; obsah **nedekóduje**. Vytvorí 90-sekundový dvojkanálový priebeh s ukážkovými hodnotami 44 100 Hz a 3 969 000 vzoriek. `apply_effect` zvýši revíziu a demo históriu, no nemení vzorky. `undo` obnoví predchádzajúci snapshot. `export_file` vždy vráti zrozumiteľnú chybu a nič nezapíše. `StubTransport` mení iba časovú pozíciu; nevydáva zvuk. Track gain, pan, mute a solo sa odovzdávajú cez `set_controls`, ale nemajú zvukový účinok.

`window.py` vytvára jedno `QMainWindow`, zdieľané `QAction` objekty pre menu, panely a skratky, výber súboru, stav akcií, stavový riadok, formuláre úprav a simulovaný priebeh operácie. Počas demo efektu ukáže neurčitý indikátor na 200 ms. Qt vlastní widgety cez rodičov; `QTimer` je dieťaťom hlavného okna. `QSettings` ukladá geometriu, veľkosť, rozloženie panelov a svetlú/tmavú tému.

`widgets.py` obsahuje `ViewState` na prevod času a pixelov, `TimelineRuler`, `WaveformView` a `SelectionBar`. Časová os prispôsobí hustotu značiek zoomu. Waveform a časová os vytvoria `QPixmap` pri zmene veľkosti, dát, témy či zoomu; bežný `paintEvent` kreslí cache, výber a playhead. Výber vzniká kliknutím/ťahaním. Nástroj Zoom priblíži ľavým a oddiali pravým klikom. Koliesko posúva, Ctrl + koliesko približuje okolo kurzora. Stereo kanály sú zobrazené oddelene.

`theme.py` drží farby tmavej aj svetlej témy, nastavuje `QPalette` a dopĺňa hodnoty do `resources/dark.qss`. Súbor QSS slúži ako spoločná šablóna aj pre svetlú tému; názov súboru je historický. Používané farby widgetov pochádzajú z `theme.py`.

## Ovládanie a klávesy

| Akcia | Skratka |
|---|---|
| Otvoriť / exportovať | Ctrl+O / Ctrl+Shift+E |
| Undo | Ctrl+Z |
| Vybrať všetko / zrušiť výber | Ctrl+A / Esc |
| Priblížiť / oddialiť | Ctrl+1 / Ctrl+3 |
| Prispôsobiť výber / projekt | Ctrl+E / Ctrl+F |
| Demo play/stop / pause | Space / P |
| Začiatok / koniec | Home / End |

V GUI nie sú nahrávanie, strih ani kopírovanie, preto ich skratky neexistujú. Akcie sa vypnú, keď bez načítanej demo stopy alebo výberu nedávajú zmysel. Mute, Solo, Gain a Pan v paneli sú UI stav.

## Testy a známe hranice

`tests/test_audio_workflow.py` testuje zmenu vzoriek bez mutácie vstupu, frekvencie filtrov, stereo, undo, declip volanie a export. `tests/test_frontend.py` obsahuje pytest-qt testy vytvorenia okna, stavov akcií, výberu/zoomu a QSettings. `tests/manual_frontend_smoke.py` overí tie isté základné GUI toky v offscreen režime bez pytest-qt. V miestnom offline prostredí prešlo 5 audio testov a manuálny Qt smoke test; pytest-qt, ruff a mypy chýbali a nebolo ich možné doinštalovať. Statické brány a pytest-qt testy preto zostávajú neoverené.

Zostáva zapojiť skutočné backendy za `ProjectModel` a `Transport`, dekódovať súbor pre metadáta a waveform, vykonávať efekty a export, a doplniť end-to-end testy. Staršia špecifikácia vyžaduje viac, než dnes poskytuje oddelený frontend prototyp.
