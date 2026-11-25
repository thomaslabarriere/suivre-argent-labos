# État du projet

**Clôturé le 25 novembre 2026.** Tout ce qu'il faut pour reprendre est ici ; le reste de la documentation est à jour
à cette date.

## Où on en est

- Hackathon Data For Good Bordeaux au Wagon, 24 novembre 2026. Le travail a été poursuivi et consolidé le
  lendemain : revue complète du code par deux relectures indépendantes, corrections, tests, publication.
- Dépôt public : https://github.com/thomaslabarriere/suivre-argent-labos (compte GitHub `thomaslabarriere`).
- Mail envoyé le 25 novembre 2026 à l'équipe Euros For Docs (contact@eurosfordocs.fr), avec `docs/synthese.pdf`
  en pièce jointe. Demandé : savoir si le travail leur est utile, si des journalistes s'en servent, et proposé
  d'aider plus tard. Pas de réponse à la date de clôture.
- État de la vérification : 74 tests automatiques et 175 contrôles sur les vraies données passent ;
  GitHub relance les tests à chaque push.

## Ce que fait Euros For Docs, et ce que ce projet ajoute

Lu sur https://www.eurosfordocs.fr/data le 25 novembre 2026 (dernière actualité du site : mai 2024).

| Sujet | Euros For Docs | Ce projet |
|---|---|---|
| Double compte convention / versements liés | oui : retire de la convention les montants liés, minimum zéro | retire toute la convention dès qu'un versement s'y rattache (le reliquat est perdu, souvent un plafond) |
| Soignants sans RPPS | réattribution par nom et profession dans l'annuaire RPPS | non fait : 464 soignants « coupés en deux » (`out/personnes_coupees.csv`, 12,6 M€) |
| Identifiants absurdes | retire NA, 0 | retire aussi [SO] et les RPPS portés par plus de 5 noms |
| Groupes de labos | regroupement manuel | règles automatiques (`commun.groupe_labo`) |
| Structures sans identifiant → SIREN / RNA | non trouvé | 17 312 structures fiables, erreur mesurée 2,0 % |
| Croisements (Open Medic, HAS, HATVP, DECP, essais) | non trouvé | scripts 21 à 35 |
| Prestataires, anomalies de montants | non trouvé | scripts 33 et 34 |
| Tests, contrat sur les sources | non trouvé | `tests/`, `contrat_entrees.py`, `controle.py` |

## Reprendre le projet

1. Lire, dans l'ordre : ce fichier, [FONCTIONNEMENT.md](FONCTIONNEMENT.md) (les briques), puis
   [RAPPORT.md](RAPPORT.md) sections 7 et 8 (pièges et défauts déjà corrigés).
2. Les grosses données ont été supprimées le 25 novembre 2026 pour libérer 10 Go. Sur la machine d'origine, `data/`
   ne garde que ce qui ne se retélécharge pas (28 Mo) : décisions de l'IA (`arbitrage/`, et sa sauvegarde d'avant
   migration), test de vérité figé (`test_verite/`), caches des dirigeants et des personnes (appels d'API évités),
   Open Medic (téléchargé à la main), essais cliniques, composition des commissions HAS, contours des départements.
   Avant toute relance : `scripts/telecharger.py` (≈ 10 Go), puis toute la chaîne depuis `01`. La base de travail
   `travail.duckdb` et les caches dérivés (`conventions_liees`, `rpps_valides`, `prestataires`) se recréent seuls.
   Les décisions de l'IA sont aussi publiées dans `resultats/arbitrage/`.
3. Après tout nouveau téléchargement : `scripts/contrat_entrees.py`. S'il échoue, une source a changé de forme :
   regarder quoi avant de relancer quoi que ce soit, puis `--maj` si le changement est légitime.
4. Relancer la chaîne (README, section Démarrage), puis `scripts/chiffres_cles.py` : les écarts disent ce qui a
   bougé depuis la clôture. `--maj` réécrit `docs/chiffres_cles.json`, puis mettre à jour les documents et
   `scripts/synthese_pdf.py`.
5. Avant tout push : `scripts/controle.py`. Ne rien publier s'il échoue.

**Nouvelle année de données.** Les années récentes grossissent à chaque mise à jour (2026 était partielle à la
clôture). `telecharger.py` récupère l'année en cours ; le contrat accepte la hausse des volumes.

**Nouvel arbitrage IA.** `07` crée les lots, un modèle Claude répond selon `resultats/arbitrage/CONSIGNES.md`, `08`
intègre. Les cas déjà arbitrés et inchangés ne repartent jamais à l'IA. Une clé API Anthropic, si on en utilise une,
va dans `.env` (ignoré par git) et nulle part ailleurs.

## Ce qui reste ouvert

Par ordre d'utilité :

1. **Réattribuer les RPPS des soignants déclarés sans numéro**, comme Euros For Docs : fusionnerait les 464
   personnes coupées en deux. Risque à mesurer : mélanger deux homonymes du même département.
2. **Garder le reliquat des conventions** (méthode Euros For Docs) plutôt que de retirer toute la convention, et
   mesurer l'écart sur les totaux.
3. **Contrôle humain** : `out/controle_humain.csv` (100 noms) et `out/controle_100.csv` (100 rattachements) n'ont
   pas été vérifiés à la main. C'est la seule mesure qui ne dépend pas de notre code.
4. **Proposer la table de rattachement à Euros For Docs** sous une forme qu'ils peuvent joindre à leur base, s'ils
   répondent.
5. Les suites de [RAPPORT.md, section 11](RAPPORT.md#11-ce-quon-pourrait-faire-ensuite).

## À savoir

- **Données nominatives publiées** (`resultats/`) : choix fait le 25 novembre 2026, données publiques, avec
  précautions (homonymes signalés, aucun total pour un homonyme possible). Point juridique non tranché :
  article R1453-7 du code de la santé publique et RGPD (RAPPORT, section 9).
- **Pour les journalistes**, l'angle le plus solide est la qualité de la base publique elle-même (ligne de
  445 M€, 98 % des rémunérations sans motif), pas des personnes. Aucun constat ne prouve une faute individuelle.
- `scripts/25_rapport_nouvelles_bases.py` (local, non versionné) contient les chiffres du 24 novembre, faux depuis
  la revue. Ne pas le réutiliser.
- Le compte GitHub du dépôt est `thomaslabarriere`, pas `Polo-1233`.
