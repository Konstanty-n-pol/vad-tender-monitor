# VAD Monitor — przetargi i firmy GIS/MV-HV (DE/CH/PL)

Cotygodniowy agent monitorujący przetargi i nowe firmy w segmencie części zamiennych
GIS/MV-HV (rozdzielnice SN/WN) w Niemczech, Szwajcarii i Polsce. Generuje digest e-mail
i statyczny dashboard HTML.

## Status źródeł (2026-07-24)

| Źródło | Status | Uwagi |
|---|---|---|
| SIMAP (CH, przetargi) | ✅ działa, bez auth | `sources/simap.py`. Nazwa parametru pełnotekstowego nie w 100% potwierdzona — patrz komentarz w pliku. |
| TED (DE/PL, UE, przetargi) | ✅ działa, bez auth | `sources/ted.py`. Expert Query po słowach kluczowych + kraj kupującego. |
| Zefix (CH, nowe/pasujące firmy) | ✅ działa, bez auth | `sources/zefix.py`. Zamiast REST API (który wymaga danych logowania) używa publicznego **SPARQL endpointu LINDAS** (`https://lindas.admin.ch/query`) — oficjalnego serwisu danych powiązanych Konfederacji Szwajcarskiej, bez żadnej rejestracji. Zapytanie skanuje pełny opis celu działalności (`schema:description`) wszystkich firm w rejestrze regexem — to wolne (obserwowane 90–210s), ale w sam raz na zadanie tygodniowe. Używa zawężonej listy `COMPANY_MATCH_TERMS` (patrz `config.py`) zamiast pełnej listy słów kluczowych — ogólne terminy jak "ersatzteil"/"casting" dawały mnóstwo szumu (agencje castingowe, generyczne firmy handlowe) w wolnym tekście opisu działalności. Brak natywnego pola "data rejestracji" na poziomie firmy w tym zbiorze — "nowość" wykrywana wyłącznie przez nasz własny dedup w `storage.py`. |
| e-Zamówienia (PL) | ⏸️ zaimplementowane, wyłączone w `config.py` | Endpoint publiczny bez rejestracji (`mo-board/api/v1/notice`), ale wymaga parametru `NoticeType` (enum), którego wartości nie udało się ustalić metodą prób i błędów. Wartości są w Załączniku 3 do Regulaminu API, pobieranym z https://ezamowienia.gov.pl/pl/integracja/ — po ustaleniu, wpisz w `sources/ezamowienia.py::NOTICE_TYPE` i włącz w `config.py`. |
| DTVP, Patterno, CEIDG, KRS, Kompas Inwestycji itd. | ❌ nie zaimplementowane | Zgodnie z planem budowy — to scraping bez API, najniższy priorytet, do zrobienia na końcu. |

## Uruchomienie lokalne

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Bez żadnych zmiennych środowiskowych pipeline i tak zadziała: SIMAP, TED i Zefix nie wymagają
żadnych kluczy, e-Zamówienia po prostu się pomija (wyłączone w configu, patrz tabela wyżej).
Wynik: `docs/index.html` (dashboard) + próba wysyłki maila (pominięta bez SMTP). Zefix (SPARQL)
jest zauważalnie wolny (do ~3-4 minut) — normalne, nie przerywaj.

## Zmienne środowiskowe

| Zmienna | Do czego |
|---|---|
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
   `SMTP_USER`, `SMTP_PASS`, `DIGEST_TO`.
3. **Zmienna repo** `DASHBOARD_URL` (Settings → Secrets and variables → Actions → Variables)
   ustawiona na finalny adres GitHub Pages.
4. Wartość `NoticeType` dla e-Zamówienia z dokumentacji integracyjnej — opcjonalne, źródło
   jest wyłączone dopóki tego nie ma.

## Znane ograniczenia MVP

- Filtrowanie branżowe dla nowych firm (Zefix, ewentualnie CEIDG/KRS w przyszłości) korzysta
  z prostych fraz brzmieniowych — może przepuścić firmy z opisem działalności inaczej
  sformułowanym (np. całkowicie po francusku/włosku zamiast niemiecku — obecnie filtrujemy
  po `lang(?name) = "de"`).
- Zefix (SPARQL) nie ma pola "data rejestracji firmy" — "nowość" to wyłącznie "nowe w naszej
  bazie", nie "faktycznie zarejestrowane w tym tygodniu". Przy pierwszym uruchomieniu wszystkie
  pasujące firmy pokażą się jako nowe (baza startuje pusta); kolejne tygodnie już tylko realne
  przyrosty/zmiany dopasowania.
- TED Expert Query ogranicza liczbę słów kluczowych w jednym zapytaniu (obecnie pierwsze 8 z
  `ALL_KEYWORDS`) — do dostrojenia, jeśli okaże się zbyt wąskie lub zbyt szerokie.
- Brak jeszcze faktycznego tygodnia produkcyjnego działania — pipeline przetestowany ręcznie
  z realnymi zapytaniami do SIMAP/TED/Zefix, ale nie uruchamiany jeszcze w GitHub Actions.
