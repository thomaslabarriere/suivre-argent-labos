"""Étape 2 : retrouver les identifiants officiels déjà écrits dans les champs texte (cas A).
On cherche un RNA (W + 9 caractères), un SIRET (14 chiffres) ou un SIREN (9 chiffres, clé de Luhn valide)
dans l'identifiant déclaré, le nom et l'adresse, puis on vérifie qu'il existe dans l'annuaire officiel."""
from commun import connexion
con = connexion()
con.execute("""CREATE OR REPLACE MACRO luhn_ok(s) AS (
  list_sum(list_transform(range(length(s)), lambda i:
     CASE WHEN (length(s) - i) % 2 = 0
          THEN (CASE WHEN 2*cast(s[i+1] AS INT) > 9 THEN 2*cast(s[i+1] AS INT) - 9 ELSE 2*cast(s[i+1] AS INT) END)
          ELSE cast(s[i+1] AS INT) END)) % 10 = 0)""")
con.execute("""CREATE OR REPLACE TABLE ids_caches AS
WITH txt AS (
  SELECT struct_id, unnest(list_concat(ids_bruts, variantes, adresses)) AS t FROM structures),
cand AS (
  SELECT struct_id, 'rna' AS type_id, unnest(regexp_extract_all(upper(t), '\\bW[0-9A-Z][0-9]{8}\\b')) AS ident FROM txt
  UNION ALL
  SELECT struct_id, 'siret', unnest(regexp_extract_all(regexp_replace(regexp_replace(t, '(\\d)[ .](\\d)', '\\1\\2', 'g'), '(\\d)[ .](\\d)', '\\1\\2', 'g'), '\\b\\d{14}\\b')) FROM txt
  UNION ALL
  SELECT struct_id, 'siren', unnest(regexp_extract_all(regexp_replace(regexp_replace(t, '(\\d)[ .](\\d)', '\\1\\2', 'g'), '(\\d)[ .](\\d)', '\\1\\2', 'g'), '\\b\\d{9}\\b')) FROM txt)
SELECT DISTINCT struct_id,
  CASE WHEN type_id='siret' THEN 'siren' ELSE type_id END AS type_id,
  CASE WHEN type_id='siret' THEN substr(ident,1,9) ELSE ident END AS ident
FROM cand""")
# vérification dans les annuaires
con.execute("""CREATE OR REPLACE TABLE ids_caches AS
SELECT c.*, 1.0 AS confiance, 'identifiant écrit dans le texte' AS methode FROM ids_caches c
WHERE (type_id='siren' AND luhn_ok(ident) AND ident IN (SELECT siren FROM ref_ul)
        -- on écarte le SIREN des laboratoires déclarants, souvent recopié par erreur
        AND ident NOT IN (SELECT DISTINCT siren_declarant FROM lignes WHERE siren_declarant IS NOT NULL))
   OR (type_id='rna' AND ident IN (SELECT rna FROM ref_rna))""")
r = con.execute("""SELECT count(DISTINCT struct_id), round(sum(montant)/1e6,1) FROM structures
                   WHERE struct_id IN (SELECT struct_id FROM ids_caches)""").fetchone()
print(f"Étape 2 : {r[0]:,} structures retrouvées par un identifiant caché, {r[1]} M€")
print(con.execute("SELECT type_id, count(*) n FROM ids_caches GROUP BY 1").df().to_string())
