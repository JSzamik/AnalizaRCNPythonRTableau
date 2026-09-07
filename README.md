# Analiza RCN — Rejestr Cen Nieruchomości

Projekt do pobierania i analizy danych transakcyjnych z Rejestru Cen Nieruchomości (RCN).
Cel: sprawdzić jak zmieniają się ceny nieruchomości w zależności od sposobu użytkowania
działki, przeznaczenia w MPZP i lokalizacji, na bazie transakcji z lat 2015–2026.

## Dashboardy na żywo

- [Analiza RCN](https://public.tableau.com/app/profile/jakub.szamik/viz/AnalizaRCN-Podzianasposobyuytkowania/Story1)
- [Analiza RCN 2](https://public.tableau.com/app/profile/jakub.szamik/viz/AnalizaRCN/Fina)

## Skąd się biorą dane

Dane wejściowe to transakcje z Rejestru Cen Nieruchomości, publikowane przez GUGiK
w podziale na powiaty (pliki `.gpkg`, format GeoPackage — w środku to zwykła baza
SQLite). Same pliki GPKG nie mają wygodnej struktury do analizy zbiorczej, więc
najpierw trzeba je pobrać, złączyć z resztą danych transakcyjnych, i dopiero wtedy
czyścić i analizować.

## Cztery kroki pipeline'u

**1. `Scrapper.py`** — pobiera pliki `.gpkg` z geoportalu dla wszystkich powiatów
(kody TERYT) wymienionych w pliku CSV. Dla każdego terytu:
- sprawdza, czy plik już nie został pobrany wcześniej (nie pobiera drugi raz),
- pobiera ZIP, rozpakowuje z niego `.gpkg`, nadaje mu czytelną nazwę (np.
  `powiat_piaseczynski_1418.gpkg` zamiast samego kodu TERYT),
- otwiera pobrany plik jako SQLite i liczy rekordy w warstwach — żeby złapać
  pliki puste albo uszkodzone w trakcie pobierania,
- na koniec zapisuje trzy pliki ze statusem: błędy pobierania, pliki
  puste/uszkodzone i pełny status każdego terytu.

**2. `analiza_extract_dzialki.R`** — działa na wyczyszczonych transakcjach działek
i dokleja do nich atrybuty, których nie ma w podstawowym pliku transakcyjnym:
sposób użytkowania działki (`dzi_sposob_uzyt`), przeznaczenie w miejscowym planie
zagospodarowania (`dzi_przezn_wmpzp`), powierzchnię ewidencyjną i cenę brutto z GPKG.
Dopasowanie działa przez powiat (nazwa pliku GPKG) i identyfikator transakcji.
Jedna transakcja może obejmować kilka działek — wtedy skrypt agreguje: bierze
najczęstszą wartość dla pól tekstowych (tryb) i sumuje pola liczbowe.

**3. `notebook.ipynb`** — główna część analityczna, w kilku etapach:
- wczytanie surowych transakcji, parsowanie dat, odcięcie transakcji spoza
  zakresu 2015–2026,
- odrzucenie duplikatów i rekordów z zerową/ujemną ceną lub powierzchnią,
- odrzucenie wartości odstających metodą IQR, osobno dla każdej kategorii
  nieruchomości (działki/lokale/budynki mają różne rozkłady cen),
- eksploracyjna analiza danych: braki danych po kolumnach, histogramy cen,
  segmenty cenowe, mediana cen w czasie wg kategorii,
- dołączenie `dzi_sposob_uzyt` i `dzi_przezn_wmpzp` z pliku `tr2.csv` (wynik
  kroku 2) i odfiltrowanie transakcji bez tych atrybutów,
- rozbicie wielowartościowego `dzi_przezn_wmpzp` (kombinacje typu
  "mieszkaniowe;usługowe") na pojedyncze tokeny, osobno wiersz na wartość,
- policzenie mediany cen w czasie (kwartalnie) wg sposobu użytkowania, ze zmianą
  rok do roku i minimalnym progiem liczby transakcji (żeby nie liczyć mediany
  z 3 transakcji),
- wygenerowanie `raport_interaktywny.html` z tabelami i wykresami, plus osobna
  sekcja z medianą cen wg rejonu.

**4. Tableau (`.twb` + Tableau Public)** — dashboard i story zbudowane na danych
z `output/`. Pliki `.twbx` (spakowana wersja z danymi w środku) nie są w repo,
bo ważą grubo ponad 100 MB i tak naprawdę są tylko artefaktem do publikacji —
gotowe dashboardy są dostępne pod linkami wyżej.

## Co jest w repo

| Plik | Co robi |
|---|---|
| `Scrapper.py` | pobieranie GPKG-ów z geoportalu |
| `analiza_extract_dzialki.R` | łączenie działek z atrybutami rodzaju z GPKG |
| `install_packages.R` | jednorazowa instalka pakietów R do powyższego |
| `notebook.ipynb` | czyszczenie, EDA, wzbogacenie danych, generowanie raportu |
| `Analiza_RCN_-_Podział_na_sposoby_użytkowania.twb` | definicja dashboardu Tableau |
| `requirements.txt` | zależności Pythona |

## Setup

```bash
pip install -r requirements.txt
Rscript install_packages.R
```
Do otwarcia `.twb` lokalnie potrzebujesz Tableau Desktop albo Public — ale skoro
gotowe dashboardy są opublikowane (linki wyżej), to raczej do podglądu struktury
niż do codziennego użytku.

## Ścieżki

W `Scrapper.py` i `analiza_extract_dzialki.R` na górze pliku jest zmienna `RAW_PATH` —
wpisujesz tam swój folder projektu i reszta ścieżek sama się z tego buduje. Notebook
działa na ścieżkach względnych (`data/`, `output/`), więc odpalaj go z głównego
katalogu repo.

## Kolejność uruchamiania

```bash
python Scrapper.py
Rscript analiza_extract_dzialki.R
# potem notebook.ipynb — upewnij się, że data/transakcje.csv i data/tr2.csv są gotowe
```
Na końcu otwierasz `.twb` w Tableau i podpinasz źródło do plików z `output/`, albo po
prostu zaglądasz do opublikowanych dashboardów.

Po przejściu całości w `output/` powinno wylądować: `dane_obrobione.csv`
(finalny, oczyszczony i wzbogacony zbiór), `dane_wmpzp_long.csv` (dane w formacie
długim wg przeznaczenia w MPZP), `histogramy_cena_brutto.png` i
`raport_interaktywny.html`.

---

Foldery z danymi (`Data/`, `data/`, `output/`, `wyniki/`) i wygenerowane pliki nie są
w repo — patrz `.gitignore`. Zakładam, że każdy odpala pipeline od zera na swoich danych.
