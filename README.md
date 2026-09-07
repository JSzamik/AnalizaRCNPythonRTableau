# Analiza RCN — Rejestr Cen Nieruchomości

Projekt do pobierania i analizy danych transakcyjnych z Rejestru Cen Nieruchomości.
Całość to cztery kroki, które robi się po kolei:

1. `Scrapper.py` pobiera pliki `.gpkg` z geoportalu dla wszystkich powiatów (TERYT)
   z pliku CSV i sprawdza, czy się nie posypały w trakcie pobierania.
2. `analiza_extract_dzialki.R` bierze wyczyszczone transakcje działek i dokleja do
   nich atrybuty z tych plików GPKG (sposób użytkowania, przeznaczenie w MPZP itd.).
3. `notebook.ipynb` czyści całość, robi EDA i generuje `raport_interaktywny.html`.
4. Plik `.twb` to dashboard Tableau, który czyta dane z tego co wypadło z notebooka.

## Co jest w repo

- `Scrapper.py` — pobieranie GPKG-ów
- `analiza_extract_dzialki.R` — łączenie działek z atrybutami rodzaju
- `install_packages.R` — jednorazowa instalka pakietów R do powyższego
- `notebook.ipynb` — czyszczenie, analiza, generowanie raportu
- `raport_interaktywny.html` — wynik działania notebooka, nie ruszać ręcznie
- `Analiza_RCN_-_Podział_na_sposoby_użytkowania.twb` — dashboard Tableau
- `requirements.txt` — zależności Pythona

## Setup

```bash
pip install -r requirements.txt
Rscript install_packages.R
```
Do otwarcia `.twb` potrzebujesz Tableau Desktop albo Public.

## Ścieżki

W `Scrapper.py` i `analiza_extract_dzialki.R` na górze pliku jest zmienna `RAW_PATH` —
wpisujesz tam swój folder projektu i reszta ścieżek sama się z tego buduje. Notebook
działa na ścieżkach względnych (`data/`, `output/`), więc odpalaj go z głównego
katalogu repo.

## Kolejność

```bash
python Scrapper.py
Rscript analiza_extract_dzialki.R
# potem notebook.ipynb — upewnij się, że data/transakcje.csv i data/tr2.csv są gotowe
```
Na końcu otwierasz `.twb` w Tableau i podpinasz źródło do plików z `output/`.

Po przejściu całości w `output/` powinno wylądować: `dane_obrobione.csv`,
`dane_wmpzp_long.csv`, `histogramy_cena_brutto.png` i `raport_interaktywny.html`.

---

Foldery z danymi (`Data/`, `data/`, `output/`, `wyniki/`) i wygenerowane pliki nie są
w repo — patrz `.gitignore`. Zakładam, że każdy odpala pipeline od zera na swoich danych.
