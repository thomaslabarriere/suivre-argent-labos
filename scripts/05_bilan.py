"""Bilan des étapes 1 à 3 : couverture en nombre et en euros, par catégorie, et exemples à vérifier."""
from commun import connexion, RACINE
con = connexion()
out = RACINE / "out"
base = """SELECT s.*, r.cle, r.idents, r.confiance, r.methode, coalesce(r.statut,'non rattaché') AS statut,
  u.denomination AS nom_officiel, u.cat_juridique, u.ape
FROM structures s LEFT JOIN (SELECT * FROM rattachements QUALIFY row_number() OVER (PARTITION BY struct_id ORDER BY statut DESC, confiance DESC)=1) r USING (struct_id)
LEFT JOIN ref_ul u ON u.siren = r.cle"""
con.execute(f"CREATE OR REPLACE TABLE resultat AS {base}")
print("\n== Couverture globale")
print(con.execute("""SELECT statut, count(*) structures, sum(nb_lignes) lignes, round(sum(montant)/1e9,3) AS md_eur,
  round(100*sum(montant)/sum(sum(montant)) OVER (),1) AS pct_eur FROM resultat GROUP BY 1 ORDER BY md_eur DESC""").df().to_string())
print("\n== Par catégorie (% des euros rattachés)")
print(con.execute("""SELECT categorie, count(*) structures, round(sum(montant)/1e6) AS meur,
  round(100*sum(montant) FILTER (WHERE statut='rattaché')/nullif(sum(montant),0),1) AS pct_rattache
FROM resultat GROUP BY 1 ORDER BY meur DESC""").df().to_string())
print("\n== Sociétés savantes, fondations, organismes de conseil : 15 plus gros montants")
print(con.execute("""SELECT struct_id, variantes[1] AS nom_declare, dep, statut, cle, nom_officiel, confiance, round(montant/1e6,2) meur
FROM resultat WHERE categorie LIKE 'Académie%' ORDER BY montant DESC LIMIT 15""").df().to_string())
con.execute(f"COPY (SELECT * EXCLUDE (adresses) FROM resultat ORDER BY montant DESC) TO '{out}/structures_rattachement.csv' (HEADER)")
con.execute(f"""COPY (SELECT * FROM resultat WHERE statut='rattaché' AND confiance < 1 USING SAMPLE 100 ROWS (reservoir, 42))
  TO '{out}/echantillon_a_verifier.csv' (HEADER)""")
print(f"\nFichiers : {out}/structures_rattachement.csv et {out}/echantillon_a_verifier.csv")

# Contrôle de cohérence : le nom déclaré ressemble-t-il au nom officiel ? (rapidfuzz, 0 à 100)
from rapidfuzz import fuzz
import unidecode, re
def n(x): return re.sub(r"[^A-Z0-9 ]+"," ",unidecode.unidecode(x if isinstance(x, str) else "").upper())   # NaN -> ""
df = con.execute("""SELECT r.struct_id, s.variantes[1] AS declare, coalesce(u.denomination, rn.titre) AS officiel, u.sigle
FROM rattachements r JOIN structures s USING (struct_id)
LEFT JOIN ref_ul u ON u.siren=r.cle LEFT JOIN ref_rna rn ON rn.rna=r.cle WHERE r.statut='rattaché'""").df()
df["coherence"] = [max(fuzz.token_set_ratio(n(a), n(b)), fuzz.ratio(n(a), n(c)) if isinstance(c, str) else 0) for a,b,c in zip(df.declare, df.officiel, df.sigle)]
con.register("coh", df[["struct_id","coherence"]])
con.execute("CREATE OR REPLACE TABLE coherence AS SELECT struct_id, max(coherence) AS coherence FROM coh GROUP BY 1")
print("\n== Cohérence des noms pour les structures rattachées (en M€)")
print(con.execute("""SELECT CASE WHEN c.coherence>=80 THEN '1. nom très proche (>=80)' WHEN c.coherence>=50 THEN '2. nom assez proche (50-79)'
  ELSE '3. nom différent (<50), à vérifier' END AS niveau, count(*) structures, round(sum(s.montant)/1e6) meur
FROM coherence c JOIN structures s USING (struct_id) GROUP BY 1 ORDER BY 1""").df().to_string())
print("\nExemples de noms différents (à vérifier) :")
print(con.execute("""SELECT s.variantes[1] AS declare, d.officiel, round(s.montant/1e6,2) meur, c.coherence
FROM coherence c JOIN structures s USING (struct_id) JOIN (SELECT * FROM df) d USING (struct_id)
WHERE c.coherence<50 ORDER BY s.montant DESC LIMIT 12""").df().to_string())

# Statut final, prudent : un rattachement n'est « fiable » que si le nom officiel ressemble au nom déclaré,
# que la structure n'est pas une personne (étudiant, influenceur, vétérinaire) et que le nom n'est pas un mot court et banal.
con.execute("""CREATE OR REPLACE TABLE final AS
SELECT s.struct_id, s.variantes[1] AS nom_declare, s.categorie, s.dep, s.nb_lignes, s.montant,
  r.cle AS identifiant, r.methode, c.coherence,
  coalesce(u.denomination, rn.titre) AS nom_officiel,
  CASE WHEN r.statut='rattaché' AND c.coherence>=80
            AND s.categorie NOT IN ('Etudiant','Influenceur','Vétérinaire')
            AND NOT (r.methode LIKE 'nom, unique en France%' AND length(s.nom_norm)<8 AND s.nom_norm NOT LIKE '% %')
       THEN 'fiable'
       WHEN r.statut='rattaché' THEN 'à vérifier'
       WHEN r.statut='ambigu' THEN 'plusieurs candidats'
       ELSE 'non rattaché' END AS statut_final
FROM structures s
LEFT JOIN (SELECT * FROM rattachements QUALIFY row_number() OVER (PARTITION BY struct_id ORDER BY statut DESC, confiance DESC)=1) r USING (struct_id)
LEFT JOIN coherence c USING (struct_id)
LEFT JOIN ref_ul u ON u.siren=r.cle LEFT JOIN ref_rna rn ON rn.rna=r.cle""")
print("\n== BILAN FINAL")
print(con.execute("""SELECT statut_final, count(*) structures, round(sum(montant)/1e9,2) md_eur,
  round(100*sum(montant)/sum(sum(montant)) OVER (),1) pct_eur FROM final GROUP BY 1 ORDER BY md_eur DESC""").df().to_string())
print("\n== Sociétés savantes, fondations, organismes de conseil")
print(con.execute("""SELECT statut_final, count(*) structures, round(sum(montant)/1e9,2) md_eur,
  round(100*sum(montant)/sum(sum(montant)) OVER (),1) pct_eur FROM final WHERE categorie LIKE 'Académie%' GROUP BY 1 ORDER BY md_eur DESC""").df().to_string())
con.execute(f"COPY (SELECT * FROM final ORDER BY montant DESC) TO '{out}/rattachement_final.csv' (HEADER)")
con.execute(f"""COPY (SELECT * FROM final WHERE statut_final='fiable' USING SAMPLE 100 ROWS (reservoir, 42))
  TO '{out}/echantillon_fiables_a_controler.csv' (HEADER)""")
