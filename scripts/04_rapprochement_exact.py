"""Étape 3 : rapprochement exact par nom normalisé, dans SIRENE et le RNA.
Ordre des règles, de la plus sûre à la moins sûre :
  0.9  nom identique + même département, un seul identifiant possible
  0.85 sigle entre parenthèses identique + même département, un seul identifiant
  0.8  nom identique, un seul identifiant dans toute la France
Les cas avec plusieurs identifiants possibles sont gardés comme « ambigus » pour l'étape 4."""
from commun import connexion
con = connexion()
deja = "SELECT struct_id FROM ids_caches"
con.execute(f"""CREATE OR REPLACE TABLE cand_exact AS
WITH s AS (SELECT * FROM structures WHERE struct_id NOT IN ({deja})),
-- Correction du 24/11 : on garde aussi les entités fermées (la base couvre 2013 à 2026, beaucoup ont fermé ou fusionné).
-- À égalité, l'entité active est préférée (voir « choix » plus bas).
r AS (SELECT *, (type_id='rna' OR coalesce(etat,'A') NOT IN ('C','F','D','S')) AS actif FROM ref_noms)
SELECT s.struct_id, r.type_id, r.ident, r.actif, 0.9 AS confiance, 'nom + département' AS methode
FROM s JOIN r ON r.nom_norm IN (s.nom_norm, s.nom_sans_par) AND r.dep = s.dep
UNION ALL
SELECT s.struct_id, r.type_id, r.ident, r.actif, 0.85, 'sigle + département'
FROM s JOIN r ON s.sigle_norm IS NOT NULL AND r.nom_norm = s.sigle_norm AND r.dep = s.dep
UNION ALL
SELECT s.struct_id, r.type_id, r.ident, r.actif, 0.8, 'nom, unique en France'
FROM s JOIN r ON r.nom_norm IN (s.nom_norm, s.nom_sans_par)""")
# une association peut avoir à la fois un RNA et un SIREN : on les fusionne via ref_ul.rna
con.execute("""CREATE OR REPLACE TABLE cand_exact AS
SELECT c.struct_id, coalesce(u.siren, c.ident) AS cle, c.type_id, c.ident, c.actif, c.confiance, c.methode
FROM cand_exact c LEFT JOIN ref_ul u ON c.type_id='rna' AND u.rna = c.ident""")
con.execute("""CREATE OR REPLACE TABLE rattachements AS
WITH meilleur AS (SELECT struct_id, max(confiance) AS conf FROM cand_exact GROUP BY 1),
choix AS (SELECT c.struct_id, c.confiance, c.methode, count(DISTINCT c.cle) AS nb_cles,
                 count(DISTINCT c.cle) FILTER (WHERE c.actif) AS nb_actifs, min(c.cle) FILTER (WHERE c.actif) AS cle_active,
                 min(c.cle) AS cle, list(DISTINCT c.type_id||':'||c.ident) AS idents
          FROM cand_exact c JOIN meilleur m ON m.struct_id=c.struct_id AND m.conf=c.confiance GROUP BY 1,2,3)
SELECT struct_id, cle, idents, confiance, methode, 'rattaché' AS statut FROM choix WHERE nb_cles = 1
UNION ALL  -- plusieurs homonymes mais un seul encore actif : on prend l'actif
SELECT struct_id, cle_active, idents[1:10], confiance, methode||' (seul actif)', 'rattaché' FROM choix WHERE nb_cles > 1 AND nb_actifs = 1
UNION ALL
SELECT struct_id, NULL, idents[1:10], confiance, methode, 'ambigu' FROM choix WHERE nb_cles > 1 AND nb_actifs <> 1
UNION ALL
SELECT struct_id, CASE WHEN count(DISTINCT cle)=1 THEN min(cle) END, list(DISTINCT type_id||':'||ident), 1.0,
       'identifiant écrit dans le texte', CASE WHEN count(DISTINCT cle)=1 THEN 'rattaché' ELSE 'ambigu' END
FROM (SELECT c.*, coalesce(u.siren, c.ident) AS cle FROM ids_caches c LEFT JOIN ref_ul u ON c.type_id='rna' AND u.rna=c.ident)
GROUP BY struct_id""")
print(con.execute("""SELECT statut, methode, count(*) AS structures, round(sum(s.montant)/1e6,1) AS meur
FROM rattachements r JOIN structures s USING (struct_id) GROUP BY ALL ORDER BY meur DESC""").df().to_string())
