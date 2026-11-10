# SATEL ETHM-1 Legacy for Home Assistant

Nieoficjalna integracja Home Assistant dla starszego modułu **SATEL ETHM-1 (bez Plus)** współpracującego z centralami **INTEGRA** przez lokalny protokół integracyjny TCP/IP.

Projekt powstał dla instalacji, w których starszy ETHM-1 nadal działa poprawnie, ale współczesna oficjalna integracja Home Assistant nie obsługuje już tego wariantu modułu.

> **Status:** działający build produkcyjny `0.1.3`, rozwijany zachowawczo na bazie stabilnej wersji `0.1.x`.

## Funkcje

- lokalna komunikacja z ETHM-1 po TCP, domyślnie port `7094`;
- automatyczne rozpoznanie centrali INTEGRA;
- wykrywanie skonfigurowanych wejść i stref;
- `binary_sensor` dla wejść;
- `alarm_control_panel` dla stref;
- odczyt naruszeń wejść, uzbrojenia i alarmu;
- uzbrajanie i rozbrajanie z Home Assistanta;
- tryby Away / Home / Night mapowane na tryby czuwania INTEGRY;
- szyfrowana komunikacja integracyjna SATEL (AES-192) z kluczem integracji;
- automatyczny reconnect;
- opcjonalny **Motion Hold** dla wejść PIR, ograniczający spam w Recorder/History bez zmiany logiki alarmowej centrali;
- konfiguracja przez GUI (`config_flow` / reconfigure).

## Przetestowane środowisko

Integracja była testowana m.in. z:

- SATEL INTEGRA 64;
- ETHM-1 firmware `1.07`;
- szyfrowaną i nieszyfrowaną integracją TCP/IP;
- Home Assistant OS.

Inne wersje INTEGRY / ETHM-1 mogą działać, ale nie są gwarantowane.

## Wymagania po stronie SATEL

W DLOADX / centrali:

1. ETHM-1 musi mieć poprawną komunikację z INTEGRĄ.
2. W module ETHM-1 włącz **Integracja**.
3. Ustaw port integracji (domyślnie `7094`).
4. Jeśli używasz szyfrowania:
   - ustaw **Klucz integracji** w centrali;
   - w ETHM-1 włącz **Kodowanie integracji**;
   - ten sam klucz wpisz w konfiguracji integracji HA.
5. Zalecany jest osobny użytkownik INTEGRY dla Home Assistanta z minimalnymi wymaganymi uprawnieniami do uzbrajania / rozbrajania.

Nie wystawiaj portu integracyjnego ETHM-1 bezpośrednio do Internetu.

## Instalacja ręczna

Skopiuj katalog:

```text
custom_components/satel_ethm1_legacy
```

do:

```text
/config/custom_components/satel_ethm1_legacy
```

Następnie zrestartuj Home Assistant.

Po restarcie:

**Ustawienia → Urządzenia i usługi → Dodaj integrację → SATEL ETHM-1 Legacy**

Podaj adres IP ETHM-1, port, kod użytkownika i opcjonalny klucz integracji.

## Instalacja przez HACS jako Custom Repository

Repozytorium ma strukturę zgodną z typową integracją HACS.

W HACS:

1. **Integrations → ⋮ → Custom repositories**.
2. Dodaj URL tego repozytorium.
3. Typ: **Integration**.
4. Zainstaluj **SATEL ETHM-1 Legacy**.
5. Zrestartuj Home Assistant.

## Motion Hold dla PIR

PIR-y alarmowe często generują bardzo krótkie impulsy. Przy częstym ruchu (np. zwierzę w domu) Home Assistant Recorder może zapisywać dziesiątki zmian stanu na minutę.

Motion Hold wygładza **wyłącznie stan publikowany do HA**:

```text
SATEL:  ON OFF ON OFF ON OFF
HA:     ON ---------------- OFF
```

- `OFF → ON` trafia do HA natychmiast;
- `ON → OFF` następuje dopiero po skonfigurowanym czasie ciszy;
- kolejne naruszenie resetuje licznik;
- centrala INTEGRA nadal pracuje na surowych naruszeniach i jej logika alarmowa nie jest zmieniana.

Opcje dostępne w **Rekonfiguruj**:

- czas podtrzymania ruchu: `0–600 s` (`0` = wyłączone);
- lista wejść objętych holdem, np. `1-8,10,12`.

Dzięki temu kontaktrony można pozostawić jako natychmiastowe, a wygładzać tylko PIR-y.

## Tryby uzbrojenia

Home Assistant jest mapowany na tryby INTEGRY:

| Home Assistant | INTEGRA |
|---|---|
| Away | pełne czuwanie |
| Home | czuwanie bez wejść wewnętrznych |
| Night | czuwanie bez wejść wewnętrznych i bez czasu na wejście |
| Disarm | rozbrojenie |

Rzeczywiste zachowanie Home/Night zależy od konfiguracji typów wejść w DLOADX.

## Bezpieczeństwo

Zalecenia:

- używaj szyfrowania integracji;
- utwórz dedykowanego użytkownika INTEGRY dla HA;
- ogranicz firewall-em dostęp do TCP/7094 wyłącznie do hosta Home Assistant;
- nie publikuj ETHM-1 do Internetu;
- trzymaj ETHM-1 i HA w zaufanej sieci / odpowiednio filtrowanym VLAN-ie.

## Aktualizacje

Przy aktualizacji ręcznej nadpisz katalog:

```text
/config/custom_components/satel_ethm1_legacy
```

i zrestartuj HA.

Przed zmianą wersji warto zachować kopię działającego katalogu `custom_components/satel_ethm1_legacy`.

## Diagnostyka

Jeśli integracja nie łączy się:

- sprawdź, czy ETHM-1 odpowiada na skonfigurowanym porcie;
- upewnij się, że opcja **Integracja** jest włączona;
- przy szyfrowaniu sprawdź zgodność klucza po obu stronach;
- sprawdź routing/firewall pomiędzy HAOS a ETHM-1;
- upewnij się, że port nie jest blokowany przez inne aktywne sesje / konfigurację starego ETHM-1.

## Changelog

Zobacz [CHANGELOG.md](CHANGELOG.md).

## Zastrzeżenie

To projekt społecznościowy i **nie jest oficjalnym oprogramowaniem SATEL**. Przed użyciem sterowania alarmem z HA sprawdź konfigurację na swojej instalacji i zachowaj niezależne, lokalne sterowanie alarmem z centrali / manipulatora.
