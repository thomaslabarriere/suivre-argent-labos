#!/usr/bin/env bash
# Compte rendu mensuel : retélécharge les données, rejoue la chaîne, prépare les cas nouveaux ou modifiés pour
# l'arbitrage, s'arrête s'il reste des lots sans décision, sinon intègre et produit le PDF du mois écoulé.
# Usage : ./scripts/run_mensuel.sh [AAAA-MM-01]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
MOIS="${1:-$("$PY" -c 'import datetime as d; t=d.date.today().replace(day=1); print((t-d.timedelta(days=1)).replace(day=1))')}"
./scripts/00_telecharger.sh --force
for s in 01_regrouper 02_referentiels 03_identifiants_caches 04_rapprochement_exact 05_bilan 06_rapprochement_approx; do
  "$PY" scripts/$s.py
done
"$PY" scripts/07_file_arbitrage.py 5000     # n'écrit que les cas nouveaux ou modifiés (empreinte)
attente=$(for f in data/arbitrage/lot_*.jsonl; do d=${f/lot_/decision_}; [ -s "$d" ] || echo "$f"; done)
if [ -n "$attente" ]; then
  echo "Lots à arbitrer avant de continuer (voir README, section Arbitrage) :"; echo "$attente"; exit 2
fi
for s in 08_integrer_arbitrage 09_dirigeants 10_echantillon 11_croisement_personnes 12_test_verite; do
  "$PY" scripts/$s.py
done
"$PY" scripts/13_rapport.py mois "$MOIS"
