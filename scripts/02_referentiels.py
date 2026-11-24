"""Prépare les annuaires officiels pour le rapprochement.
- ref_ul    : une ligne par unité légale SIRENE (personnes morales), avec noms normalisés.
- ref_noms  : (nom normalisé, département, identifiant) pour SIRENE et RNA, toutes variantes de nom.
"""
import glob
from commun import connexion, RACINE
con = connexion()
UL = RACINE / "data/ref/sirene_ul.parquet"; ET = RACINE / "data/ref/sirene_etab.parquet"
RNA = sorted(glob.glob(str(RACINE / "data/ref/rna/**/*.csv"), recursive=True))

# 1. SIRENE, unités légales personnes morales (on écarte les entrepreneurs individuels, catégorie 1000)
con.execute(f"""CREATE OR REPLACE TABLE ref_ul AS
SELECT siren, denominationUniteLegale AS denomination, sigleUniteLegale AS sigle,
       denominationUsuelle1UniteLegale AS denom_usuelle, categorieJuridiqueUniteLegale AS cat_juridique,
       etatAdministratifUniteLegale AS etat, identifiantAssociationUniteLegale AS rna,
       activitePrincipaleUniteLegale AS ape
FROM read_parquet('{UL}') WHERE denominationUniteLegale IS NOT NULL""")
# 2. départements où chaque unité légale a un établissement (+ enseignes)
con.execute(f"""CREATE OR REPLACE TABLE ref_etab AS
SELECT siren, dep(codePostalEtablissement) AS dep, enseigne1Etablissement AS enseigne,
       denominationUsuelleEtablissement AS denom_etab, etatAdministratifEtablissement AS etat_etab
FROM read_parquet('{ET}') WHERE siren IN (SELECT siren FROM ref_ul)""")
con.execute("""CREATE OR REPLACE TABLE ref_noms AS
WITH deps AS (SELECT DISTINCT siren, dep FROM ref_etab WHERE dep IS NOT NULL),
noms AS (
  SELECT siren, norm(denomination) n, 'denomination' src FROM ref_ul
  UNION SELECT siren, norm(sigle), 'sigle' FROM ref_ul WHERE sigle IS NOT NULL
  UNION SELECT siren, norm(denom_usuelle), 'denom_usuelle' FROM ref_ul WHERE denom_usuelle IS NOT NULL)
SELECT 'siren' AS type_id, n.siren AS ident, n.n AS nom_norm, d.dep, n.src, u.etat
FROM noms n JOIN ref_ul u USING (siren) LEFT JOIN deps d USING (siren) WHERE n.n IS NOT NULL
UNION ALL
SELECT DISTINCT 'siren', siren, norm(coalesce(enseigne, denom_etab)), dep, 'enseigne', etat_etab
FROM ref_etab WHERE coalesce(enseigne, denom_etab) IS NOT NULL""")
# 3. RNA (répertoire des associations, fichiers waldec par département)
if RNA:
    fichiers = "[" + ",".join(f"'{f}'" for f in RNA) + "]"
    con.execute(f"""CREATE OR REPLACE TABLE ref_rna AS
    SELECT id AS rna, siret, titre, titre_court, adrs_codepostal AS cp, position, date_disso
    FROM read_csv({fichiers}, delim=';', header=true, all_varchar=true, ignore_errors=true, union_by_name=true)""")
    con.execute("""INSERT INTO ref_noms
    SELECT 'rna', rna, norm(titre), dep(cp), 'titre', position FROM ref_rna WHERE titre IS NOT NULL
    UNION ALL SELECT 'rna', rna, norm(titre_court), dep(cp), 'titre_court', position FROM ref_rna WHERE titre_court IS NOT NULL
    UNION ALL SELECT 'rna', rna, sigle(titre), dep(cp), 'sigle_titre', position FROM ref_rna WHERE sigle(titre) IS NOT NULL""")
con.execute("DELETE FROM ref_noms WHERE nom_norm IS NULL OR length(nom_norm) < 3")
con.execute("CREATE OR REPLACE TABLE ref_noms AS SELECT DISTINCT * FROM ref_noms")
for t in ["ref_ul","ref_etab","ref_rna","ref_noms"]:
    try: print(t, f"{con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:,}")
    except Exception: print(t, "absent")
