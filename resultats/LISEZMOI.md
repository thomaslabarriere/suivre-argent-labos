# Résultats publiés

Sorties des scripts de `scripts/`, régénérées par `scripts/99_exporter_public.py`. Méthode et définitions :
[docs/RAPPORT.md](../docs/RAPPORT.md).

**À lire avant d'utiliser un fichier nominatif.**

- Les données viennent de sources publiques : Transparence Santé, HATVP, HAS, registre des entreprises.
- Un lien d'intérêt n'est pas une irrégularité : ces versements sont légaux et déclarés.
- Les croisements par nom comportent des homonymes possibles. Regarder la colonne `qualite` (experts HAS ; aucun
  total n'est donné pour un « homonyme possible »), `personnes_meme_nom` (élus) ; les dirigeants ne sont listés que
  s'ils sont payés dans le département de leur structure. Vérifier chaque cas avant de le citer.
- Un montant peut être une erreur du déclarant : voir `anomalies_declarations.csv`. Dans `professionnels_top.csv`,
  `dont_conventions_non_executees` isole les conventions sans versement déclaré (souvent un maximum prévu, pas une
  somme versée) et `alerte` signale les sociétés déclarées comme des personnes.
- Une erreur ? Ouvrez une issue : la ligne sera corrigée ou retirée. La correction à la source se demande à
  l'entreprise déclarante sur transparence.sante.gouv.fr.

| Fichier | Contenu | Script |
|---|---|---|
| `rattachement_structures.csv` | chaque structure sans identifiant et son SIREN / RNA retrouvé | 01 à 08 |
| `arbitrage/` | lots soumis à l'IA, ses décisions et consignes | 07, 08 |
| `test_verite.csv`, `controle_100.csv`, `journal_decisions.csv` | mesure de l'erreur, échantillon de contrôle humain, journal de l'IA | 10, 12 |
| `anomalies_declarations.csv` | déclarations invraisemblables | 33 |
| `prestataires.csv` | bénéficiaires qui sont des prestataires (CRO, agences, grossistes...) | 34 |
| `elus_declarations_vs_versements.csv` | élus payés : le labo est-il cité dans leur déclaration d'intérêts ? | 35 |
| `professionnels_top.csv`, `professionnels_par_profession.csv` | 500 professionnels les mieux payés ; totaux par profession | 24 |
| `elus_beneficiaires.csv`, `elus_liens_labos.csv` | élus parmi les bénéficiaires ; labos cités dans leurs déclarations | 23, 24 |
| `experts_has_versements.csv`, `experts_has_detail_labos.csv` | membres des commissions de la HAS et versements reçus | 27 |
| `croisement_dirigeants_professionnels.csv`, `croisement_structures_dirigees_par_labo.csv` | dirigeants payés à titre personnel ; structures dirigées par un labo payeur | 09, 11 |
| `labos_*`, `groupes_*`, `marques_labos.csv` | remboursements et versements par labo et groupe ; marque, labo, groupe | 21, 30 |
| `asmr_*` | remboursements par niveau de progrès thérapeutique | 26 |
| `lobbying_*` | dépenses et actions de lobbying des labos | 22 |
| `specialites_*`, `labos_cibles_specialites.csv`, `departements_*`, `carte_euros_par_medecin.png` | spécialités et départements | 31, 32 |
| `essais_*` | essais cliniques par labo, établissement et ville | 29 |
| `hopitaux_*`, `marches_hopitaux_labos.csv` | hôpitaux : versements reçus et marchés publics | 28 |
