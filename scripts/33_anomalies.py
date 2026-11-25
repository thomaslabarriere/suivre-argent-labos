"""Anomalies de déclaration dans Transparence Santé : ce qu'un contrôle de vraisemblance aurait dû arrêter.

Repère, sur la vue nette `ts_net` :
1. les lignes de 10 M€ ou plus (une seule ligne peut peser plusieurs % du total national) ;
2. les avantages « hospitalité, repas, transport » de 20 000 € ou plus pour un seul professionnel ;
3. les professionnels de santé déclarés avec un numéro à 9 chiffres (un SIREN) au lieu d'un RPPS ;
4. les rémunérations de professionnels sans aucun motif, ni texte libre, ni événement ;
5. les montants négatifs.
Une anomalie n'est pas une preuve d'erreur : c'est une ligne à faire vérifier par le déclarant.
Sortie : out/anomalies_declarations.csv (une ligne par déclaration suspecte), résumé à l'écran."""
import duckdb
from commun import RACINE, vues_ts

con = vues_ts(duckdb.connect())
PRS = "beneficiaire_categorie_code = 'PRS'"
COLS = """raison_sociale AS declarant, identite AS beneficiaire, prenom, beneficiaire_categorie AS categorie,
  beneficiaire_identifiant AS identifiant, profession_libelle AS profession, lien_interet, motif_lien_interet AS motif,
  left(coalesce(information_evenement, autre_motif, ''), 120) AS detail, montant, cast(coalesce(date, date_debut) AS DATE) AS date"""
SANS_MOTIF = "coalesce(motif_lien_interet,'') = '' AND coalesce(autre_motif,'') = '' AND coalesce(information_evenement,'') = ''"

a = con.execute(f"""
SELECT 'ligne de 10 M€ ou plus' AS anomalie, {COLS} FROM ts_net WHERE montant >= 1e7
UNION ALL
SELECT 'hospitalité, repas ou transport de 20 000 € ou plus pour une personne', {COLS} FROM ts_net
  WHERE {PRS} AND lien_interet = 'avantage' AND montant >= 20000
    AND (motif_lien_interet ILIKE 'Hospitalit%' OR motif_lien_interet ILIKE '%repas%' OR motif_lien_interet ILIKE '%transport%')
UNION ALL
SELECT 'professionnel déclaré avec un SIREN (1 000 € ou plus)', {COLS} FROM ts_net
  WHERE {PRS} AND regexp_matches(replace(coalesce(beneficiaire_identifiant,''), ' ', ''), '^[0-9]{{9}}$') AND montant >= 1000
UNION ALL
SELECT 'montant négatif', {COLS} FROM ts_net WHERE montant < 0
ORDER BY anomalie, montant DESC""").df()
a.to_csv(RACINE / "out/anomalies_declarations.csv", index=False)

tot = con.execute("SELECT sum(montant) FROM ts_net").fetchall()[0][0]
print(a.groupby("anomalie").montant.agg(["size", "sum"]).assign(pct_total_net=lambda d: (100 * d["sum"] / tot).round(2)).to_string())
print("\nplus grosses lignes :")
print(a[a.anomalie.str.startswith("ligne")].head(10)[["declarant", "beneficiaire", "lien_interet", "motif", "montant", "date"]].to_string())

r = con.execute(f"""SELECT count(*), sum(montant), sum(montant) FILTER (WHERE {SANS_MOTIF}), count(*) FILTER (WHERE {SANS_MOTIF})
  FROM ts_net WHERE {PRS} AND lien_interet = 'remuneration'""").fetchall()[0]
print(f"\nrémunérations de professionnels : {r[1]/1e6:.1f} M€ en {r[0]:,} lignes ; sans aucun motif : "
      f"{r[2]/1e6:.1f} M€ ({100*r[2]/r[1]:.1f} % des euros, {100*r[3]/r[0]:.1f} % des lignes)")
s = con.execute(f"""SELECT count(*), sum(montant) FROM ts_net
  WHERE {PRS} AND regexp_matches(replace(coalesce(beneficiaire_identifiant,''), ' ', ''), '^[0-9]{{9}}$')""").fetchall()[0]
print(f"professionnels déclarés avec un SIREN : {s[0]:,} lignes, {s[1]/1e6:.1f} M€")
