# Vedome vynechané funkcie

| Funkcia | Dôvod |
|---|---|
| Viac stôp, label tracks, MIDI a spectrogram | Dátový model GUI uchováva jednu audio stopu. |
| Nahrávanie, vstupné zariadenia a recording meter | Nahrávanie je v `SPEC.md` budúce rozšírenie; chýba capture vrstva. |
| Strih, copy/paste, trim, silence, envelope/draw, redo a loop | Nie sú implementované v aktuálnom GUI a jeho audio adaptéri. |
| Efekt iba na označenom úseku | Súčasné DSP operácie spracujú celý `AudioData`. |
| Playback meter, export MP3 a výber výstupného zariadenia | Nie sú napojené na súčasný jednoduchý transport/export. |
| Plugin manager, Generate/Analyze, macros, scripting | Špecifikácia neobsahuje pluginový ani automatizačný systém. |
| Cloud/sync, audio.com, rozsiahle Preferences | Projekt spracúva lokálne súbory; jednoduché nastavenia ukladá `QSettings`. |

AI denoise vyžaduje voliteľný DeepFilterNet; declip vyžaduje voliteľný VoiceFixer a jeho model. Bez nich príslušné akcie zlyhajú so správou a nenechajú zmenené audio.
