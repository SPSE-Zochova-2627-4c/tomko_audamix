# Špecifikácia maturitnej práce

## Audamix – softvér na úpravu audia

## 1. Základné informácie

**Názov projektu:** Audamix  
**Typ projektu:** desktopová aplikácia  
**Programovací jazyk:** Python  
**Grafické rozhranie:** Qt 6 prostredníctvom PySide6  
**Oblasť:** digitálne spracovanie zvukového signálu a aplikácia metód umelej inteligencie

Audamix je aplikácia určená na jednoduchú úpravu zvukových súborov. Používateľovi umožní načítať nahrávku, zobraziť jej základné vlastnosti a aplikovať na ňu klasické metódy digitálneho spracovania zvuku alebo vybrané AI metódy.

## 2. Motivácia a problém

Úprava zvuku často vyžaduje špecializovaný softvér a znalosť práce so zvukovým signálom. Cieľom projektu je vytvoriť jednoduché grafické prostredie, v ktorom bude možné vykonať najčastejšie úpravy bez manuálnej práce so vzorkami zvuku.

Projekt zároveň demonštruje rozdiel medzi klasickým spracovaním signálu a spracovaním pomocou neurónových sietí. Používateľ tak môže porovnať výsledky tradičných filtrov s výsledkami AI metód.

## 3. Ciele projektu

Hlavným cieľom je navrhnúť a vytvoriť funkčnú desktopovú aplikáciu na spracovanie zvukových súborov.

Čiastkové ciele:

- vytvoriť prehľadné grafické používateľské rozhranie,
- umožniť načítanie podporovaného zvukového súboru,
- zobraziť základné informácie o načítanom zvuku,
- implementovať vybrané klasické metódy digitálneho spracovania signálu,
- implementovať odstránenie šumu pomocou klasických metód,
- implementovať zmenu hlasitosti a frekvenčné úpravy,
- pripraviť AI metódy na odšumenie a rekonštrukciu orezaného signálu,
- umožniť používateľovi uložiť výsledný zvuk,
- overiť správnosť a použiteľnosť aplikácie pomocou testovania.

## 4. Používateľ a rozsah systému

### 4.1 Cieľový používateľ

Cieľovým používateľom je človek, ktorý potrebuje rýchlo upraviť zvukovú nahrávku, ale nechce pracovať priamo s programovým kódom alebo s jednotlivými vzorkami signálu. Aplikácia má byť použiteľná aj pre používateľa bez pokročilých znalostí digitálneho spracovania zvuku.

### 4.2 Rozsah prvej verzie

Do prvej verzie patria:

- import zvukového súboru,
- zobrazenie základných parametrov zvuku,
- prehratie alebo kontrola načítanej nahrávky, ak to umožní použitá audio vrstva,
- klasické úpravy zvuku,
- AI úpravy zvuku,
- zobrazenie stavu spracovania,
- export upraveného zvuku.

Mimo rozsahu prvej verzie sú viacstopové projekty, strih videa, živé nahrávanie cez mikrofón a cloudové spracovanie. Tieto funkcie môžu byť predmetom budúceho rozšírenia.

## 5. Funkčné požiadavky

### F01 – Načítanie zvukového súboru

Používateľ musí mať možnosť vybrať zvukový súbor zo svojho zariadenia a načítať ho do aplikácie. Pri neplatnom alebo nepodporovanom súbore aplikácia zobrazí zrozumiteľné chybové hlásenie.

### F02 – Zobrazenie informácií o zvuku

Po načítaní aplikácia zobrazí minimálne:

- názov súboru,
- dĺžku nahrávky,
- vzorkovaciu frekvenciu,
- počet kanálov,
- počet vzoriek alebo bitovú hĺbku, ak je údaj dostupný.

### F03 – Zobrazenie priebehu signálu

Aplikácia zobrazí časový priebeh zvukového signálu. Pri stereo súbore musí byť možné rozlíšiť ľavý a pravý kanál alebo zobraziť ich kombinovaný priebeh.

### F04 – Zmena hlasitosti

Používateľ môže zmeniť amplitúdu zvukového signálu. Aplikácia musí zabrániť alebo upozorniť na vznik neplatných hodnôt a nadmerného orezania signálu.

### F05 – Frekvenčné úpravy

Používateľ môže upravovať frekvenčné vlastnosti zvuku pomocou vybraných digitálnych filtrov, napríklad dolnopriepustného, hornopriepustného alebo pásmového filtra. Parametre filtra musia byť zadateľné cez grafické rozhranie.

### F06 – Klasické odstránenie šumu

Aplikácia poskytne klasickú metódu na zníženie šumu v nahrávke. Počas spracovania zobrazí jeho stav a po dokončení sprístupní výsledok na ďalšiu úpravu alebo export.

### F07 – AI Denoising

Aplikácia umožní použiť AI metódu na odstránenie šumu pomocou neurónovej siete alebo pripraveného AI modelu. Model musí byť oddelený od grafického rozhrania a jeho použitie nesmie zablokovať aplikáciu bez zobrazenia stavu.

### F08 – AI Declipping

Aplikácia umožní pokúsiť sa rekonštruovať časti signálu poškodené orezaním. Používateľ musí byť upozornený, že výsledok je odhad a nemusí presne zodpovedať pôvodnej nahrávke.

### F09 – Náhľad a opakovanie úprav

Používateľ musí mať možnosť porovnať pôvodný a upravený zvuk alebo aspoň vrátiť poslednú úpravu. Spracovanie nesmie prepísať pôvodný súbor bez výslovného potvrdenia používateľa.

### F10 – Export výsledku

Používateľ môže uložiť upravený zvuk ako nový súbor. Pri ukladaní si vyberie umiestnenie a názov súboru; aplikácia oznámi úspešné dokončenie alebo dôvod zlyhania.

### F11 – Ošetrenie chýb

Aplikácia musí ošetriť najmä:

- chýbajúci alebo nečitateľný súbor,
- nepodporovaný formát,
- nesprávne parametre filtra,
- nedostatok pamäte alebo zlyhanie modelu,
- prerušenie alebo neúspešný export.

## 6. Nefunkčné požiadavky

- Rozhranie musí byť zrozumiteľné a ovládateľné bez znalosti Pythonu.
- Aplikácia musí používať komponentové oddelenie rozhrania, spracovania signálu a AI modelov.
- Dlhšie operácie nesmú pôsobiť ako zamrznutie aplikácie; používateľ musí vidieť stav alebo priebeh operácie.
- Spracovanie musí zachovať vzorkovaciu frekvenciu a počet kanálov, pokiaľ zvolená operácia nevyžaduje ich zmenu.
- Pri výpočtoch sa musia kontrolovať rozsahy hodnôt, aby výsledný signál neobsahoval neplatné alebo neočakávané hodnoty.
- Aplikácia musí pracovať s lokálnymi súbormi a bez potreby odosielať zvuk na externý server.
- Zdrojový kód a dokumentácia majú byť čitateľné a spustiteľné v podporovanom prostredí.

## 7. Návrh používateľského rozhrania

Hlavné okno bude obsahovať:

1. panel na otvorenie a uloženie súboru,
2. oblasť so základnými informáciami o zvuku,
3. vizualizáciu časového priebehu,
4. ovládacie prvky pre klasické filtre,
5. ovládacie prvky pre AI metódy,
6. tlačidlo na vrátenie alebo obnovenie úpravy,
7. stavový riadok s informáciou o prebiehajúcom spracovaní.

Pri každej operácii musí byť zrejmé, na ktorý zvuk sa aplikuje, aké parametre boli použité a či operácia prebehla úspešne.

## 8. Technický návrh

### 8.1 Použité technológie

| Oblasť | Technológia |
|---|---|
| Programovací jazyk | Python |
| Grafické rozhranie | Qt 6 / PySide6 |
| Numerické výpočty | NumPy |
| Čítanie a zápis zvuku | SoundFile |
| Klasické DSP | digitálne zvukové filtre |
| AI spracovanie | neurónové siete alebo AI filtre |

### 8.2 Navrhované vrstvy

- **GUI vrstva:** okná, tlačidlá, vstupné polia, vizualizácia a stavové hlásenia.
- **Aplikačná vrstva:** riadenie pracovného postupu, kontrola vstupov a prepínanie medzi operáciami.
- **DSP vrstva:** zmena hlasitosti, frekvenčné filtre a klasické odstránenie šumu.
- **AI vrstva:** načítanie modelu, AI denoising a AI declipping.
- **Dátová vrstva:** načítanie, uchovanie a export zvukového signálu pomocou SoundFile a NumPy.

Takéto rozdelenie umožní testovať spracovanie zvuku samostatne od grafického rozhrania a neskôr vymeniť alebo doplniť AI model bez veľkých zmien v aplikácii.

### 8.3 Všeobecný tok spracovania

`súbor → načítanie → kontrola formátu → zobrazenie informácií → výber metódy → spracovanie → náhľad → export`

Pri AI metódach sa medzi výber metódy a spracovanie doplní načítanie a overenie príslušného modelu.

## 9. Dátový model

Načítaný zvuk bude reprezentovaný najmä ako numerické pole vzoriek. Spolu so vzorkami sa uchovajú metadáta potrebné na správne prehrávanie a uloženie:

- vzorky zvukového signálu,
- vzorkovacia frekvencia,
- počet kanálov,
- formát alebo bitová hĺbka, ak je dostupná,
- názov a cesta pôvodného súboru,
- informácia o aktuálnej úprave.

Pôvodné dáta musia zostať dostupné počas práce, aby bolo možné vytvoriť nový výstup alebo obnoviť pôvodný stav.

## 10. Testovanie a akceptačné kritériá

Projekt bude testovaný na úrovni jednotlivých metód aj celého používateľského procesu.

Minimálne testovacie scenáre:

- načítanie platného zvukového súboru,
- odmietnutie neplatného alebo nepodporovaného súboru,
- správne zobrazenie dĺžky, vzorkovacej frekvencie a kanálov,
- zmena hlasitosti bez vzniku neočakávaných hodnôt,
- aplikovanie filtra s platnými parametrami,
- odmietnutie nesprávnych parametrov filtra,
- odstránenie šumu klasickou metódou,
- spracovanie pomocou AI denoisingu a declippingu, ak sú modely dostupné,
- export upraveného súboru a jeho opätovné načítanie,
- zobrazenie chyby pri nedostupnom modeli alebo neúspešnom exporte.

Za splnený sa projekt považuje vtedy, keď používateľ dokáže bez zásahu do zdrojového kódu načítať zvuk, vykonať aspoň jednu klasickú úpravu, zobraziť výsledok, uložiť ho ako nový súbor a dostať zrozumiteľnú spätnú väzbu pri chybovom stave.

## 11. Obmedzenia a riziká

- AI modely môžu vyžadovať veľké množstvo operačnej pamäte a výpočtového času.
- Kvalita odstránenia šumu a rekonštrukcie orezaného signálu závisí od typu nahrávky a použitého modelu.
- Nie každý zvukový formát musí byť podporovaný použitou knižnicou.
- Pri príliš dlhých nahrávkach môže spracovanie vyžadovať delenie signálu na menšie časti.
- Výsledok AI rekonštrukcie je odhad, preto musí byť v aplikácii označený ako spracovaný výstup.

## 12. Možné budúce rozšírenia

- viacstopové projekty,
- strih a spájanie častí nahrávky,
- nahrávanie zvuku priamo z mikrofónu,
- prehrávanie so zobrazením aktuálnej pozície,
- história všetkých úprav,
- ďalšie zvukové efekty a formáty,
- export nastavení spracovania,
- zrýchlenie AI spracovania pomocou grafickej karty.

## 13. Výsledný stav projektu

Výsledkom bude spustiteľná desktopová aplikácia s grafickým rozhraním, ktorá používateľovi umožní načítať, analyzovať, upraviť a uložiť zvukový súbor. Súčasťou maturitnej práce bude aj vysvetlenie princípov digitálneho spracovania zvuku, opis použitých technológií, návrh aplikácie, implementácia vybraných metód a vyhodnotenie výsledkov.
