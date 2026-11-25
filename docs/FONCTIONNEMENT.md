# Comment ça marche

Une fiche par brique : ce qu'elle lit, ce qu'elle produit, ses pièges, comment la tester et comment la réutiliser
seule. Les résultats et la méthode détaillée sont dans [RAPPORT.md](RAPPORT.md).

```
 sources publiques
       |
 [1] Téléchargement ──> [2] Contrat sur les sources
       |
       +──────────────────────────────+
       |                              |
 [3] Rattachement des structures   [6] Croisements (21 à 35)
       |                              |   s'appuient sur [0] : ts_net, identité des personnes, groupes de labos
 [4] Arbitrage par IA                 |
       |                              |
 [5] Mesure de l'erreur               |
       |                              |
       +──────────────+───────────────+
                      |
              [7] Contrôles et tests
                      |
              [8] Export et publication ──> resultats/
```

Toutes les briques passent par `scripts/commun.py` [0]. Chaque script se lance seul :
`.venv/bin/python scripts/<script>`. La variable `SUIVRE_RACINE` fait tourner n'importe quel script sur un autre
dossier de données, ce qu'utilisent les tests.

---

## [0] Socle commun : `scripts/commun.py`

Les règles qu'il ne faut écrire qu'une fois. Chaque bug grave du projet venait d'une règle réécrite différemment dans
deux scripts.

| Élément | Ce qu'il fait |
|---|---|
| `vues_ts(con)` | Vue `ts` (toutes les déclarations, parquet annuels) et vue `ts_net` : sans les conventions déjà exécutées par des rémunérations ou avantages liés (`convention_liee`, 6,4 Md€ de double compte). |
| `vue_professionnels(con)` | Vue `prs` : lignes nettes vers les professionnels, avec une clé `personne` fiable (voir ci-dessous). |
| `vue_lignes_net(con)` | Les lignes « structures » de la base de travail, en net. |
| `groupe_labo(nom)` | Le groupe d'un labo (Janssen et J&J ensemble, MSD distinct de Merck KGaA, Mylan dans Viatris...). |
| `nn`, `dep_norm`, `chiffres`, `norm`, `dep` | Normalisation des noms, des départements (974 et 2A compris), des identifiants et des noms de structures. |
| `cle_structure`, `empreinte` | Identité stable d'une structure et d'un cas d'arbitrage, indépendante des numéros internes. |

**Identité d'un professionnel.** Le champ identifiant contient aussi des valeurs factices (« [SO] », « 0 », « NA »,
« 00000000000 ») partagées par des milliers de personnes. Un RPPS n'est retenu que s'il a 11 chiffres, commence
par 10, respecte la clé de Luhn et ne porte pas plus de 5 noms différents. Sinon, la personne est identifiée par nom,
premier prénom et département normalisés. Les RPPS valides sont mis en cache dans `data/ext/rpps_valides.parquet`.

**Réutiliser.** C'est la brique la plus utile à reprendre telle quelle : la règle de double compte et la règle
d'identité s'appliquent à toute exploitation de Transparence Santé.

---

## [1] Téléchargement : `scripts/telecharger.py`

- **Lit :** l'API de data.gouv.fr, qui donne l'URL à jour de chaque ressource.
- **Produit :** `data/` (environ 11 Go) : Transparence Santé par année, SIRENE, RNA, BDPM, HATVP, RPPS, DECP,
  contours des départements.
- **Pièges :**
  - Les URL de data.gouv changent à chaque mise à jour : ne jamais les écrire en dur.
  - L'export complet de Transparence Santé est tronqué sans message d'erreur : on télécharge année par année et on
    vérifie que chaque parquet se termine par `PAR1`.
  - Open Medic se télécharge à la main (lien à jeton, voir README).
- **Lancer :** `telecharger.py` pour tout, `telecharger.py ts_autre sirene rna` pour le rattachement seul,
  `--force` pour retélécharger.

## [2] Contrat sur les sources : `scripts/contrat_entrees.py`

- **Lit :** les fichiers de `data/` et la référence versionnée `tests/reference_entrees.json`.
- **Vérifie :**
  - **Colonnes :** chaque colonne attendue est présente, avec le même type.
  - **Volume :** le nombre de lignes ne baisse pas de plus de 3 %.
  - **Codes :** aucune valeur nouvelle ou disparue dans les champs codés (type de lien, catégorie et type
    d'identifiant du bénéficiaire).
  - **Années :** aucune année ne manque.
- **Pourquoi :** une source qui change ne fait pas planter le code, elle fausse les chiffres en silence. Exemple :
  une nouvelle catégorie de bénéficiaire serait ignorée par tous les filtres.
- **Lancer :** après chaque téléchargement. Après avoir vérifié un changement légitime, `--maj` réécrit la référence.

---

## [3] Rattachement des structures : scripts `01` à `08`

520 000 versements à des structures n'ont ni SIREN ni RNA exploitable (5,5 Md€ bruts). La chaîne retrouve leur
identifiant officiel. Base de travail : `data/travail.duckdb`.

| Étape | Lit | Produit |
|---|---|---|
| `01_regrouper` | `data/raw/ts_autre_structures.parquet` | tables `lignes` et `structures` : 88 105 structures (nom normalisé + département) |
| `02_referentiels` | SIRENE, RNA | `ref_ul`, `ref_etab`, `ref_noms`, `ref_rna` |
| `03_identifiants_caches` | `structures` | SIREN, SIRET ou RNA écrits dans le nom ou l'adresse (clé de Luhn vérifiée) |
| `04_rapprochement_exact` | `structures`, `ref_noms` | nom + département, sigle, nom unique en France |
| `05_bilan` | tout | contrôle de cohérence |
| `06_rapprochement_approx` | idem | `cand_approx` : 6 meilleurs candidats par structure (rapidfuzz) ; `approx_auto` : acceptés sans IA |
| `07_file_arbitrage 5000` | `cand_approx` | `data/arbitrage/lot_NN.jsonl` : les 5 000 plus gros cas douteux |
| `08_integrer_arbitrage` | lots + décisions | `final2`, `out/rattachement_final.csv` |

- **Pièges :**
  - 39 écritures différentes pour l'AP-HP.
  - Le SIREN du labo déclarant est parfois écrit dans le champ du bénéficiaire.
  - Un nom de famille peut ressembler à un nom de société.
  - Le score de similarité « inclus dans » donne 100 à « PARIS » face à « ESSENCEMEDIACOM PARIS » : on prend la
    moyenne de deux scores.
- **Garde-fous (08) :**
  - Les catégories qui désignent souvent une personne (étudiant, influenceur, vétérinaire) ne sont jamais déclarées
    fiables par le seul nom.
  - Un homonyme (même nom, autre département, autre activité) rétrograde le rattachement.
- **Réutiliser :** `resultats/rattachement_structures.csv` donne pour chaque structure son identifiant, la méthode,
  la confiance et le statut. On peut la joindre à n'importe quel extrait de Transparence Santé par nom normalisé et
  département, sans relancer la chaîne.

## [4] Arbitrage par IA : `07` et `08`

- **Principe :**
  - L'IA ne choisit qu'entre des candidats déjà trouvés dans les registres, ou répond « aucun ».
  - Elle n'écrit jamais de numéro, donc ne peut pas en inventer.
  - Elle donne une confiance et une raison.
- **Consignes :** [`resultats/arbitrage/CONSIGNES.md`](../resultats/arbitrage/CONSIGNES.md).
- **Format :** une ligne JSON par cas dans `decision_NN.jsonl`.
- **Qui :**
  - premier passage : Claude Haiku 5.5 ;
  - relecture à l'aveugle des cas hésitants : Sonnet 5.5 (`revlot_NN` vers `revision_NN`).
- **Figeage :**
  - Chaque cas porte une empreinte (structure + candidats triés).
  - Un cas inchangé n'est jamais réarbitré.
  - Une décision dont l'empreinte ne correspond plus est rejetée : « périmée ».
  - Une décision qui ne correspond à aucun cas est rejetée : « orpheline ».
- **Rejouer sans IA :** copier `resultats/arbitrage/*` dans `data/arbitrage/` avant `08`.
- **Automatiser :** remplacer les sous-agents par l'API Claude en mode batch (lecture d'un lot, écriture des
  décisions au même format).

## [5] Mesure de l'erreur : `10`, `12`, `14`

- **`12_test_verite` :**
  - Prend les 13 552 structures dont l'identifiant était écrit dans le texte et efface cet identifiant.
  - Rejoue les règles et compare au vrai numéro.
  - Résultat : 2,0 % d'erreur probable sur les réponses « fiables ».
  - Le lot de test est figé (`data/test_verite/decision_test.jsonl`) pour que la mesure reste comparable.
- **`14_test_verite_ia` :** la même mesure pour les décisions de l'IA.
- **`10_echantillon` :** 100 cas tirés au hasard, avec graine fixe, pour un contrôle humain (`out/controle_100.csv`).

## Dirigeants : `09` et `11`

- **`09` :**
  - Récupère les dirigeants des sociétés rattachées (API recherche-entreprises, mise en cache).
  - Repère les structures dirigées par le labo qui les paie (exemple : le GERS).
- **`11` :**
  - Repère un dirigeant payé aussi à titre personnel par le même labo.
  - Le rapprochement se fait sur le nom et le premier prénom exacts, avec des montants nets.
  - Seuls les cas dans le département de la structure sont publiés.

---

## [6] Croisements : scripts `21` à `35`

Tous lisent `ts_net` (et `prs` pour les personnes) via [0].

| Script | Croise avec | Produit |
|---|---|---|
| `21_croisement_medicaments` | Open Medic, BDPM | remboursé par labo et groupe face au versé |
| `22_lobbying` | répertoire HATVP des représentants d'intérêts | dépenses et actions de lobbying des groupes payeurs |
| `23_elus_liens_labos` | déclarations d'intérêts HATVP | labos cités par les élus (actions, emplois, conseil) |
| `24_professionnels_elus` | liste des déclarants HATVP | 500 professionnels les mieux payés, totaux par profession, élus parmi les bénéficiaires |
| `26_asmr` | avis ASMR de la HAS (BDPM), Open Medic | remboursements par niveau de progrès thérapeutique |
| `27_experts_has` | composition des commissions HAS | versements reçus par chaque expert, avant et pendant son mandat |
| `28_marches_hopitaux` | DECP (marchés publics), rattachement | hôpitaux payés par un labo et qui lui passent des marchés |
| `29_essais_cliniques` | ClinicalTrials.gov | essais par labo et établissement, face aux conventions de recherche |
| `30_marques_labos` | BDPM, Open Medic | marque, labo titulaire, groupe |
| `31_specialites_carte`, `32_carte` | RPPS, Open Medic | euros par médecin, par spécialité et par département ; carte |
| `33_anomalies` | aucun | déclarations invraisemblables |
| `34_prestataires` | SIRENE (activité, catégorie juridique) | sociétés payées pour un service (CRO, agences, informatique...) ; marquage ligne à ligne `data/ext/prestataires.parquet` |
| `35_elus_declarations` | déclarations HATVP | pour chaque élu payé, le labo est-il cité dans sa déclaration ? |

**Ordre :**
- `21` avant `22`, et `22` avant `30` ;
- `24` avant `35` ;
- la chaîne de rattachement avant `09`, `11`, `28` et `34`.

**Pièges communs :**
- **Montants :** une convention sans versement est souvent un plafond, pas une somme versée.
- **DECP :** les montants des marchés sont des maxima.
- **Open Medic :** les montants sont au format « 8.739.219,66 ».
- **Groupes :** un nom de labo seul, sans groupe, mélange des filiales.

---

## [7] Contrôles et tests

| Outil | Quand | Ce qu'il garantit |
|---|---|---|
| `pytest` (`tests/`, 74 tests, 2 s) | à chaque modification ; GitHub le lance à chaque push | fonctions de normalisation ; un test par bug déjà corrigé, sur un mini jeu fictif (`tests/donnees_test.py`) ; contrat sur les sources |
| `scripts/contrat_entrees.py` | après chaque téléchargement | les sources n'ont pas changé de forme |
| `scripts/chiffres_cles.py` | après chaque relance | les 37 chiffres cités dans les documents n'ont pas bougé et y figurent tels quels (`docs/chiffres_cles.json`) |
| `scripts/controle.py` (environ 1 min) | avant toute publication | tout ce qui précède, plus reproductibilité, identités, doublons, montants recalculés ligne à ligne, recoupements entre fichiers, seuil d'erreur du rattachement (3 %), `resultats/` à jour, absence de secret |

`controle.py` produit aussi deux listes à relire :
- `out/controle_humain.csv` : les 20 premiers noms de chaque fichier nominatif ;
- `out/personnes_coupees.csv` : les soignants dont une partie des lignes n'a pas de RPPS, et dont le total est donc
  coupé en deux.

**Ajouter un test quand on corrige un bug :** ajouter le piège dans `tests/donnees_test.py` (quelques lignes
fictives), puis le résultat attendu dans `tests/test_regressions.py`.

## [8] Export et publication : `scripts/99_exporter_public.py`

- **Fait :**
  - Copie dans `resultats/` la liste explicite des fichiers publiés.
  - Écrit `rattachement_structures.csv` et les lots d'arbitrage.
  - Tout ce qui n'est pas dans la liste reste dans `out/`, non versionné.
- **Publication :** lancer `controle.py` ; ne rien publier s'il échoue.

## Synthèse PDF : `scripts/synthese_pdf.py`

Produit `docs/synthese.pdf`, deux pages sans nom de personne, à partir de `docs/chiffres_cles.json` : la synthèse ne
peut pas contredire les autres documents. À relancer après `chiffres_cles.py --maj`.

## Compte rendu mensuel : `13_rapport.py`, `run_mensuel.sh`

`run_mensuel.sh` enchaîne la chaîne de rattachement, s'arrête s'il reste des lots sans décision, puis produit un PDF
du mois écoulé : versements, structures identifiées, nouveaux bénéficiaires.
