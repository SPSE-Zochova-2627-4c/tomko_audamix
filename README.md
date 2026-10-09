# Audamix

**Softvér na úpravu audia**

Audamix je desktopová aplikácia na spracovanie a úpravu zvukových súborov. Projekt vzniká ako maturitný projekt a jeho cieľom je umožniť používateľovi jednoducho aplikovať klasické metódy digitálneho spracovania zvuku aj moderné metódy založené na umelej inteligencii.

## 🎯 Cieľ projektu

Cieľom projektu je vytvoriť desktopovú aplikáciu, ktorá umožní spracovávať zvukové súbory bez potreby manuálnej úpravy zvukovej stopy.

Aplikácia umožní používateľovi:

- načítať zvukový súbor,
- zobraziť jeho základné informácie,
- upravovať vlastnosti zvukového signálu,
- aplikovať klasické filtre digitálneho spracovania zvuku,
- odstraňovať šum zo zvukovej nahrávky,
- upravovať hlasitosť a frekvenčné vlastnosti zvuku,
- využívať AI metódy na spracovanie zvukového signálu,
- rekonštruovať poškodené alebo orezané časti zvukovej nahrávky.

## 🔊 Funkcie

### Klasické spracovanie zvuku

Aplikácia bude obsahovať vybrané metódy digitálneho spracovania signálu, napríklad:

- odstránenie šumu,
- zmenu hlasitosti,
- frekvenčné úpravy,
- digitálne zvukové filtre,
- ďalšie metódy spracovania zvukového signálu.

### 🤖 Spracovanie pomocou AI

Súčasťou aplikácie budú aj metódy spracovania zvuku založené na umelej inteligencii.

Plánované AI funkcie zahŕňajú:

- **AI Denoising** – odstraňovanie šumu pomocou neurónovej siete,
- **AI Declipping** – rekonštrukcia skreslených alebo orezaných častí zvukového signálu.

## 🛠️ Technológie

Projekt je vyvíjaný v jazyku **Python**.

| Oblasť | Technológia |
|---|---|
| Programovací jazyk | Python |
| Grafické rozhranie | Qt 6 |
| Python GUI framework | PySide6 |
| Spracovanie signálu | NumPy |
| Práca so zvukovými súbormi | SoundFile |
| Klasické DSP | Digitálne zvukové filtre |
| AI spracovanie | Neurónové siete / AI filtre |

## 🖥️ Grafické používateľské rozhranie

Používateľské rozhranie bude vytvorené pomocou **Qt 6** a knižnice **PySide6**.

Aplikácia bude poskytovať jednoduché grafické rozhranie na načítanie zvukových súborov, zobrazenie ich informácií a aplikáciu jednotlivých efektov a filtrov.

## AI backendy

AI spracovanie používa lokálne predtrénované modely a zvuk sa pri spracovaní
neodosiela na server:

- AI denoise: DeepFilterNet3 (`deepfilternet`), určený najmä na potlačenie
  šumu v reči. Model sa stiahne do lokálnej cache pri prvom použití.
- AI declipping: voliteľný VoiceFixer (`voicefixer`) pre reč. Keď jeho váhy
  nie sú nainštalované, aplikácia operáciu odmietne a nepoužije falošný
  interpolovaný „AI“ výsledok.

Mapovanie voči efektom Audacity je: Noise Reduction/Noise Gate → denoise,
Low/High-Pass a EQ → klasické DSP filtre, Compressor/Limiter → dynamické
spracovanie a Clip Fix → declipping. DeepFilterNet je speech enhancement
model, preto jeho výsledok pri hudbe alebo inom materiáli nemusí byť vhodný.

## 📁 Projekt

Štruktúra projektu bude priebežne dopĺňaná počas vývoja.

```text
Audamix/
├── ...
└── README.md
