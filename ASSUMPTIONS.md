# Predpoklady pre Qt frontend

Zadanie frontendu obsahovalo nevyplnené zástupné sekcie „PROJECT CONTEXT“, „SPEC“ a „FEATURES IN SCOPE“. Ako funkčnú špecifikáciu som preto použil súbor `SPEC.md` v repozitári. Posledná výslovná požiadavka používateľa určila Python 3.11+ a PySide6; frontend je samostatný balík a neimportuje existujúce audio jadro.

## Zvolený rozsah prvej verzie

- Jedna lokálna audio stopa; názov, dĺžka, frekvencia, kanály a počet vzoriek.
- Časová os, rozlíšené stereo kanály, kurzor, výber, posuv a zoom.
- Ukážkový Play/Pause/Stop a presun na začiatok alebo koniec.
- Formuláre pre hlasitosť, low/high/band-pass, klasické odšumenie, AI denoise a AI declip.
- Demo undo, dialóg exportu s pravdivým oznámením, že backend chýba.
- Mute, Solo, Gain, Pan, zbalenie/zatvorenie stopy a stavové hlásenia.
- Tmavá a svetlá téma s uložením nastavení.

`SPEC.md` podmieňuje prehrávanie dostupnosťou audio vrstvy. Keďže frontend má byť samostatný, transport iba posúva ukazovateľ a nevydáva zvuk. Súbor sa nedekóduje: stub kontroluje existenciu a príponu, potom pripraví deterministické ukážkové dáta. Čísla v paneli preto nie sú metadátami vstupného súboru. Export vždy odmietne zápis. Efekty vytvoria iba demo históriu; skutočné audio zostáva nedotknuté. Tieto obmedzenia sú v UI uvedené.

Výber a zoom sú stav rozhrania; track close vyloží demo stopu. Viacstopové projekty a záznam sú podľa `SPEC.md` budúce rozšírenia. Playback meter chýba, pretože stub nemá reálne úrovne. Strih a kopírovanie nie sú v rozsahu prvej verzie. Menu Effects je pridané, lebo špecifikácia vyžaduje ovládanie DSP a AI metód. Ostatné Audacity menu bez opory v špecifikácii sa nepridali.

Frontend používa len PySide6 a štandardnú knižnicu. NumPy je závislosťou oddeleného audio jadra, nie UI. Vrcholy ukážkového priebehu vznikajú raz pomocou `math`.
