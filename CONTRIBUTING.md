# Contributing

Projekt jest rozwijany konserwatywnie, ponieważ starsze moduły ETHM-1 mają różne wersje firmware i zachowania.

## Zasady zmian

1. Nie zmieniaj jednocześnie warstwy transportowej, discovery i encji.
2. Każda zmiana protokołu powinna być możliwie mała i łatwa do wycofania.
3. Nie zmieniaj istniejących `unique_id` bez mechanizmu migracji.
4. Zmiany wpływające na Recorder/History nie powinny generować dodatkowych atrybutów zmieniających się przy każdym pollingu.
5. Pull request powinien opisywać model centrali, wersję ETHM-1 i sposób testu.

## Minimalna walidacja

Przed PR:

```bash
python -m compileall -q custom_components/satel_ethm1_legacy
```

oraz sprawdź, że wszystkie pliki JSON są poprawne.
