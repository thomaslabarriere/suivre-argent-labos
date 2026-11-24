"""Étape 1 : charger les lignes « AUTRE » (structures) et regrouper les variantes d'une même structure.
Clé de regroupement : nom normalisé + département. Résultat : table `structures`.
Tout est déterministe (listes triées, égalités départagées) : deux exécutions sur les mêmes données donnent le même résultat.
Un code postal étranger ne donne pas de département (Milan 20100 n'est pas la Corse)."""
from commun import connexion, RACINE, sql_chemin
con = connexion()
src = RACINE / "data/raw/ts_autre_structures.parquet"
con.execute(f"""CREATE OR REPLACE TABLE lignes AS
SELECT id, entreprise_id, raison_sociale, numero_siren AS siren_declarant, lien_interet, motif_lien_interet,
       try_cast(montant AS DOUBLE) AS montant, try_cast(date AS DATE) AS date,
       identite, beneficiaire_identifiant, coalesce(pays_code,'FR') AS pays, beneficiaire_categorie, adresse,
       regexp_extract(coalesce(code_postal,''), '[0-9]{{5}}') AS cp, ville,
       coalesce(sans_parentheses(identite), norm(identite)) AS nom_norm, norm(identite) AS nom_complet, sigle(identite) AS sigle_norm, sans_parentheses(identite) AS nom_sans_par,
       CASE WHEN coalesce(pays_code,'FR') IN ('FR','') THEN dep(regexp_extract(coalesce(code_postal,''), '[0-9]{{5}}')) END AS dep
FROM read_parquet('{sql_chemin(src)}')""")
# Valeur la plus fréquente d'une colonne dans chaque structure, égalités départagées par ordre alphabétique
# (mode() et any_value() départagent au hasard, ce qui changeait le nom affiché d'une exécution à l'autre).
def mode_det(col, alias):
    return f"""{alias} AS (SELECT nom_norm, dep, {col} AS v FROM (
      SELECT nom_norm, dep, {col}, row_number() OVER (PARTITION BY nom_norm, dep ORDER BY count(*) DESC, {col}) r
      FROM lignes WHERE nom_norm IS NOT NULL AND {col} IS NOT NULL GROUP BY 1, 2, 3) WHERE r = 1)"""
COLS = {"categorie": "beneficiaire_categorie", "pays": "pays", "sigle_norm": "sigle_norm", "nom_sans_par": "nom_complet", "cp": "cp"}
ctes = ",\n".join(mode_det(c, "m_" + a) for a, c in COLS.items())
joins = "\n".join(f"LEFT JOIN m_{a} ON m_{a}.nom_norm = g.nom_norm AND m_{a}.dep IS NOT DISTINCT FROM g.dep" for a in COLS)
con.execute(f"""CREATE OR REPLACE TABLE structures AS
WITH {ctes},
v AS (SELECT nom_norm, dep, list(identite ORDER BY n DESC, identite) l, count(*) nb FROM
        (SELECT nom_norm, dep, identite, count(*) n FROM lignes WHERE nom_norm IS NOT NULL GROUP BY ALL) GROUP BY ALL),
g AS (SELECT nom_norm, dep,
       list(DISTINCT beneficiaire_identifiant ORDER BY beneficiaire_identifiant) FILTER (WHERE beneficiaire_identifiant IS NOT NULL)[1:10] AS ids_bruts,
       list(DISTINCT adresse ORDER BY adresse)[1:3] AS adresses, count(*) AS nb_lignes, coalesce(sum(montant),0) AS montant
     FROM lignes WHERE nom_norm IS NOT NULL GROUP BY nom_norm, dep)
SELECT row_number() OVER (ORDER BY g.montant DESC, g.nom_norm, g.dep NULLS FIRST) AS struct_id, g.nom_norm, g.dep,
       {", ".join(f"m_{a}.v AS {a}" for a in COLS)},
       v.l[1:8] AS variantes,   -- la variante la plus fréquente d'abord : c'est elle qui sert de « nom déclaré »
       v.nb AS nb_variantes, g.ids_bruts, g.adresses, g.nb_lignes, g.montant
FROM g JOIN v ON v.nom_norm = g.nom_norm AND v.dep IS NOT DISTINCT FROM g.dep
{joins}""")
# rattache chaque ligne à sa structure
con.execute("""CREATE OR REPLACE TABLE lignes AS SELECT l.*, s.struct_id FROM lignes l
LEFT JOIN structures s ON s.nom_norm = l.nom_norm AND s.dep IS NOT DISTINCT FROM l.dep""")
r = con.execute("""SELECT (SELECT count(*) FROM lignes), (SELECT count(DISTINCT identite) FROM lignes),
  (SELECT count(*) FROM structures), (SELECT round(sum(montant)/1e9,2) FROM lignes),
  (SELECT count(*) FROM lignes WHERE struct_id IS NULL)""").fetchone()
print(f"Lignes : {r[0]:,} | noms bruts distincts : {r[1]:,} | structures après regroupement : {r[2]:,} | montant : {r[3]} Md€ | lignes sans nom : {r[4]:,}")
print(con.execute("SELECT struct_id, categorie, nb_variantes, variantes[1:4] AS ex, round(montant/1e6,1) AS meur FROM structures ORDER BY nb_variantes DESC LIMIT 5").df().to_string())
