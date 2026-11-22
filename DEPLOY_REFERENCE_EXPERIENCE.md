# Ceyrl — bezpečné nasadenie redizajnu

Dizajn: Ceyrl reference experience v5. Názov produktu je vždy **Ceyrl**.

## Pred nasadením
1. V Bot-Hosting.net zálohuj celý perzistentný adresár `CTW_DATA_DIR` vrátane `identity.sqlite3`, `users/*/inventory.sqlite3`, priečinkov PDF vault a `.encryption_key`. Zálohu ulož mimo hostingu.
2. Over, že hosting pri aktualizácii kódu **neprepisuje dátový adresár** a používa správne HTTPS nastavenia.
3. Nasaď commit z vetvy `main` až po úspešných testoch na GitHub Actions. Reštartuj server.
4. V prehliadači použi tvrdé obnovenie stránky (`Ctrl+Shift+R`).

## Rýchle overenie nasadenia
- URL `/static/experience.css?v=experience-5` má vrátiť CSS.
- URL `/static/experience.js?v=experience-5` má vrátiť JS.
- `/api/auth/state` musí fungovať podľa existujúcich autentifikačných pravidiel.
- Navigácia má položky Dashboard, Event Radar, Moje udalosti, Moje vstupenky, Predaje, Analytika, Účet a nastavenia spolu s ostatnými pôvodnými modulmi.
- Fotografie v hero sekciách sú dekoratívne, nezobrazujú skutočnú akciu konkrétneho používateľa. Ich načítanie závisí od `images.unsplash.com`; lokálna grafika slúži ako fallback.

## Akceptačné testy pred sprístupnením používateľom
- Desktop (~1440px), tablet (~800px), mobil (~390px): rozloženie bez horizontálneho pretečenia a prekrývania tlačidiel.
- Pridanie/úprava udalosti a vyhľadávanie, prepnutie mriezka/zoznam, filter minulé/nadchádzajúce.
- Pridanie vstupeniek, PDF trezor, prepnutie kartové/tabuľkové zobrazenie a filtrovanie.
- Zaznamenanie predaja, aktualizácia stavu miest a výpočet čistej marže.
- Event Radar: textové vyhľadávanie, rýchle mená, krajiny, kategórie a dátumy, import potvrdeného podujatia a súkromné uložené sledovania.
- Stav zdrojov zodpovedá reálne dostupným integráciám; žiadne falošné ceny alebo vymyslená dostupnosť. Rozšírené Ticketmaster vyhľadávanie vyžaduje serverové `CTW_TICKETMASTER_API_KEY`, nie kľúč od bežného používateľa.
- Účet: editácia mena, heslo, relácie, export dát, preferencie pohybu.
- Viacúčtový test: Alice a Bob nevidia podujatia, PDF ani sledovania toho druhého.
- Otestuj externé zdroje na živom hostingu a chybové stavy (429, 502, výpadok konektora).
- Test s režimom `prefers-reduced-motion` a klávesnicovým ovládaním.

## Dôležité
GitHub CI kontroluje backend regresie a syntax frontendových súborov. Nie je to náhrada za screenshotové, end-to-end a produkčné testovanie s reálnymi externými poskytovateľmi. Ani automatické testy neznamenajú, že tretie strany zaručujú dostupnosť vstupeniek.
