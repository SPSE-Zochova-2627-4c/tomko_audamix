# Predpoklady

Pôvodné zadanie frontendu obsahovalo prázdne sekcie pre kontext, špecifikáciu a zoznam funkcií. Pri rozsahu som vychádzal zo súboru `SPEC.md`, existujúceho audio jadra a následnej požiadavky na priamy štart zo súboru.

- Aplikácia má jednu lokálnu mono alebo stereo stopu. Viacstopový model neexistuje.
- `python audamix.py` z koreňa repozitára je hlavný vstupný bod. Závislosti sa inštalujú z `audamix/requirements.txt`; nie je potrebné inštalovať projekt ako balík.
- GUI ponúka Open, Export, Play/Pause/Stop, presun na začiatok/koniec, výber kurzorom a myšou, zoom, Mute/Solo/Gain/Pan, gain, low/high/band-pass, klasické odšumenie, AI denoise/declip, undo, témy a ukladanie stavu okna.
- Efekty sa aplikujú na celú stopu, pretože existujúce DSP rozhranie pracuje s celým `AudioData`. Výber slúži na navigáciu a priblíženie.
- Priebeh počíta najviac 2048 peak/RMS blokov na kanál pri načítaní alebo úprave. Je to kompromis medzi detailom a rýchlosťou kreslenia.
- Náhľad sa pri prehrávaní renderuje ako dočasný WAV. Mute, Gain a Pan ovplyvňujú náhľad aj export; Solo pri jednej stope nemení zvuk.
- Gain efekt používa dB, Gain posuvník násobok 0 až 2. Pan pri stereu tlmí protiľahlý kanál; pri mono nemá účinok.
- Efekty bežia v `QThread`, aby okno zostalo responzívne. Počas operácie sú konfliktné akcie vypnuté a okno sa dá zavrieť po dokončení.
- AI závislosti sú voliteľné; chýbajúci model sa oznámi chybou. `declip` je presný názov operácie a rekonštrukcia je odhad.
- Tmavá téma je predvolená. `QSettings` ukladá geometriu, rozloženie panelov a výber témy.
