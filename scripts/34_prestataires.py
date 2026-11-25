"""Séparer les prestataires des bénéficiaires au sens de la loi.

Transparence Santé enregistre comme « bénéficiaires » des sociétés qui ne reçoivent pas un avantage mais le prix
d'un service : sociétés de recherche clinique sous contrat (CRO), grossistes, agences de communication et
d'événementiel, hôtels, voyagistes, éditeurs informatiques. Additionner ces flux aux versements faits aux
soignants et aux hôpitaux gonfle les totaux et fausse les comparaisons entre labos.

Classement d'un bénéficiaire personne morale, dans cet ordre :
1. son nom contient celui d'une grande CRO ou d'un grand grossiste (liste NOMS, utile pour les sociétés étrangères) ;
2. sinon, s'il a un SIREN (déclaré, ou retrouvé par la chaîne de rattachement), son activité principale INSEE (APE)
   et sa catégorie juridique : seules les sociétés commerciales (catégorie 5xxx ou étrangère 3xxx) sont classées
   prestataires ; une association ou un établissement public de recherche (APE 72.19Z) reste un bénéficiaire.
Les professionnels de santé, étudiants, établissements FINESS ne sont jamais des prestataires ici.
Limite assumée : une CRO déclarée sans SIREN et absente de NOMS reste comptée comme bénéficiaire.
Sorties : out/prestataires.csv (un bénéficiaire classé par ligne), data/ext/prestataires.parquet (id de ligne → type),
résumé à l'écran avec les totaux avec et sans prestataires."""
import duckdb
from commun import RACINE, DB, vues_ts, sql_chemin

NOMS = {  # motif sur le nom normalisé -> type
    r"\b(IQVIA|QUINTILES|IMS HEALTH|SYNEOS|INC RESEARCH|PAREXEL|ICON (CLINICAL|PLC)|PPD (DEVELOPMENT|FRANCE)|COVANCE|LABCORP"
    r"|FORTREA|MEDPACE|PRA HEALTH|PSI CRO|WORLDWIDE CLINICAL|CROMSOURCE|NOVOTECH|PHARMALEX|CLINIPACE|PREMIER RESEARCH"
    r"|ADVANCED CLINICAL|SIRO CLINPHARM|CLINACT|KAPPA SANTE|EXCELYA|ITEC SERVICES|IDDI)\b": "recherche sous contrat (CRO)",
    r"\b(ALLIANCE HEALTHCARE|OCP REPARTITION|CERP|PHOENIX PHARMA|CSP CENTRE SPECIALITES)\b": "grossiste, répartiteur",
}
APE = {  # préfixe APE -> type (sociétés commerciales seulement)
    "72.1": "recherche sous contrat (CRO)", "71.20B": "recherche sous contrat (CRO)",
    "46.46": "grossiste, répartiteur", "46.69": "grossiste, répartiteur", "46.18": "grossiste, répartiteur",
    "73.11": "communication, marketing, études", "73.12": "communication, marketing, études",
    "73.20": "communication, marketing, études", "70.21": "communication, marketing, études",
    "70.22": "conseil", "82.30": "événementiel, congrès", "79.": "voyage, hôtellerie, restauration",
    "55.": "voyage, hôtellerie, restauration", "56.": "voyage, hôtellerie, restauration",
    "62.0": "informatique, données", "63.1": "informatique, données", "58.2": "informatique, données",
}

con = vues_ts(duckdb.connect())
con.execute(f"ATTACH '{sql_chemin(DB)}' AS w (READ_ONLY)")
cas_ape = " ".join(f"WHEN n.ape LIKE '{k}%' THEN '{v}'" for k, v in APE.items())
cas_nom = " ".join(f"WHEN regexp_matches(n.nom, '{k}') THEN '{v}'" for k, v in NOMS.items())
con.execute(f"""CREATE TABLE cl AS
WITH b AS (
  SELECT t.id, t.montant, t.identite, t.beneficiaire_categorie_code cat,
         upper(strip_accents(coalesce(t.identite, ''))) nom,
         CASE WHEN t.beneficiaire_type_code = 'SIREN' THEN left(regexp_replace(t.beneficiaire_identifiant, '[^0-9]', '', 'g'), 9)
              WHEN f.identifiant2 ~ '^[0-9]{{9}}$' THEN f.identifiant2 END siren
  FROM ts_net t
  LEFT JOIN w.lignes l ON l.id = t.id
  LEFT JOIN w.final2 f ON f.struct_id = l.struct_id AND f.statut2 = 'fiable'
  WHERE t.beneficiaire_categorie_code NOT IN ('PRS', 'ETU', 'VET', 'INF') AND t.beneficiaire_type_code <> 'FINESS'),
n AS (SELECT b.*, u.ape, u.cat_juridique, u.denomination FROM b LEFT JOIN w.ref_ul u USING (siren))
SELECT id, montant, identite, cat, siren, ape, cat_juridique, denomination,
  CASE {cas_nom}
       WHEN cast(n.cat_juridique AS VARCHAR) ~ '^[35]' THEN CASE {cas_ape} END
  END AS type_prestataire
FROM n""")
con.execute(f"COPY (SELECT id, type_prestataire FROM cl WHERE type_prestataire IS NOT NULL) TO '{sql_chemin(RACINE / 'data/ext/prestataires.parquet')}'")

tot = con.execute("SELECT sum(montant) FROM ts_net").fetchall()[0][0]
r = con.execute("""SELECT type_prestataire, count(*) lignes, count(DISTINCT coalesce(siren, identite)) beneficiaires,
  round(sum(montant) / 1e6, 1) meur FROM cl WHERE type_prestataire IS NOT NULL GROUP BY 1 ORDER BY meur DESC""").df()
r["pct_total_net"] = (100 * r.meur * 1e6 / tot).round(1)
print(r.to_string())
p = r.meur.sum() * 1e6
# Presse et éditeurs de logiciels sont des catégories que la loi nomme : on les montre à part.
print(con.execute("""SELECT cat AS categorie_declaree, round(sum(montant) / 1e6, 1) meur FROM cl
  WHERE type_prestataire IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""").df().to_string())
print(f"\ntotal net déclaré : {tot/1e9:.2f} Md€ ; dont prestataires : {p/1e9:.2f} Md€ ({100*p/tot:.1f} %) ; "
      f"hors prestataires : {(tot-p)/1e9:.2f} Md€")
top = con.execute("""SELECT type_prestataire, coalesce(denomination, min(identite)) beneficiaire, siren, ape,
  count(*) lignes, round(sum(montant)) euros FROM cl WHERE type_prestataire IS NOT NULL
  GROUP BY type_prestataire, coalesce(denomination, identite), siren, ape, denomination ORDER BY euros DESC, beneficiaire""").df()
top = top.groupby(["type_prestataire", "beneficiaire", "siren", "ape"], dropna=False, as_index=False)[["lignes", "euros"]].sum() \
    .sort_values(["euros", "beneficiaire"], ascending=[False, True])
top.to_csv(RACINE / "out/prestataires.csv", index=False)
print("\n", top.head(15).to_string())
