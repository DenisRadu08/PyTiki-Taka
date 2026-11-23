# ==============================================================================
# PyTiki-Taka — MARATON GENETIC AI 6.5 - 7 ORE (TRUE-ENGINE 1:1 + ANTI-LUCK CRN)
# ==============================================================================
# Simuleaza ~62.340 de meciuri 100% REALE 1:1 (ambele reprize + schimbul de teren
# la pauza + toate regulile FIFA + faze fixe + 26 gene tactice) in 4 etape:
#   - Etapa 1: 70 generatii x 36 echipe x 12 meciuri vs Base Build (30.240 meciuri)
#   - Etapa 2: Liga Campionilor Hall of Fame Top 30 x 30 meciuri     (900 meciuri)
#   - Etapa 3: 60 generatii x 36 echipe x 14 meciuri vs Top 4 Boss  (30.240 meciuri)
#   - Etapa 4: Examen Final 100 meciuri vs Base + 12m H2H Finala      (960 meciuri)
#
# Salveaza automat:
#   - Log complet in models/genetic_archive/marathon_log_YYYYMMDD_HHMMSS.txt
#   - Checkpoint la fiecare 10 generatii in models/genetic_archive/checkpoint_latest.json
#   - Model unic arhivat in models/genetic_archive/genetic_league_YYYYMMDD_HHMMSS.json
#   - Actualizeaza models/genetic_best.json cu noul Campion Suprem 1:1!
# ==============================================================================

New-Item -ItemType Directory -Force -Path "models\genetic_archive" | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "models\genetic_archive\marathon_log_$ts.txt"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "  PORNIRE MARATON GENETIC AI (6.5 - 7 ORE | ~62.340 MECIURI REALE 1:1)" -ForegroundColor Cyan
Write-Host "  Log salvat automat in: $logFile" -ForegroundColor Yellow
Write-Host "  Sfaturi: Conecteaza laptopul la priza si opreste Sleep-ul din Windows!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Cyan

$env:PYTHONIOENCODING = "utf-8"
py -u train_genetic.py --stage1-gens 70 --stage3-gens 60 --pop 36 --matches 12 --ticks 1800 --hof 30 --final-matches 100 2>&1 | Tee-Object -FilePath $logFile
