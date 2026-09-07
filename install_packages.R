# Pakiety R wymagane przez analiza_extract_dzialki.R
# Uruchom raz: Rscript install_packages.R

pakiety <- c("DBI", "RSQLite", "data.table", "rio")

brakujace <- pakiety[!(pakiety %in% installed.packages()[, "Package"])]
if (length(brakujace) > 0) {
  install.packages(brakujace, repos = "https://cloud.r-project.org")
} else {
  cat("Wszystkie pakiety są już zainstalowane.\n")
}
