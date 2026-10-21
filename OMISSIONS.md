# Vedome vynechané funkcie

| Funkcia Audacity | Dôvod |
|---|---|
| Nahrávanie, výber zariadenia a recording meter | Frontend nemá capture/audio vrstvu; záznam je v `SPEC.md` budúce rozšírenie. |
| Strih, copy/paste, trim, silence, envelope/draw | Prvá verzia špecifikácie tieto editačné nástroje nevyžaduje. |
| Viac stôp, label tracks, MIDI a spectrogram | Mimo prvej verzie alebo bez zodpovedajúceho dátového modelu. |
| Plugin manager, Generate/Analyze menu, macros, scripting | Špecifikácia neobsahuje pluginový alebo automatizačný systém. |
| Cloud/sync, audio.com, rozsiahle Preferences | Aplikácia má pracovať lokálne; nastavenia aktuálne rieši `QSettings`. |
| Skutočné prehrávanie, DSP/AI a export v GUI | Frontend-only hranica zadania; protokoly majú zatiaľ stuby. |

Existujúce CLI s reálnym spracovaním zostáva k dispozícii oddelene. Vynechanie z GUI neznamená, že všetky tieto funkcie neexistujú v jadre.
