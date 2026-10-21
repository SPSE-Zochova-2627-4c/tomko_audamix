# Stav požiadaviek a overenia

Táto tabuľka porovnáva aktuálny repozitár so `SPEC.md`. „CLI/jadro“ znamená skutočné spracovanie; „GUI stub“ znamená iba ovládací prvok alebo ukážkový stav. Samotný frontend nie je hotová audio aplikácia.

| Požiadavka | Aktuálny stav | Dôkaz a hranica |
|---|---|---|
| F01 načítanie | CLI/jadro áno; GUI čiastočne | `AudioData.load` číta cez SoundFile. GUI kontroluje iba existenciu a príponu, nie obsah. |
| F02 informácie | CLI/jadro áno; GUI demo | `get_info`, `command_info`. GUI zobrazuje ukážkové čísla zo stubu. |
| F03 priebeh | GUI demo | `WaveformView` kreslí generované špičky dvoch kanálov, nie dáta súboru. |
| F04 hlasitosť | CLI/jadro áno; GUI stub | `SignalProcessor.adjust_volume` mení vzorky a chráni peak. GUI iba uloží demo krok. |
| F05 frekvenčné úpravy | CLI/jadro áno; GUI stub | Low/high/band-pass filter používa Hz a validáciu. GUI má frekvenčný dialóg bez DSP prepojenia. |
| F06 klasické odšumenie | CLI/jadro základné; GUI stub | Mediánový filter alebo jednoduché STFT potlačenie. GUI zobrazí simulovaný stav. |
| F07 AI denoise | Backend dostupný podmienene; GUI stub | DeepFilterNet3 cez `AudioAI`. Váhy a kvalita neboli v tomto overení testované. |
| F08 AI declip | Backend voliteľný; GUI stub | `AudioAI.declip` vyžaduje VoiceFixer. GUI upozorní, že výsledok by bol odhad. |
| F09 náhľad/undo | CLI undo čiastočne; GUI demo | `AudioProcessor.undo` obnoví predchádzajúci objekt. GUI transport nevydáva zvuk. |
| F10 export | CLI/jadro áno; GUI nie | `AudioData.save` zapisuje súbor. GUI ukáže dialóg, potom zápis pravdivo odmietne. |
| F11 chyby | Čiastočne | CLI vracia nenulový kód pri zlyhaní; GUI vysvetlí chýbajúci súbor/model/export. Reálne GUI backend chyby nie sú zapojené. |
| §6 komponenty | Čiastočne | Oddelené dátové/DSP/AI vrstvy a GUI protokoly; ich integrácia chýba. |
| §6 priebeh dlhých operácií | GUI ukážka | Indikátor počas simulácie; skutočné AI vlákno/priebeh nie je zapojené. |
| §6 vzorky, frekvencia, kanály | CLI čiastočne | DSP vracia rovnaký tvar a metadáta; úplná validácia všetkých formátov nebola vykonaná. |
| §6 lokálnosť | Áno s výnimkou stiahnutia váh | Zvuk sa neposiela na server; prvé použitie DeepFilterNet môže stiahnuť model. |
| §7 návrh okna | GUI prototyp | Menu, panely, informácie, waveform, DSP/AI formuláre, undo a stavový riadok. |
| §8–9 vrstvy a model | Čiastočne | Existujúci backend a frontend protokoly nie sú prepojené. |
| §10 akceptačný tok | CLI čiastočne; GUI nesplnené | Cez CLI možno načítať, upraviť a uložiť. GUI zatiaľ nevie reálne upraviť/exportovať. |
| §11–13 obmedzenia a cieľ | Rozpracované | Riziká AI/veľkých súborov a budúce rozšírenia zostávajú otvorené. |

## Kontroly vykonané v tomto prostredí

- `python -m unittest discover -s tests -p 'test_audio_workflow.py' -v`: 5 testov prešlo.
- `QT_QPA_PLATFORM=offscreen python -W error tests/manual_frontend_smoke.py`: prešlo vytvorenie okna, stav akcií, výber, zoom, simulovaný efekt, undo, skratky, QSettings a zatvorenie bez výpisu varovaní.
- `python -m compileall -q src/audamix_frontend` a `git diff --check`: prešli.
- Frontend balík sa lokálne nainštaloval do nového venv pomocou `pip install --no-build-isolation --no-deps -e .` s prístupom k už existujúcim lokálnym site-packages. Čistú inštaláciu závislostí zo siete sa nepodarilo overiť.
- `pytest-qt` testy v `tests/test_frontend.py`, `ruff check` a `mypy --strict` **neboli vykonané**: balíky v prostredí chýbajú a index balíkov nebol dostupný. Nemožno tvrdiť nulové nálezy.

## Kontrola technického zadania frontendu

Splnené v kóde: Qt Widgets v Pythone, `pyproject.toml`, `src/` balík, modulový a konzolový vstupný bod, spoločné `QAction`, `QMainWindow`/`QToolBar`/`QDockWidget`, `QSettings`, protokoly backendu, `QPainter` widgety s cache, dark/light téma, výber a zoom myšou, horizontálny posuv, stav akcií a unikátne skratky v manuálnom smoke teste. Neoverené ostávajú požadované automatické pytest-qt, ruff a mypy brány. Skutočný audio engine v GUI nie je súčasťou frontend-only zadania.
