"""
Skrypt pobiera pliki GPKG (Rejestr Cen Nieruchomości) z geoportalu opendata.geoportal.gov.pl
dla wszystkich kodów TERYT wskazanych w pliku CSV (kolumna "teryt").

Wzorzec adresu pliku:
https://opendata.geoportal.gov.pl/InneDane/latest_exports/rcn_transakcje_ceny/GPKG/{TERYT}_transakcje_ceny.gpkg.zip

Po pobraniu i rozpakowaniu:
    - plik .gpkg jest przenoszony/zmieniany na czytelną nazwę zbudowaną na podstawie
      kolumny "nazwa_pliku" z CSV (np. powiat_piaseczynski_1418.gpkg). Jeśli w CSV
      nie ma takiej kolumny/wartości, używana jest kolumna "obszar" (np. "powiat
      piaseczyński"), a w ostateczności sam kod TERYT.
    - plik jest sprawdzany pod kątem tego, czy nie jest pusty/uszkodzony (otwierany
      jako baza SQLite - GPKG to w środku SQLite - i liczone są rekordy w warstwach).

Wyniki:
    - Data/                              -> pobrane i ładnie nazwane pliki .gpkg
    - Data/_bledy_pobierania.csv         -> kody TERYT, których nie udało się pobrać
    - Data/_puste_lub_uszkodzone.csv     -> pliki, które pobrały się, ale są puste/uszkodzone
    - Data/_status_pobierania.csv        -> pełny status KAŻDEGO terytu (pobrany/blad, plik_ok)

Wymagania:
    pip install requests

Użycie:
    python pobierz_rcn.py
"""

import csv
import re
import sqlite3
import time
import zipfile
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# KONFIGURACJA
# ---------------------------------------------------------------------------

# Wpisz tu swoją ścieżkę główną (folder projektu RCN) - reszta ścieżek
# buduje się automatycznie na jej podstawie. Możesz dowolnie zmieniać
# RAW_PATH albo nadpisać CSV_PATH / OUTPUT_DIR z osobna.
RAW_PATH = r""

# Ścieżka do pliku CSV z listą kodów TERYT (kolumna "teryt")
CSV_PATH = Path(RAW_PATH) / "wyniki_rcn.csv"

# Folder docelowy, do którego mają trafić pobrane pliki
OUTPUT_DIR = Path(RAW_PATH) / "Data"

# Szablon adresu URL - {teryt} zostanie podstawiony kodem z CSV
URL_TEMPLATE = (
    "https://opendata.geoportal.gov.pl/InneDane/latest_exports/"
    "rcn_transakcje_ceny/GPKG/{teryt}_transakcje_ceny.gpkg.zip"
)

# Nazwy kolumn w CSV
TERYT_COLUMN = "teryt"
NAZWA_PLIKU_COLUMN = "nazwa_pliku"   # np. "powiat_piaseczynski_1418.gml"
OBSZAR_COLUMN = "obszar"             # np. "powiat piaseczyński" (zapasowe źródło nazwy)

# Ile sekund odczekać między kolejnymi pobraniami (uprzejmość wobec serwera)
DELAY_BETWEEN_REQUESTS = 0.5

# Timeout pojedynczego żądania (sekundy)
TIMEOUT = 60

# Poniżej jakiego rozmiaru (w bajtach) plik .gpkg uznajemy z góry za podejrzany
MIN_ROZSADNY_ROZMIAR = 1024  # 1 KB

# ---------------------------------------------------------------------------
# LOGIKA SKRYPTU
# ---------------------------------------------------------------------------


def wczytaj_dane_z_csv(csv_path: str) -> list[dict]:
    """Wczytuje unikalne (po teryt) wiersze z CSV, zachowując kolejność.

    Zwraca listę słowników: {"teryt": ..., "nazwa_pliku": ..., "obszar": ...}
    """
    wiersze = []
    widziane = set()
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if TERYT_COLUMN not in reader.fieldnames:
            raise ValueError(
                f"Nie znaleziono kolumny '{TERYT_COLUMN}' w CSV. "
                f"Dostępne kolumny: {reader.fieldnames}"
            )
        for row in reader:
            teryt = (row.get(TERYT_COLUMN) or "").strip()
            if not teryt or teryt in widziane:
                continue
            widziane.add(teryt)
            wiersze.append(
                {
                    "teryt": teryt,
                    "nazwa_pliku": (row.get(NAZWA_PLIKU_COLUMN) or "").strip(),
                    "obszar": (row.get(OBSZAR_COLUMN) or "").strip(),
                }
            )
    return wiersze


def bezpieczna_nazwa(tekst: str) -> str:
    """Zamienia tekst na bezpieczną, plikową nazwę (bez spacji, polskich ogonków
    zostawia jak są, ale usuwa znaki niedozwolone w nazwach plików na Windows)."""
    tekst = tekst.strip()
    tekst = re.sub(r"\s+", "_", tekst)
    tekst = re.sub(r'[<>:"/\\|?*]', "", tekst)
    return tekst


def zbuduj_docelowa_nazwe(teryt: str, nazwa_pliku_csv: str, obszar_csv: str) -> str:
    """Buduje docelową nazwę pliku .gpkg na podstawie danych z CSV.

    Priorytet:
    1. kolumna "nazwa_pliku" z CSV (np. "powiat_piaseczynski_1418.gml" -> ...gpkg)
    2. kolumna "obszar" z CSV (np. "powiat piaseczyński" -> powiat_piaseczynski_1418.gpkg)
    3. sam kod TERYT
    """
    if nazwa_pliku_csv:
        return Path(nazwa_pliku_csv).stem + ".gpkg"
    if obszar_csv:
        return f"{bezpieczna_nazwa(obszar_csv)}_{teryt}.gpkg"
    return f"{teryt}.gpkg"


def znajdz_istniejacy_plik(output_dir: Path, teryt: str) -> Path | None:
    """Szuka w folderze docelowym pliku .gpkg, który już odpowiada danemu terytowi
    (niezależnie od tego, czy nosi 'surową' nazwę, czy już ładną z CSV)."""
    for kandydat in output_dir.glob(f"*{teryt}.gpkg"):
        return kandydat
    return None


def rozpakuj_i_usun_zip(zip_path: Path, output_dir: Path, docelowa_nazwa: str) -> tuple[Path | None, str]:
    """Rozpakowuje ZIP bezpośrednio do output_dir (bez podfolderów),
    zapisując wyłącznie plik .gpkg pod docelowa_nazwa, po czym usuwa archiwum ZIP.

    Zwraca (ścieżka_do_pliku_gpkg_lub_None, komunikat).
    """
    docelowa_sciezka = output_dir / docelowa_nazwa
    zapisano = False
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member.endswith("/") or not member.lower().endswith(".gpkg"):
                    continue
                with zf.open(member) as src, open(docelowa_sciezka, "wb") as dst:
                    dst.write(src.read())
                zapisano = True
                break  # zakładamy jeden plik .gpkg w archiwum
    except zipfile.BadZipFile:
        return None, "błąd: uszkodzony plik ZIP (nie rozpakowano)"

    zip_path.unlink(missing_ok=True)

    if not zapisano:
        return None, "ostrzeżenie: w ZIP nie znaleziono pliku .gpkg (ZIP usunięty)"

    return docelowa_sciezka, f"rozpakowano i usunięto ZIP -> {docelowa_sciezka.name}"


def sprawdz_gpkg(path: Path) -> tuple[bool, str]:
    """Sprawdza, czy plik .gpkg istnieje, ma sensowny rozmiar i zawiera jakiekolwiek
    rekordy w swoich warstwach (GPKG to w środku baza SQLite).

    Zwraca (czy_ok, opis).
    """
    if not path.exists():
        return False, "plik nie istnieje"

    rozmiar = path.stat().st_size
    if rozmiar < MIN_ROZSADNY_ROZMIAR:
        return False, f"plik podejrzanie mały ({rozmiar} B)"

    try:
        conn = sqlite3.connect(str(path))
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM gpkg_contents")
        tabele = [r[0] for r in cur.fetchall()]

        if not tabele:
            conn.close()
            return False, "brak warstw w gpkg_contents (plik pusty/niepoprawny)"

        laczna_liczba_wierszy = 0
        for tabela in tabele:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{tabela}"')
                laczna_liczba_wierszy += cur.fetchone()[0]
            except sqlite3.Error:
                continue
        conn.close()

        if laczna_liczba_wierszy == 0:
            return False, "plik gpkg nie zawiera żadnych rekordów (pusty)"
        return True, f"OK ({laczna_liczba_wierszy} rekordów)"

    except sqlite3.Error as e:
        return False, f"nie udało się otworzyć jako SQLite/GPKG: {e}"


def pobierz_plik(
    teryt: str, nazwa_pliku_csv: str, obszar_csv: str, output_dir: Path, session: requests.Session
) -> tuple[str, bool, str, bool, str]:
    """Pobiera plik ZIP dla danego kodu TERYT, rozpakowuje z niego .gpkg,
    nadaje mu czytelną nazwę i sprawdza, czy nie jest pusty/uszkodzony.

    Zwraca krotkę: (teryt, sukces_pobrania, komunikat_pobrania, plik_ok, komunikat_sprawdzenia)
    """
    docelowa_nazwa = zbuduj_docelowa_nazwe(teryt, nazwa_pliku_csv, obszar_csv)

    istniejacy = znajdz_istniejacy_plik(output_dir, teryt)
    if istniejacy:
        ok, opis = sprawdz_gpkg(istniejacy)
        return teryt, True, f"pominięto (plik już istnieje: {istniejacy.name})", ok, opis

    url = URL_TEMPLATE.format(teryt=teryt)
    zip_path = output_dir / f"{teryt}_transakcje_ceny.gpkg.zip"

    try:
        with session.get(url, stream=True, timeout=TIMEOUT) as resp:
            if resp.status_code == 404:
                return teryt, False, "brak pliku na serwerze (404)", False, "nie pobrano"
            resp.raise_for_status()

            tmp_path = zip_path.with_suffix(zip_path.suffix + ".part")
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            tmp_path.rename(zip_path)

        gpkg_path, komunikat = rozpakuj_i_usun_zip(zip_path, output_dir, docelowa_nazwa)
        if gpkg_path is None:
            return teryt, False, komunikat, False, "nie pobrano"

        ok, opis = sprawdz_gpkg(gpkg_path)
        return teryt, True, komunikat, ok, opis

    except requests.exceptions.RequestException as e:
        return teryt, False, f"błąd: {e}", False, "nie pobrano"


def main() -> None:
    if not RAW_PATH:
        raise SystemExit("Uzupełnij RAW_PATH na górze skryptu przed uruchomieniem.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    wiersze = wczytaj_dane_z_csv(CSV_PATH)
    print(f"Znaleziono {len(wiersze)} unikalnych kodów TERYT do pobrania.")
    print(f"Pliki będą zapisane w: {OUTPUT_DIR}\n")

    wyniki = []
    session = requests.Session()

    for i, wiersz in enumerate(wiersze, start=1):
        teryt = wiersz["teryt"]
        teryt_str, ok, komunikat, plik_ok, opis_sprawdzenia = pobierz_plik(
            teryt, wiersz["nazwa_pliku"], wiersz["obszar"], OUTPUT_DIR, session
        )
        status = "OK " if ok else "BŁĄD"
        znacznik_pliku = "" if plik_ok else "  [PLIK PUSTY/USZKODZONY]"
        print(f"[{i}/{len(wiersze)}] {teryt_str}: {status} - {komunikat}{znacznik_pliku}")
        wyniki.append((teryt_str, ok, komunikat, plik_ok, opis_sprawdzenia))
        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Podsumowanie
    sukcesy = [w for w in wyniki if w[1]]
    porazki = [w for w in wyniki if not w[1]]
    puste_lub_uszkodzone = [w for w in wyniki if w[1] and not w[3]]

    print("\n" + "=" * 60)
    print(f"Podsumowanie: {len(sukcesy)} pobranych / pominiętych, {len(porazki)} błędów pobierania")
    print(f"W tym {len(puste_lub_uszkodzone)} plików pustych/uszkodzonych")
    print("=" * 60)

    if porazki:
        print("\nKody, których NIE udało się pobrać:")
        for teryt, _, komunikat, _, _ in porazki:
            print(f"  - {teryt}: {komunikat}")

        bledy_path = OUTPUT_DIR / "_bledy_pobierania.csv"
        with open(bledy_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["teryt", "komunikat"])
            for teryt, _, komunikat, _, _ in porazki:
                writer.writerow([teryt, komunikat])
        print(f"\nLista błędów pobierania zapisana w: {bledy_path}")

    if puste_lub_uszkodzone:
        print("\nPliki puste/uszkodzone (warto pobrać ponownie / zgłosić):")
        for teryt, _, _, _, opis in puste_lub_uszkodzone:
            print(f"  - {teryt}: {opis}")

        puste_path = OUTPUT_DIR / "_puste_lub_uszkodzone.csv"
        with open(puste_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["teryt", "opis"])
            for teryt, _, _, _, opis in puste_lub_uszkodzone:
                writer.writerow([teryt, opis])
        print(f"\nLista pustych/uszkodzonych plików zapisana w: {puste_path}")

    # Pełny status dla KAŻDEGO terytu (nie tylko problematycznych) - jeden zbiorczy plik
    status_path = OUTPUT_DIR / "_status_pobierania.csv"
    with open(status_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["teryt", "status_pobrania", "komunikat_pobrania", "plik_ok", "opis_sprawdzenia"])
        for teryt, ok, komunikat, plik_ok, opis in wyniki:
            status_pobrania = "pobrany" if ok else "blad"
            plik_ok_str = "tak" if plik_ok else "nie"
            writer.writerow([teryt, status_pobrania, komunikat, plik_ok_str, opis])
    print(f"\nPełny status pobierania (wszystkie {len(wyniki)} terytów) zapisany w: {status_path}")


if __name__ == "__main__":
    main()