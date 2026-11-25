"""Étape 7b : un dirigeant (personne physique) d'une structure payée par un labo reçoit-il AUSSI de l'argent
de ce même labo à titre personnel, comme professionnel de santé ?
Montants nets des deux côtés : `prs` (versements aux professionnels, commun.vue_professionnels) et `lignes_net`
(versements aux structures). Correspondance par nom + premier prénom exacts (normalisés), donc des homonymes sont
possibles : le fichier publié ne garde que les cas où la personne est payée dans le département de la structure
(`dep_identique`). Chaque cas est à vérifier."""
import pandas as pd
from commun import connexion, RACINE, vue_lignes_net
con = vue_lignes_net(connexion())
con.execute("""CREATE OR REPLACE TEMP TABLE pers AS SELECT DISTINCT d.siren, d.nom, d.prenoms,
  nn(d.nom) nom_n, split_part(nn(replace(coalesce(d.prenoms, ''), ',', ' ')), ' ', 1) prenom_n
  FROM dirigeants d JOIN final2 f ON f.identifiant2 = d.siren
  WHERE d.type_dirigeant = 'personne physique' AND d.nom IS NOT NULL AND f.statut2 = 'fiable'""")
print("personnes :", con.execute("SELECT count(*) FROM pers").fetchone()[0])
pp = con.execute("""SELECT p.siren, p.nom, p.prenoms, t.raison_sociale AS labo_perso, t.profession_libelle AS profession,
  t.dep AS dep_perso, sum(t.montant) AS montant_perso, count(*) AS nb_perso
  FROM pers p JOIN prs t ON t.nom_n = p.nom_n AND t.prenom_n = p.prenom_n
  WHERE p.prenom_n <> '' GROUP BY ALL""").df()
con.register("pp", pp)
# Labo regroupé par son nom normalisé sans formes juridiques (ROCHE = ROCHE SAS). Montants agrégés AVANT la jointure
# pour ne rien compter deux fois. dep_identique : la personne est payée dans le département de la structure (moins de risque d'homonyme).
con.execute("""CREATE OR REPLACE TABLE croisement_personnes AS
WITH perso AS (
  SELECT siren, nom, prenoms, norm(labo_perso) AS labo, string_agg(DISTINCT profession, ', ') AS profession,
         list(DISTINCT dep_perso) AS deps_perso, sum(montant_perso) AS recu_personnellement, sum(nb_perso) AS nb_versements_perso
  FROM pp GROUP BY 1,2,3,4),
struct AS (
  SELECT f.identifiant2 AS siren, min(f.nom_officiel) AS structure, min(f.dep) AS dep_structure,
         norm(l.raison_sociale) AS labo, min(l.raison_sociale) AS laboratoire, sum(l.montant) AS verse_a_la_structure
  FROM final2 f JOIN lignes_net l ON l.struct_id=f.struct_id WHERE f.statut2='fiable' GROUP BY f.identifiant2, norm(l.raison_sociale))
SELECT s.siren, s.structure, p.nom, p.prenoms, p.profession, s.laboratoire,
  round(p.recu_personnellement) AS recu_personnellement, p.nb_versements_perso, round(s.verse_a_la_structure) AS verse_a_la_structure,
  list_contains(p.deps_perso, s.dep_structure) AS dep_identique
FROM perso p JOIN struct s USING (siren, labo)
ORDER BY dep_identique DESC, verse_a_la_structure DESC""")
con.execute("""CREATE OR REPLACE TABLE croisement_groupe AS
SELECT siren_beneficiaire, min(f.nom_officiel) AS nom_beneficiaire, norm(laboratoire) AS labo, min(laboratoire) AS laboratoire,
  string_agg(DISTINCT dirigeant, ' ; ' ORDER BY dirigeant) AS dirigeant, max(montant_du_labo) AS montant_du_labo
FROM croisement_groupe g LEFT JOIN final2 f ON f.identifiant2=g.siren_beneficiaire GROUP BY 1, 3 ORDER BY montant_du_labo DESC""")
print(con.execute("""SELECT count(*) lignes, count(DISTINCT siren) structures, count(DISTINCT nom||coalesce(prenoms,'')) personnes,
  count(*) FILTER (WHERE dep_identique) lignes_meme_dep, count(DISTINCT siren) FILTER (WHERE dep_identique) structures_meme_dep,
  count(DISTINCT siren) FILTER (WHERE dep_identique AND recu_personnellement>=5000) structures_meme_dep_5k FROM croisement_personnes""").df().to_string())
print(con.execute("SELECT count(*), count(DISTINCT siren_beneficiaire) FROM croisement_groupe").fetchone(), "lignes / structures dirigées par un labo payeur")
con.execute(f"COPY (SELECT * EXCLUDE (dep_identique) FROM croisement_personnes WHERE dep_identique) TO '{RACINE}/out/croisement_dirigeants_professionnels.csv' (HEADER)")
con.execute(f"COPY croisement_groupe TO '{RACINE}/out/croisement_structures_dirigees_par_labo.csv' (HEADER)")
