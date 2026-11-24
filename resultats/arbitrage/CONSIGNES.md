# Consignes d'arbitrage

Contexte : base publique Transparence Santé. Des laboratoires déclarent des versements à des structures (hôpitaux,
associations, sociétés savantes, agences…) sans leur identifiant officiel. Pour chaque cas, on a le nom déclaré
(plusieurs écritures possibles), le département, l'adresse, le montant total, et des candidats trouvés dans les
registres officiels SIRENE (siren:...) et RNA des associations (rna:W...).

Ta tâche : pour chaque cas, dire quel candidat est la structure qui a réellement reçu l'argent, ou « aucun ».

## Règles
1. Le bénéficiaire est l'entité juridique principale. Un service, un pôle, une DRCI, un « siège » ou un site d'hôpital
   se rattache à l'hôpital lui-même (le CHU, le CH, l'AP-HP…), pas à une structure annexe.
2. Ne choisis PAS une structure annexe qui porte le même nom : CSE, comité d'entreprise, amicale du personnel,
   crèche, syndicat, association d'anciens, club sportif, cafétéria, fondation, sauf si le nom déclaré le dit
   explicitement (ex. « Fondation de l'AP-HP » → la fondation).
3. Un mot commun (ville, « FRANCE », « MEDICAL », « CONSEIL ») ne suffit pas. Il faut que le cœur du nom corresponde.
4. `nom_rapproche` est le nom (souvent une enseigne ou un ancien nom) par lequel le candidat a été trouvé :
   il compte autant que `nom`.
5. Une entité « actif: false » peut être la bonne (données sur plusieurs années, fusions). Préfère l'active à égalité.
6. `etablissement_dans_le_departement: true` est un indice fort. `forme` et `ape` (code NAF) aident :
   86.10Z = hôpital, 72.xx = recherche, 73.11Z = agence de publicité, 94.12Z = organisation professionnelle.
7. Si aucun candidat ne convient mais que tu connais avec certitude l'entité réelle (ex. « CHU de Pontchaillou » =
   Centre hospitalier universitaire de Rennes), mets `choix: "aucun"` et écris son nom officiel complet dans
   `nom_propose`. N'invente JAMAIS de numéro SIREN ou RNA.
8. Dans le doute, `choix: "aucun"` avec `confiance: "basse"`. Une erreur coûte plus cher qu'un « aucun ».

## Format de sortie
Un fichier JSONL : exactement une ligne par cas, dans le même ordre que le lot, et rien d'autre :
{"id": 7, "choix": "siren:390704484", "confiance": "haute", "nom_propose": null, "raison": "Essence Mediacom est l'enseigne de Mediacom Paris"}
- `choix` : une `cle` copiée à l'identique depuis `candidats`, ou "aucun".
- `confiance` : "haute", "moyenne" ou "basse".
- `nom_propose` : null, sauf règle 7.
- `raison` : 15 mots maximum, en français.
