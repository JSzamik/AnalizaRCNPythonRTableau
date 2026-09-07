#!/usr/bin/env Rscript
# -*- coding: utf-8 -*-
# ============================================================
# EKSTRAKTOR DZIAŁEK + ATRYBUTY RODZAJU Z PLIKÓW GPKG (RCN)
# ============================================================
# Wejście : <DANE_DIR>/transakcje_2015_2026_clean.csv (kategoria transakcje_dzialki)
# Dopasowanie po: nazwa pliku powiatu (zrodlo_plik) + id_transakcji
#               = tran_lokalny_id_iip z tabeli transakcje_dzialki w GPKG
# Dołączane atrybuty: dzi_sposob_uzyt, dzi_przezn_wmpzp, dzi_pow_ewid, dzi_cena_brutto
# Wyjście : <WYNIKI_DIR>/transakcje_dzialki_2015_2026_rodzaj.csv
# ============================================================

suppressPackageStartupMessages({
  library(DBI)
  library(RSQLite)
  library(data.table)
})

# ------------------------------------------------------------
# KONFIGURACJA ŚCIEŻEK
# ------------------------------------------------------------
# Wpisz tu swoją ścieżkę główną (np. lokalny folder na dysku, folder
# zsynchronizowany z repo itd.) - reszta ścieżek buduje się automatycznie
# na jej podstawie. Możesz dowolnie zmieniać RAW_PATH albo nadpisać
# którąkolwiek ze ścieżek poniżej z osobna.

RAW_PATH <- ""

FOLDER_GPKG <- file.path(RAW_PATH, "Data")
PLIK_CZYSTY <- file.path(RAW_PATH, "AnalizaTransakcji", "transakcje_2015_2026_clean.csv")
PLIK_WY     <- file.path(RAW_PATH, "AnalizaTransakcji", "transakcje_dzialki_2015_2026_rodzaj.csv")

# katalog na wyniki - tworzymy, jeśli nie istnieje
dir.create(dirname(PLIK_WY), recursive = TRUE, showWarnings = FALSE)

if (RAW_PATH == "") {
  stop("[BŁĄD] Uzupełnij RAW_PATH na górze skryptu przed uruchomieniem.")
}
if (!dir.exists(FOLDER_GPKG)) {
  stop(sprintf("[BŁĄD] Katalog z plikami GPKG nie istnieje: %s", FOLDER_GPKG))
}
if (!file.exists(PLIK_CZYSTY)) {
  stop(sprintf("[BŁĄD] Plik wejściowy nie istnieje: %s", PLIK_CZYSTY))
}

# tryb (najczęstsza niepusta wartość)
mode_na <- function(v) {
  v <- v[!is.na(v) & v != ""]
  if (length(v) == 0) return(NA_character_)
  names(sort(table(v), decreasing = TRUE))[1]
}

cat("[INFO] Wczytuję działki z pliku czystego...\n")
x <- fread(PLIK_CZYSTY)
dz <- x[kategoria == "transakcje_dzialki"]
rm(x); invisible(gc())
cat(sprintf("[INFO] Działek łącznie: %s (%d powiatów)\n",
            format(nrow(dz), big.mark = " "), uniqueN(dz$zrodlo_plik)))

# lista plików GPKG
gpkg <- list.files(FOLDER_GPKG, pattern = "\\.gpkg$", full.names = TRUE, ignore.case = TRUE)
n_pl <- length(gpkg)
cat(sprintf("[INFO] Plików GPKG: %d\n", n_pl))

# dzielimy działki wg powiatu (zrodlo_plik) - tylko powiaty, dla których są działki
dz[, key := tolower(id_transakcji)]
setkey(dz, zrodlo_plik)
powiaty_dz <- unique(dz$zrodlo_plik)

wszystkie <- list()
licznik <- 0
n_znaleziono_atr <- 0

for (plik in gpkg) {
  nazwa_powiatu <- tools::file_path_sans_ext(basename(plik))
  if (!(nazwa_powiatu %in% powiaty_dz)) next

  licznik <- licznik + 1
  if (licznik %% 25 == 0) cat(sprintf("  [%d/%d] %s ...\n", licznik, n_pl, nazwa_powiatu))

  # działki danego powiatu
  dz_sub <- dz[.(nazwa_powiatu)]

  tryCatch({
    con <- dbConnect(SQLite(), dbname = plik)
    on.exit(try(dbDisconnect(con), silent = TRUE), add = TRUE)

    ## zakładamy obecność tabeli transakcje_dzialki; w razie braku pomijamy
    if (!("transakcje_dzialki" %in% dbListTables(con))) {
      dbDisconnect(con)
      next
    }
    q <- "SELECT tran_lokalny_id_iip, dzi_sposob_uzyt, dzi_przezn_wmpzp, dzi_pow_ewid, dzi_cena_brutto FROM transakcje_dzialki"
    g <- as.data.table(dbGetQuery(con, q))
    dbDisconnect(con)

    if (nrow(g) == 0) {
      wszystkie[[length(wszystkie) + 1]] <- dz_sub
      next
    }

    g[, key := tolower(tran_lokalny_id_iip)]
    # agregacja per transakcja: jedna transakcja moze obejmowac wiele dzialek
    g <- g[, .(
      dzi_sposob_uzyt  = mode_na(dzi_sposob_uzyt),
      dzi_przezn_wmpzp = mode_na(dzi_przezn_wmpzp),
      dzi_pow_ewid     = sum(dzi_pow_ewid, na.rm = TRUE),
      dzi_cena_brutto  = sum(dzi_cena_brutto, na.rm = TRUE)
    ), by = key]

    m <- merge(dz_sub, g, by = "key", all.x = TRUE)
    m[, key := NULL]
    n_znaleziono_atr <- n_znaleziono_atr + sum(!is.na(m$dzi_sposob_uzyt))
    wszystkie[[length(wszystkie) + 1]] <- m
  }, error = function(e) {
    cat(sprintf("    [BŁĄD] %s: %s\n", nazwa_powiatu, e$message))
  })
}

cat("[INFO] Łączę wyniki...\n")
wynik <- rbindlist(wszystkie, fill = TRUE)
cat(sprintf("[INFO] Wierszy w wyniku: %s\n", format(nrow(wynik), big.mark = " ")))

# Jednolita kolejność kolumn
kol_zrodlowe <- c("kategoria", "zrodlo_plik", "id_transakcji", "teryt", "data_transakcji",
                   "rodzaj_transakcji", "rodzaj_nieruchomosci", "rodzaj_rynku",
                   "sprzedajacy", "kupujacy", "cena_brutto", "powierzchnia")
atrybuty <- c("dzi_sposob_uzyt", "dzi_przezn_wmpzp", "dzi_pow_ewid", "dzi_cena_brutto")
brakuje <- setdiff(c(kol_zrodlowe, atrybuty), names(wynik))
for (b in brakuje) wynik[, (b) := NA]
setcolorder(wynik, c(kol_zrodlowe, atrybuty))

fwrite(wynik, PLIK_WY, bom = TRUE)
cat(sprintf("\n[SUKCES] Zapisano: %s (%s rekordów)\n", PLIK_WY, format(nrow(wynik), big.mark = " ")))
cat(sprintf("[INFO] Rekordy z wypełnionym atrybutem dzi_sposob_uzyt: %s\n",
            format(n_znaleziono_atr, big.mark = " ")))
cat("[INFO] Dystrybucja rodzaju działki:\n")
print(wynik[!is.na(dzi_sposob_uzyt), .N, by = dzi_sposob_uzyt][order(-N)])

# ------------------------------------------------------------
# Szybka weryfikacja zapisanego pliku (opcjonalne, uruchamiane tylko
# interaktywnie - nie wykonuje się przy `Rscript ...`)
# ------------------------------------------------------------
if (interactive()) {
  library(rio)
  dane_rodzaj <- import(PLIK_WY)
  print(unique(dane_rodzaj$dzi_sposob_uzyt))
}
