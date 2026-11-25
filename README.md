# Suivre l'argent des laboratoires

Outils open source pour exploiter [Transparence Santé](https://www.transparence.sante.gouv.fr), la base publique des
liens d'intérêts entre l'industrie de santé et les acteurs de santé en France. Projet né au hackathon Data For Good
Bordeaux au Wagon (24 novembre 2026).

[![tests](https://github.com/thomaslabarriere/suivre-argent-labos/actions/workflows/tests.yml/badge.svg)](https://github.com/thomaslabarriere/suivre-argent-labos/actions/workflows/tests.yml)

Deux chantiers :

1. **Rattacher les structures sans identifiant.** 520 000 versements à des structures (hôpitaux, sociétés savantes,
   associations, agences) n'ont ni SIREN ni RNA : 5,5 Md€ déclarés. La chaîne `01` à `14` retrouve leur identifiant
   officiel dans SIRENE et le RNA, avec un arbitrage par IA contrôlé et un taux d'erreur mesuré.
2. **Donner du contexte aux montants.** Les scripts `21` à `35` croisent Transparence Santé avec les remboursements de
   l'Assurance maladie, la base des médicaments, la HATVP, l'annuaire des médecins, les marchés publics, les essais
   cliniques et les experts de la HAS.

## Ce qu'on trouve

- 6,4 Md€ sont comptés deux fois si l'on additionne les conventions et les rémunérations qui les exécutent.
  Tous les chiffres du projet sont nets.
- 17 312 structures sans identifiant rattachées de façon fiable à leur SIREN ou RNA : 78 % des euros, avec
  une erreur probable mesurée de 2,0 %.
- 36 % de l'argent net déclaré paie des prestataires (agences, CRO, informatique, conseil) ; hors prestataires, 8,2 Md€.
- 35 déclarations de 10 M€ ou plus pèsent 10 % du total ; la plus grosse (445 M€) ressemble à une erreur de saisie.
- 7,3 Md€ remboursés en 2025 (27 %) vont à des médicaments sans progrès thérapeutique selon la HAS (ASMR V).
- Un spécialiste reçoit en moyenne 1 441 € par an des labos, un généraliste 222 €.
- 1 % des professionnels de santé payés reçoivent 50 % des euros.
- 212 paires hôpital × labo combinent versements et marchés publics de 2023 à 2026.

## Les documents

| Document | Contenu |
|---|---|
| [docs/A_RETENIR.md](docs/A_RETENIR.md) | les onze constats principaux, en une page |
| [docs/FONCTIONNEMENT.md](docs/FONCTIONNEMENT.md) | comment marche chaque brique : ce qu'elle lit, produit, ses pièges, comment la réutiliser |
| [docs/RAPPORT.md](docs/RAPPORT.md) | la méthode complète, une fiche par base de données, les recommandations et les suites possibles |
| [resultats/LISEZMOI.md](resultats/LISEZMOI.md) | les fichiers de résultats, y compris nominatifs, et les précautions de lecture |
| [docs/synthese.pdf](docs/synthese.pdf) | deux pages à faire circuler |

## Les briques

```
 [1] Téléchargement ──> [2] Contrat sur les sources
        |
        +── [3] Rattachement des structures (01-08) ── [4] Arbitrage par IA ── [5] Mesure de l'erreur (10-14)
        |
        +── [6] Croisements (21-35), sur [0] le socle commun : vue nette, identité des personnes, groupes de labos
        |
 [7] Contrôles et tests ──> [8] Export ──> resultats/
```

Le détail de chaque brique est dans [docs/FONCTIONNEMENT.md](docs/FONCTIONNEMENT.md).

## Démarrage

Python 3.11 ou plus, `curl`, environ 15 Go de disque libre.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q                                 # 74 tests, sans données, 2 secondes

.venv/bin/python scripts/telecharger.py                       # sources (≈ 11 Go) ; URL à jour via l'API data.gouv
.venv/bin/python scripts/contrat_entrees.py                   # les sources ont-elles changé de forme ?
./scripts/run_mensuel.sh                                      # chaîne de rattachement + compte rendu PDF
for s in 21 22 23 24 26 27 28 29 30 31 32 33 34 35; do .venv/bin/python scripts/${s}_*.py; done
.venv/bin/python scripts/99_exporter_public.py                # résultats publiés dans resultats/
.venv/bin/python scripts/controle.py                          # contrôles avant publication ; ne rien publier s'il échoue
```

**Open Medic se télécharge à la main** (le site génère un lien à jeton) :
1. ouvrir https://open-data-assurance-maladie.ameli.fr/medicaments/index.php ;
2. section « Bases complémentaires », année 2025, niveau CIP13 ;
3. enregistrer `NB_2025_cip13.CSV.gz` et `NB_2025_cip13_age_sexe_spe.CSV.gz` dans `data/ext/openmedic/`.

**Rejouer l'arbitrage sans IA :** copier `resultats/arbitrage/*` dans `data/arbitrage/` avant l'étape `08`.

## Organisation

```
scripts/     code (commun.py : règles partagées)
tests/       tests automatiques, mini jeu fictif, référence des sources
data/        données téléchargées et base DuckDB de travail (non versionné)
out/         sorties de travail (non versionné)
resultats/   résultats publiés
docs/        documents, chiffres_cles.json
```

## Précautions

Un lien d'intérêt n'est pas une irrégularité : ces versements sont légaux et déclarés. Les rapprochements par nom
comportent des homonymes possibles. Les fichiers nominatifs reprennent des données publiques ; une erreur se signale
par une issue (voir [docs/RAPPORT.md, section 9](docs/RAPPORT.md#9-données-personnelles-et-publication)).

Code sous licence MIT ; données sous la licence de leur producteur (Licence Ouverte / Etalab 2.0 pour la plupart).
