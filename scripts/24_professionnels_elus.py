"""Argent versé aux professionnels de santé, et responsables publics parmi les bénéficiaires.

1. Par profession, et les 500 professionnels les mieux payés. Montants nets (`ts_net`, voir commun.vues_ts).
   Une personne = son RPPS quand il est valide, sinon nom + premier prénom + département normalisés
   (vue `prs`, commun.vue_professionnels ; les identifiants factices comme [SO] ou 0 ne servent jamais de clé).
   Une convention restée dans la vue nette n'est exécutée par aucun versement déclaré : son montant est souvent un
   maximum prévu. Colonne `dont_conventions_non_executees` pour le distinguer de l'argent versé.
2. Les responsables publics (liste HATVP) qui portent le même nom, le même premier prénom et le même département
   qu'un professionnel payé. Un déclarant HATVP sans département n'est jamais rapproché. Homonymes possibles :
   `personnes_meme_nom` compte les professionnels distincts qui correspondent au même élu.
Sorties : out/professionnels_par_profession.csv, out/professionnels_top.csv, out/elus_beneficiaires.csv"""
import re, unidecode, pandas as pd, duckdb
from commun import RACINE, vues_ts

con = vues_ts(duckdb.connect())
prof = con.execute("""SELECT profession_libelle, count(DISTINCT personne) personnes, count(*) versements,
  round(sum(montant)/1e6, 1) meur, round(sum(montant)/count(DISTINCT personne)) eur_par_personne
  FROM prs GROUP BY 1 ORDER BY meur DESC, profession_libelle""").df()
prof.to_csv(RACINE/"out/professionnels_par_profession.csv", index=False); print(prof.head(12).to_string())

# Nom affiché = la forme la plus fréquente sous cette clé (un RPPS porte parfois une ligne au nom d'une autre
# personne, erreur du déclarant). Égalités départagées par ordre alphabétique.
top = con.execute("""WITH f0 AS (
  SELECT personne, upper(identite) nom, upper(prenom) prenom, dep, profession_libelle profession, count(*) n FROM prs GROUP BY 1, 2, 3, 4, 5),
f AS (SELECT * FROM f0 QUALIFY row_number() OVER (PARTITION BY personne ORDER BY n DESC, nom, prenom, dep, profession) = 1),
pl AS (SELECT personne, arg_max(raison_sociale, (s, raison_sociale)) principal_labo FROM
  (SELECT personne, raison_sociale, sum(montant) s FROM prs WHERE montant IS NOT NULL GROUP BY 1, 2) GROUP BY 1),
a AS (SELECT personne, min(rpps) rpps, round(sum(montant)) euros, count(*) versements,
  count(DISTINCT raison_sociale) labos, round(max(montant)) plus_grosse_ligne,
  round(coalesce(sum(montant) FILTER (WHERE lien_interet = 'convention'), 0)) dont_conventions_non_executees,
  count(DISTINCT nom_n) noms_declares, min(chiffres(beneficiaire_identifiant)) identifiant_declare
  FROM prs GROUP BY personne)
SELECT f.nom, f.prenom, f.profession, f.dep, a.rpps, a.euros, a.versements, a.labos, pl.principal_labo,
  a.* EXCLUDE (personne, rpps, euros, versements, labos) FROM a JOIN f USING (personne) LEFT JOIN pl USING (personne)
ORDER BY euros DESC, personne LIMIT 500""").df()
# Un identifiant à 9 chiffres est un SIREN : une société déclarée par erreur comme professionnel de santé.
top["alerte"] = (top.rpps.isna() & top.identifiant_declare.fillna("").str.fullmatch(r"\d{9}")).map(
    {True: "identifiant à 9 chiffres (SIREN) : sans doute une société déclarée comme personne", False: ""})
tot = con.execute("SELECT round(sum(montant)/1e9, 3), count(DISTINCT personne) FROM prs").fetchall()[0]
part = con.execute("""WITH p AS (SELECT personne, sum(montant) s FROM prs GROUP BY 1)
  SELECT round(100*sum(s) FILTER (WHERE s >= (SELECT quantile_cont(s, 0.99) FROM p))/sum(s), 1), median(s),
         count(*) FILTER (WHERE s >= 1e5), count(*) FILTER (WHERE s >= 1e6) FROM p""").fetchall()[0]
print(f"professionnels : {tot[0]} Md€ nets, {tot[1]:,} personnes ; 1 % des plus payés : {part[0]} % des euros ; "
      f"médiane {part[1]:.0f} € ; {part[2]:,} au-dessus de 100 k€ ; {part[3]} au-dessus de 1 M€")
top.to_csv(RACINE/"out/professionnels_top.csv", index=False); print(top.head(15).to_string())

# --- élus bénéficiaires
n = lambda x: " ".join(re.sub(r"[^A-Z ]", " ", unidecode.unidecode(str(x or "")).upper()).split())
dep = lambda x: None if pd.isna(x) or not str(x).strip() else ("0" + str(x).strip() if re.fullmatch(r"\d", str(x).strip()) else str(x).strip().upper())
h = pd.read_csv(RACINE/"data/ext/hatvp/liste_declarants.csv", sep=";", dtype=str)
h["dep"] = h.departement.map(dep)
h = h[h.dep.notna()]
h["k"] = h.nom.map(n) + "|" + h.prenom.map(lambda x: (n(x).split() or [""])[0]) + "|" + h.dep
h = h.sort_values(["k", "nom", "prenom"]).groupby("k").agg(nom=("nom", "first"), prenom=("prenom", "first"), departement=("dep", "first"),
    mandats=("qualite", lambda s: " ; ".join(sorted(set(s.dropna())))[:300])).reset_index()
con.register("h", h)
el = con.execute("""SELECT h.nom, h.prenom, h.departement, h.mandats, min(b.profession_libelle) profession, min(b.rpps) rpps,
  b.personne, round(sum(b.montant)) euros, count(*) versements, count(DISTINCT b.raison_sociale) labos,
  arg_max(b.raison_sociale, (b.montant, b.raison_sociale)) FILTER (WHERE b.montant IS NOT NULL) plus_gros_versement_de,
  min(year(b.date)) premiere_annee, max(year(b.date)) derniere_annee
FROM prs b JOIN h ON h.k = b.nom_n || '|' || b.prenom_n || '|' || b.dep
GROUP BY h.nom, h.prenom, h.departement, h.mandats, b.personne
ORDER BY euros DESC, h.nom, h.prenom, h.departement, b.personne""").df()
# plusieurs professionnels distincts derrière un même élu : au moins l'un d'eux est un homonyme
el["personnes_meme_nom"] = el.groupby(["nom", "prenom", "departement"]).nom.transform("size")
el.to_csv(RACINE/"out/elus_beneficiaires.csv", index=False)
ne = el[["nom", "prenom", "departement"]].drop_duplicates().shape[0]
print(f"\nresponsables publics HATVP retrouvés comme professionnels de santé bénéficiaires (nom + prénom + département) : "
      f"{ne} élus, {len(el)} professionnels, {el.euros.sum()/1e6:.2f} M€ ; "
      f"{el[el.personnes_meme_nom == 1][['nom','prenom','departement']].drop_duplicates().shape[0]} élus ne correspondent qu'à un seul professionnel")
print(el.head(20)[["nom", "prenom", "departement", "mandats", "profession", "euros", "versements", "labos", "personnes_meme_nom"]].assign(mandats=lambda d: d.mandats.str[:50]).to_string())
