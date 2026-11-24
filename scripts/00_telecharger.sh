#!/usr/bin/env bash
# Étape 0 : sources de la chaîne de rattachement (extrait Transparence Santé « AUTRE », SIRENE, RNA), ~6 Go.
# Les URL à jour sont résolues par l'API data.gouv.fr (voir telecharger.py). Ajouter --force pour retélécharger.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
"$PY" scripts/telecharger.py "$@" ts_autre sirene rna
