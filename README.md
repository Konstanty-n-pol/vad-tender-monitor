# VAD Monitor — przetargi i firmy GIS/MV-HV (DE/CH/PL)

Cotygodniowy agent monitorujący przetargi i nowe firmy w segmencie części zamiennych
GIS/MV-HV (rozdzielnice SN/WN) w Niemczech, Szwajcarii i Polsce. Generuje digest e-mail
i statyczny dashboard HTML.

## Status źródeł (2026-07-23)

| Źródło | Status | Uwagi |
|---|---|---|
| SIMAP (CH) | ✅ działa, bez auth | `sources/simap.py`. Nazwa parametru pełnotekstowego nie w 100% potwierdzona — patrz komentarz w pliku. |
| TED (DE/PL, UE) | ✅ działa, bez auth | `sources/ted.py`. Expert Query po słowach kluczowych + kraj kupującego. |
| Zefix (CH, nowe firmy) | ⏸️ zaimplementowane, czeka na dane logowania | Wymaga HTTP Basic Auth — napisz na **zefix@bj.admin.ch** o dostęp (bezpłatny), potem ustaw `ZEFIX_USER`/`ZEFIX_PASS`. |
| e-Zamówienia (PL) | ⏸️ zaimplementowane, wyłączone w `config.py` | Endpoint publiczny bez rejestracji (`mo-board/api/v1/notice`), ale wymaga parametru `NoticeType` (enum), którego wartości nie udało się ustalić metodą prób i błędów. Wartości są w Załączniku 3 do Regulaminu API, pobieranym z https://ezamowienia.gov.pl/pl/integracja/ — po ustaleniu, wpisz w `sources/ezamowienia.py::NOTICE_TYPE` i włącz w `config.py`. |
| DTVP, Patterno, CEIDG, KRS, Kompas Inwestycji itd. | ❌ nie zaimplementowane | Zgodnie z planem budowy — to scraping bez API, najniższy priorytet, do zrobienia na końcu. |

## Uruchomienie lokalne

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Bez żadnych zmiennych środowiskowych pipeline i tak zadziała: SIMAP i TED nie wymagają
kluczy, Zefix/e-Zamówienia po prostu się pominą z komunikatem w logu. Wynik: `docs/index.html`
(dashboard) + próba wysyłki maila (pominięta bez SMTP).

## Zmienne środowiskowe

| Zmienna | Do czego |
|---|---|
| `ZEFIX_USER`, `ZEFIX_PASS` | dane logowania Zefix (patrz tabela wyżej) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | wysyłka e-maila z istniejącej skrzynki |
| `DIGEST_TO` | adres, na który ma iść cotygodniowy digest |
| `DASHBOARD_URL` | link do dashboardu wstawiany w stopce maila (np. URL GitHub Pages) |

### Gmail: hasło aplikacji

Zwykłe hasło do konta **nie zadziała** przy włączonym 2FA (a powinno być włączone).
Wygeneruj "hasło aplikacji" na https://myaccount.google.com/apppasswords i użyj go jako
`SMTP_PASS` (host: `smtp.gmail.com`, port: `587`).

## Architektura

- `config.py` — słowa kluczowe (rdzenie, nie pełne formy — patrz komentarz w pliku o
  odmianie/złożeniach), kody CPV, włączanie/wyłączanie źródeł.
- `filters.py` — wspólna logika dopasowania (substring na rdzeniu, żeby złapać odmiany
  polskie i złożenia niemieckie; frazy wielowyrazowe jako krotki z logiką "wszystkie muszą
  wystąpić").
- `sources/*.py` — jeden moduł na źródło, każdy zwraca listę znormalizowanych `Record`.
- `storage.py` — SQLite (`data/records.sqlite3`) do deduplikacji i historii; przetargi po
  terminie oznaczane jako `expired`, nie usuwane.
- `generate.py` + `templates/*.j2` — te same dane renderowane do e-maila i dashboardu.
- `mailer.py` — wysyłka SMTP.
- `main.py` — spina wszystko w jeden przebieg.
- `.github/workflows/weekly.yml` — harmonogram: co poniedziałek 06:00 UTC, commituje
  zaktualizowaną bazę + dashboard z powrotem do repo (Pages serwuje `docs/`).

## Żeby to zaczęło realnie działać, brakuje jeszcze

1. **Repo na GitHubie** (publiczne lub prywatne) + włączony GitHub Pages wskazujący na branch
   `main`, folder `/docs`.
2. **Sekrety w repo** (Settings → Secrets and variables → Actions): `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, `SMTP_PASS`, `DIGEST_TO`, opcjonalnie `ZEFIX_USER`/`ZEFIX_PASS`.
3. **Zmienna repo** `DASHBOARD_URL` (Settings → Secrets and variables → Actions → Variables)
   ustawiona na finalny adres GitHub Pages.
4. Dane logowania Zefix (mail do zefix@bj.admin.ch) — opcjonalne, bez nich moduł się po
   prostu pomija.
5. Wartość `NoticeType` dla e-Zamówienia z dokumentacji integracyjnej — opcjonalne, źródło
   jest wyłączone dopóki tego nie ma.

## Znane ograniczenia MVP

- Filtrowanie geograficzne/branżowe dla nowych firm (Zefix, ewentualnie CEIDG/KRS w
  przyszłości) korzysta z prostych fraz brzmieniowych — może przepuścić firmy z opisem
  działalności inaczej sformułowanym.
- TED Expert Query ogranicza liczbę słów kluczowych w jednym zapytaniu (obecnie pierwsze 8 z
  `ALL_KEYWORDS`) — do dostrojenia, jeśli okaże się zbyt wąskie lub zbyt szerokie.
- Brak jeszcze faktycznego tygodnia produkcyjnego działania — pipeline przetestowany ręcznie
  z realnymi zapytaniami do SIMAP/TED, ale nie uruchamiany jeszcze w GitHub Actions.
