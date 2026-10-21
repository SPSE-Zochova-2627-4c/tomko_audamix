# Zmeny projektu

Súčasný stav a použitie sú opísané v koreňovom `README.md` a `docs/ARCHITECTURE.md`. Tento súbor zachytáva hlavné etapy; pôvodné podrobné poznámky o „headroom preservation“ boli historickým návrhom a ich ukážky už nezodpovedali aktuálnemu API.

## Aktuálne rozpracované zmeny

- Opravené `declip` v AI vrstve a vo volaniach aplikačnej vrstvy.
- DSP operácie vracajú nové dáta, validujú parametre a zachovávajú mono/stereo tvar. Frekvencie filtrov sa zadávajú v Hz. Klasické odšumenie zachováva dĺžku signálu. Pri peaku nad 1.0 sa výsledok zníži s varovaním.
- `AudioData` predvolene zachová pôvodnú úroveň, poskytuje peak/RMS/peak-to-RMS metriky a export odvodzuje formát od výstupnej prípony.
- `AudioProcessor` eviduje úspešné kroky a umožňuje undo; CLI má opraviteľné argumenty vrátane `--cutoff`, `--declip`, dávkového spracovania a tvorby stereo ticha.
- Pridaný samostatný PySide6 frontend prototyp s demo backendmi, témou, akciami, waveformom, výberom, zoomom a persistenciou okna. Nie je pripojený k audio jadru.
- Pridané testy audio workflow, pytest-qt testy GUI a opakovateľný manuálny offscreen smoke test.
- Základné `requirements.txt` sú oddelené od `requirements-ai.txt`; CLI načíta AI modul až pri AI príkaze, aby bežná inštalácia nevyžadovala Rust kompiláciu DeepFilterLib.

## Predchádzajúca história

- `7c521c1` — predtrénovaný backend pre AI denoise.
- `c2c58f4` — počiatočný commit projektu.

Git história obsahuje presné zmeny súborov. AI backend a úpravy reálneho audia neboli v GUI integračne overené.
