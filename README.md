# C TicketWave PRO V4 — Ticket Operations Workspace

Profesionálna aplikácia pre správu vstupeniek, eventov, inzerátov a predaja. V4 má kompletne prepracované tmavomodré rozhranie s logom **C** a je navrhnutá pre tím s vlastnými prihlasovacími účtami.

## Rýchle spustenie na Windows

1. Nainštaluj **Python 3.11 alebo novší** a zapni `Add Python to PATH`.
2. Rozbaľ ZIP do samostatného priečinka, napr. `C:\TicketWave-V4`.
3. Dvojklikom spusti **`start-windows.bat`**. Pri prvom štarte sa nainštalujú potrebné Python balíky do `.venv`.
4. Otvor **http://127.0.0.1:8765**. Aplikácia je pre bezpečnosť dostupná iba z tvojho počítača.
5. Pri prvom spustení vytvor administrátorský účet (heslo aspoň 12 znakov). Potom cez **Team Members** pozývaj kolegov.
6. Vytvor **Events**, potom pridaj vstupenky v **Ticket Inventory**, prípadne lokálne inzeráty v **Listings**. Dokončené predaje zapisuj do **Sales & Profit**.

Spúšťací súbor musí zostať otvorený, kým aplikáciu používaš. Pre dlhodobé tímové používanie použi HTTPS server s trvalým úložiskom; v projekte je aj Docker konfigurácia. Neposkytuj prístup na internet priamo k lokálnemu Windows portu.

## Novinky V4

- **Nová navigácia:** Overview, Events, Ticket Inventory, Listings, Sales & Profit, Expenses, Team Members, Activity Log, My Account.
- **Vizuálny redesign:** konzistentná tmavomodrá paleta, väčšie KPI, upravené tabuľky, moderný login, nové SVG ikony, mobilné menu a responzívny layout.
- **Sales & Profit:** žiadne fialové „admit one“ recap kartičky. Nahradené profesionálnou tabuľkou eventov, ziskovosťou, ROI a rozklikávacím presným finančným rozpisom.
- **Rýchle vyhľadávanie:** hore hľadaj lístky cez **Ctrl+K** + Enter; v Ticket Inventory funguje okamžité filtrovanie bez opakovaného sťahovania databázy pri každom stlačení klávesu.
- **Inventory overview:** dostupné kusy, predané lístky, počet lotov a šifrovaných PDF príloh.
- **My Account:** správa hesla a vývoz inventára či predajov (pre Manager/Admin).
- **Jasnejšie onboarding tlačidlá:** novému workspace bez eventov aplikácia ponúkne najprv vytvorenie eventu.
- **Vypnuté nechcené časti:** Integrations & Settings, Find Events, Event Watchlist a staré Event Recaps už nie sú v rozhraní. Automatické pozadie watchlistu je tiež **predvolene vypnuté**. Staré backendové tabuľky/API zostali zachované z dôvodu kompatibility, aby sa nestratili žiadne pôvodné dáta.

## Čo je funkčne prepojené s backendom

| Funkcia | Ako funguje |
|---|---|
| Bezpečné účty | Prihlasovanie, Argon2id hashovanie hesiel, osobné sessions, CSRF ochrana a audit |
| Tím | Role Admin, Manager, Operator, Viewer; pozvánky a jednorazové resetovanie hesla |
| Databáza | Trvalá SQLite databáza v `data/ticketwave.sqlite3` |
| Eventy | Vytváranie a prehľad podujatí, termínov a miest |
| Ticket Inventory | Loty, sekcie, rady, sedadlá, stav, kusy, nákupná cena |
| PDF trezor | Šifrované ukladanie PDF vo `data/vault/`, kontrola duplicitných príloh |
| Listings | Lokálne drafty, marketplace ID, stav, cena, poplatky, ochrana pred duplicitami |
| Sales & Profit | Evidencia predajov, automatický odpočet predaných kusov, reálne finančné prehľady |
| Expenses | Náklady na eventy, evidované meny, dátumy a popisy |
| Audit | Zmeny v záznamoch pripísané používateľovi |
| Export | CSV inventára a predaja |

### Ako sa počíta zisk

**Čistý zisk v EUR = príjmy z predaných vstupeniek − poplatky marketplace − nákupná cena predaných kusov − EUR prevádzkové náklady.** ROI na úrovni eventu = čistý zisk / (cena predaných vstupeniek + eventové náklady) × 100 %. Keď je investícia nulová, ukáže sa pomlčka. Iné meny sa **neprepočítavajú automaticky na EUR**.

**Dôležité:** aplikácia sama nepublikuje inzeráty na Viagogo. Lokálne listingy fungujú, ale live Viagogo publikovanie vyžaduje schválené seller API oprávnenia a nie je súčasťou tejto verzie. Ticketmaster live vyhľadávanie a jeho konfigurácia sú v V4 skryté na tvoju žiadosť; eventy sa vytvárajú v aplikácii manuálne.

## Prechod z V3 na V4 bez straty údajov

1. **Vypni starú aj novú aplikáciu.** Zálohuj celý pôvodný priečinok `data/` z V3, nie iba samotný `.sqlite3` súbor.
2. Rozbaľ V4 do nového priečinka.
3. Skopíruj **celý** pôvodný `data/` do koreňa V4. Musí obsahovať `ticketwave.sqlite3`, `vault/` a predovšetkým **`.encryption_key`**.
4. Spusti `start-windows.bat` v V4 a prihlás sa so svojím existujúcim účtom.
5. Skontroluj počet eventov, lístkov, predajov, používateľov a či idú PDF otvárať.
6. Starý priečinok a zálohu V3 nechaj uložené do času, kým si overíš úspešnú migráciu.

**Nikdy nestrácaj `.encryption_key`**. Bez tohto súboru už nie je možné dešifrovať uložené PDF ani ďalšie chránené údaje. Pred migráciou server vypni kvôli SQLite WAL súborom.

## Prevádzka a bezpečnosť

- Heslá sa neskladujú čitateľne, PDF sú šifrované a každý zamestnanec má vlastný účet.
- SQLite je vhodná pre menšie dôveryhodné tímy. Pre veľkú SaaS aplikáciu pre nesúvisiace firmy treba samostatné tenantovanie a ďalšie bezpečnostné opatrenia (MFA, monitoring, nezávislý audit, produkčné migrácie DB).
- Na verejnom serveri používaj **HTTPS**, bezpečné cookies (`CTW_SECURE_COOKIES=1`), dôslednú konfiguráciu povolených originov, zálohy a autentifikované prístupy.
- Zálohuj **celý `data/`** vrátane skrytého súboru `.encryption_key` a encrypted PDF `vault/`; zálohy drž mimo verejného priečinka projektu.
- Nepridávaj databázu, kľúče ani zákaznícke PDF do GitHubu. `.gitignore` pred nimi chráni.
- Aplikácia je lokálny tímový produkt, nie nezávisle bezpečnostne auditovaná produkčná SaaS služba.

## Docker

V projekte sú `Dockerfile` a `docker-compose.yml`. Pre Docker nastav silný `CTW_BOOTSTRAP_CODE`; reverzná proxy s HTTPS je nutná, ak má aplikácia slúžiť viacerým ľuďom mimo lokálnej siete. Persistentné dáta sú v docker volume `ticketwave_data`.

## Testovanie

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q tests
node --check static/app.js
```

Aktuálne testy pokrývajú autentifikáciu, práva, inventár, PDF, inzeráty, predaje, finančné výpočty, API regresie a odstránené položky V4. Browser UI sa testovalo aj cez render s ukážkovými dátami, pretože testovací prehliadač nepovoľoval prístup na lokálnu HTTP adresu. To nenahrádza finálne testy s reálnou hostovanou inštaláciou.

## Štruktúra projektu

- `app.py` – FastAPI backend, SQLite, auth, business logic
- `static/index.html` – aplikácia a prihlasovanie
- `static/style.css`, `static/v3.css`, `static/v4.css` – stylesheety; V4 je finálna prezentačná vrstva
- `static/app.js` – funkčná logika frontend-u
- `static/logo.png` – logo C
- `tests/` – integračné a regresné testy
- `screenshots/` – **testovacie** náhľady V4, nie skutočné predajné dáta používateľa
- `start-windows.bat` – spustenie na Windows

**Verzia:** 4.0.0 · November 2026
