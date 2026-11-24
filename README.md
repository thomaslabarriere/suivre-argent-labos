# Suivre l'argent des laboratoires

Outils open source pour exploiter [Transparence Santé](https://www.transparence.sante.gouv.fr), la base publique des
liens d'intérêts entre l'industrie de santé et les acteurs de santé en France. Projet né au hackathon Data For Good
Bordeaux au Wagon (24 novembre 2026).

Deux chantiers :

1. **Rattacher les structures sans identifiant.** 520 000 versements à des structures (hôpitaux, sociétés savantes,
   associations, agences) n'ont ni SIREN ni RNA : 5,5 Md€ déclarés. La chaîne `00` à `14` retrouve leur identifiant
   officiel dans SIRENE et le RNA, avec un arbitrage par IA contrôlé et un taux d'erreur mesuré.
2. **Donner du contexte aux montants.** Les scripts `21` à `32` croisent Transparence Santé avec les remboursements de
   l'Assurance maladie, la base des médicaments, la HATVP, l'annuaire des médecins, les marchés publics, les essais
   cliniques et les experts de la HAS.

**Le document complet (méthode, trouvailles, fiche par base, recommandations) : [docs/RAPPORT.md](docs/RAPPORT.md).**

## Ce qu'on trouve

- 6,4 Md€ sont comptés deux fois si l'on additionne les conventions et les rémunérations qui les exécutent.
  Tous les chiffres du projet sont nets.
- 17 312 structures sans identifiant rattachées de façon fiable à leur SIREN ou RNA : 78 % des euros, avec
  une erreur probable mesurée de 2 %.
- 7,3 Md€ remboursés en 2025 (27 %) vont à des médicaments sans progrès thérapeutique selon la HAS (ASMR V).
- Un spécialiste reçoit en moyenne 1 441 € par an des labos, un généraliste 222 €.
- 1 % des professionnels de santé payés reçoivent 51 % des euros.
- 219 paires hôpital × labo combinent versements et marchés publics de 2023 à 2026.

Résultats agrégés : [`resultats/`](resultats/). Rattachement de chaque structure :
[`resultats/rattachement_structures.csv`](resultats/rattachement_structures.csv).

## Installation

Python 3.11 ou plus, `curl`, environ 15 Go de disque libre.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Données

```bash
.venv/bin/python scripts/telecharger.py                      # tout (≈ 11 Go)
.venv/bin/python scripts/telecharger.py ts_autre sirene rna  # chaîne de rattachement seule (≈ 6 Go)
.venv/bin/python scripts/telecharger.py --force ...          # retélécharger
```

Les URL de data.gouv.fr changent à chaque mise à jour : `telecharger.py` les résout par l'API data.gouv.

**Open Medic se télécharge à la main** (le site génère un lien à jeton) :
1. ouvrir https://open-data-assurance-maladie.ameli.fr/medicaments/index.php ;
2. section « Bases complémentaires », année 2025, niveau CIP13 ;
3. enregistrer `NB_2025_cip13.CSV.gz` et `NB_2025_cip13_age_sexe_spe.CSV.gz` dans `data/ext/openmedic/`.

Les essais cliniques (`29`) et la composition des commissions de la HAS (`27`) sont récupérés par leurs scripts.

## Chaîne de rattachement (chantier 1)

```bash
./scripts/run_mensuel.sh          # tout, puis le compte rendu PDF du mois écoulé
```

ou étape par étape (`.venv/bin/python scripts/<script>`) :

| Script | Rôle |
|---|---|
| `01_regrouper.py` | regrouper les variantes de nom (nom normalisé + département) |
| `02_referentiels.py` | préparer SIRENE et RNA |
| `03_identifiants_caches.py` | identifiants écrits dans le texte (clé de Luhn) |
| `04_rapprochement_exact.py` | nom + département, sigle, nom unique en France |
| `05_bilan.py` | contrôle de cohérence |
| `06_rapprochement_approx.py` | rapprochement approximatif (rapidfuzz) |
| `07_file_arbitrage.py 5000` | les 5 000 plus gros cas douteux en lots pour l'IA |
| `08_integrer_arbitrage.py` | contrôle et intégration des décisions, garde-fous homonymes |
| `09_dirigeants.py`, `11_croisement_personnes.py` | dirigeants des sociétés, dirigeants payés à titre personnel |
| `10_echantillon.py` | 100 cas pour un contrôle humain |
| `12_test_verite.py`, `14_test_verite_ia.py` | mesure de l'erreur sans humain |
| `13_rapport.py mois AAAA-MM-01` | compte rendu PDF |

### Arbitrage

`07` écrit `data/arbitrage/lot_NN.jsonl`. Chaque lot est confié à un modèle Claude avec
[`CONSIGNES.md`](resultats/arbitrage/CONSIGNES.md), qui répond dans `decision_NN.jsonl` (une ligne par cas). Nous
l'avons fait avec des sous-agents Claude Code (Haiku 5.5), puis une relecture à l'aveugle des cas hésitants par
Sonnet 5.5 (`revlot_NN` → `revision_NN`). L'IA ne choisit que parmi des candidats trouvés dans les registres et
n'écrit jamais de numéro. Un cas déjà arbitré et inchangé n'est jamais réarbitré (empreinte).

Pour rejouer nos décisions sans IA : copier `resultats/arbitrage/*` dans `data/arbitrage/` avant `08`.

## Croisements (chantier 2)

Pré-requis : `telecharger.py` complet et Open Medic. Ordre : `21` avant `22`, `22` avant `30`, la chaîne de
rattachement avant `28`.

| Script | Question |
|---|---|
| `21_croisement_medicaments.py` | ce que la Sécu rembourse à chaque labo, face à ce qu'il verse |
| `22_lobbying.py` | dépenses de lobbying (HATVP) des labos |
| `23_elus_liens_labos.py` | labos cités dans les déclarations d'intérêts des élus |
| `24_professionnels_elus.py` | argent versé aux professionnels ; élus parmi les bénéficiaires |
| `26_asmr.py` | progrès thérapeutique (ASMR) de ce qui est remboursé |
| `27_experts_has.py` | versements reçus par les experts des commissions de la HAS |
| `28_marches_hopitaux.py` | hôpitaux qui reçoivent de l'argent d'un labo et lui passent des marchés |
| `29_essais_cliniques.py` | essais cliniques industriels et conventions de recherche |
| `30_marques_labos.py` | qui est qui : marque → labo → groupe |
| `31_specialites_carte.py`, `32_carte.py` | euros par médecin, par spécialité et par département ; carte |
| `99_exporter_public.py` | copie les agrégats publiables dans `resultats/` |

## Organisation

```
scripts/     code (commun.py : fonctions partagées)
data/        données téléchargées et base DuckDB de travail (non versionné)
out/         sorties complètes, dont fichiers nominatifs (non versionné)
resultats/   agrégats publiés
docs/        RAPPORT.md
```

## Précautions

Un lien d'intérêt n'est pas une irrégularité : ces versements sont légaux et déclarés. Les rapprochements par nom
comportent des homonymes possibles. Ce dépôt ne publie aucune donnée nominative de personne physique (voir
[docs/RAPPORT.md, section 9](docs/RAPPORT.md#9-données-personnelles-et-publication)).

Code sous licence MIT ; données sous la licence de leur producteur (Licence Ouverte / Etalab 2.0 pour la plupart).
