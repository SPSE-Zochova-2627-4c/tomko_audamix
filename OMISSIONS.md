# Vedome vynechané funkcie

Implementované z pôvodného zoznamu: strih (Cut/Delete/Trim), Copy/Paste, Silence, Redo, loop, efekty iba na označenom úseku, Fade In/Out, Generate (tón, ticho, šum), Analyze (štatistiky), spektrogram, label track, playback meter, export MP3 a výber výstupného zariadenia, základné Preferences a 14 efektov ako v Audacity (Normalize, Compressor, Limiter, Noise Gate, Bass and Treble, Parametric EQ, Notch, Echo, Phaser, Wahwah, Tremolo, Distortion, Invert, Reverse).

| Funkcia | Dôvod |
|---|---|
| Viac stôp, MIDI | Dátový model GUI uchováva jednu audio stopu; MIDI nie je v `SPEC.md`. |
| Nahrávanie, vstupné zariadenia a recording meter | Nahrávanie je v `SPEC.md` budúce rozšírenie; chýba capture vrstva. |
| Envelope/draw nástroj | Nahradený Fade In/Out; voľné kreslenie obálky ani vzoriek nie je implementované. |
| Efekty meniace dĺžku (Change Speed/Tempo/Pitch, Paulstretch, Truncate Silence, Repeat), Reverb, Click Removal | Efekty sa aplikujú na výber so zachovaním dĺžky; potrebovali by prepočet výberu a labelov. |
| Plugin manager, macros, scripting | Špecifikácia neobsahuje pluginový ani automatizačný systém. |
| Cloud/sync, audio.com, rozsiahle Preferences | Projekt spracúva lokálne súbory; Preferences obsahujú iba tému, výstupné zariadenie a predvolený formát exportu. |

Ďalšie hranice: labely sa neexportujú do súboru; stereo schránka sa pri vložení do mono stopy zmieša na mono; história undo/redo je v pamäti a nie je obmedzená.

AI denoise vyžaduje voliteľný DeepFilterNet; declip vyžaduje voliteľný VoiceFixer a jeho model. Bez nich príslušné akcie zlyhajú so správou a nenechajú zmenené audio.
