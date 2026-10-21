# Architektúra a implementovaný stav

Tento dokument opisuje aktuálny kód v repozitári, nie cieľový stav zo `SPEC.md`. Qt rozhranie používa existujúcu dátovú a DSP vrstvu cez adaptéry; AI zostáva voliteľné.

## Tok skutočného audia

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

`audamix/processor.py` koordinuje načítanie, operácie, export a `ProcessingResult` s úspechom, správou a chybou. Uchováva históriu a predchádzajúce objekty pre jedno-krokové návraty cez `undo`. Názov operácie je všade `declip`. GUI používa vlastný adaptér `AudioProject` nad rovnakými `AudioData` a `SignalProcessor`; CLI používa `AudioProcessor`.

`audamix/main.py` je CLI pre `info`, `edit`, `process`, `batch`, `generate-silence` a `demo`. `edit` vypisuje údaje, nemá interaktívne ovládanie. `process` reťazí AI denoise, declip, filter a hlasitosť v tomto poradí. `--cutoff` je frekvencia v Hz. `batch` prejde podporované prípony v adresári. Chyby sa vypíšu a vrátia nenulový kód. Vstup sa nesmie zapísať na tú istú cestu ako výstup.

## Tok desktopovej aplikácie

```text
python audamix.py → QApplication → MainWindow
QAction / myš / klávesnica → ProjectModel / Transport (protokoly)
→ AudioProject (AudioData + SignalProcessor) / AudioTransport (Qt Multimedia)
→ TrackSnapshot / QPainter alebo dočasný WAV / QMediaPlayer
```

`src/audamix_frontend/model.py` definuje protokoly a izolované stuby. Predvolená aplikácia používa `real_backend.py`: `AudioProject` dekóduje lokálny súbor, uchováva históriu pre undo, vytvára peak/RMS dáta pre každý kanál, volá DSP alebo voliteľný AI model a exportuje výsledok. `AudioTransport` vytvára Qt Multimedia prehrávač až pri prvom prehratí a hrá náhľadový WAV. `set_controls` mení Mute, Gain a Pan náhľadu aj exportu; Solo pri jednej stope nemení audio.

`window.py` vytvára `QMainWindow`, zdieľané `QAction` objekty, dialógy a stavový riadok. Efekty spúšťa v `QThread` s indikátorom priebehu. Počas efektu blokuje konfliktné akcie a zatvorenie okna. `QSettings` ukladá geometriu, rozloženie panelov a tému.

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
| Play/stop / pause | Space / P |
| Začiatok / koniec | Home / End |

V GUI nie sú nahrávanie, strih ani kopírovanie, preto ich skratky neexistujú. Akcie sa vypnú, keď bez načítanej stopy alebo výberu nedávajú zmysel. Mute, Gain a Pan ovplyvňujú náhľad aj export; Solo pri jednej stope nemá efekt.

## Testy a známe hranice

`tests/test_audio_workflow.py` overuje jadro a CLI. `tests/test_frontend.py` testuje GUI, zoom, QSettings, reálny gain, undo a export. `tests/manual_frontend_smoke.py` spúšťa offscreen GUI s platným WAV. Aktuálne príkazy a výsledky sú v `VERIFICATION.md`.

Skutočné prehrávanie cez systémové zariadenie a AI modely nie sú v headless prostredí overené. GUI stále spracúva iba jednu stopu a efekty sa aplikujú na celú stopu.
