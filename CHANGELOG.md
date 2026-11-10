# Changelog

## 0.1.3

- Baza: stabilna produkcyjna wersja `0.1.2`.
- Dodano opcjonalny Motion Hold dla wskazanych wejść PIR.
- Naruszenie `OFF → ON` jest publikowane natychmiast.
- Powrót `ON → OFF` jest opóźniany do czasu upłynięcia skonfigurowanego okresu ciszy.
- Ponowne naruszenie anuluje oczekujący timer OFF.
- Dodano konfigurację czasu hold (`0–600 s`) oraz listy wejść (`1-8,10,12`).
- Nie zmieniono protokołu, AES-192, discovery, coordinatora ani alarm control panel względem `0.1.2`.
- Nie dodano nowych encji i nie zmieniono `unique_id` istniejących czujek.

## 0.1.2

- Dodano obsługę szyfrowanej integracji SATEL (AES-192).
- Dodano pole klucza integracji oraz rekonfigurację połączenia z GUI.
- Zachowano mechanikę odczytu wejść i sterowania z działającej gałęzi `0.1.x`.

## 0.1.1

- Stabilny punkt bazowy na kodzie `0.1.0`.
- Bez zmian mechaniki protokołu, discovery, czujek i alarm control panel.

## 0.1.0

- Pierwsza działająca wersja.
- Odczyt wejść i stref z INTEGRY przez stary ETHM-1.
- `binary_sensor` dla wejść.
- `alarm_control_panel` dla stref.
- Uzbrajanie i rozbrajanie.
