"""Croisement 24/11 (base Transparence Santé complète) :
1. l'argent versé aux professionnels de santé eux-mêmes (par profession, par labo, les plus gros bénéficiaires) ;
   Montants : vue nette `ts_net` (sans double compte convention / rémunération, voir commun.vues_ts).
   Une personne = son numéro RPPS/ADELI quand il est déclaré, sinon nom + prénom + département (homonymes possibles).
2. les responsables publics (liste HATVP) qui apparaissent comme professionnels de santé bénéficiaires,
   avec le même nom, le même prénom et le même département. Homonymes possibles : à vérifier fiche par fiche.
Sorties : out/professionnels_par_profession.csv, out/professionnels_top.csv, out/elus_beneficiaires.csv"""
import re, unidecode, pandas as pd, duckdb
from commun import RACINE, vues_ts
con = vues_ts(duckdb.connect())
PERS = "coalesce(beneficiaire_identifiant, identite || '|' || coalesce(prenom,'') || '|' || coalesce(dep_code,''))"
con.execute(f"CREATE VIEW t AS SELECT *, {PERS} AS personne FROM ts_net")
print(con.execute("SELECT beneficiaire_categorie_code, beneficiaire_categorie, count(*) n, round(sum(montant)/1e9,2) md FROM t GROUP BY 1,2 ORDER BY md DESC").df().to_string())
PRS = "beneficiaire_categorie_code='PRS'"
print(con.execute(f"SELECT lien_interet, count(*) n, round(sum(montant)/1e6) meur FROM t WHERE {PRS} GROUP BY 1 ORDER BY meur DESC").df().to_string())
prof = con.execute(f"""SELECT profession_libelle, count(DISTINCT personne) personnes, count(*) versements,
  round(sum(montant)/1e6,1) meur, round(sum(montant)/count(DISTINCT personne)) eur_par_personne
  FROM t WHERE {PRS} GROUP BY 1 ORDER BY meur DESC""").df()
prof.to_csv(RACINE/"out/professionnels_par_profession.csv", index=False); print(prof.head(12).to_string())
top = con.execute(f"""SELECT any_value(identite) nom, any_value(prenom) prenom, any_value(profession_libelle) profession, any_value(dep_code) dep,
  any_value(beneficiaire_identifiant) rpps, round(sum(montant)) euros, count(*) versements, count(DISTINCT raison_sociale) labos,
  arg_max(raison_sociale, montant) principal_labo
  FROM t WHERE {PRS} GROUP BY personne ORDER BY euros DESC LIMIT 500""").df()
tot = con.execute(f"SELECT round(sum(montant)/1e9,3), count(DISTINCT personne) FROM t WHERE {PRS}").fetchall()[0]
print(f"professionnels : {tot[0]} Md€ nets, {tot[1]:,} personnes ; 1 % des plus payés : "
      + str(con.execute(f"""WITH p AS (SELECT personne, sum(montant) s FROM t WHERE {PRS} GROUP BY 1)
          SELECT round(100*sum(s) FILTER (WHERE s >= (SELECT quantile_cont(s, 0.99) FROM p))/sum(s),1) FROM p""").fetchall()[0][0]) + " % des euros")
top.to_csv(RACINE/"out/professionnels_top.csv", index=False); print(top.head(15).to_string())
# --- élus bénéficiaires
n = lambda x: re.sub(r"[^A-Z ]", " ", unidecode.unidecode(str(x or "")).upper()).split()
h = pd.read_csv(RACINE/"data/ext/hatvp/liste_declarants.csv", sep=";", dtype=str)
h["k"] = h.nom.map(lambda x: " ".join(n(x))) + "|" + h.prenom.map(lambda x: (n(x) or [""])[0]) + "|" + h.departement.fillna("").str.zfill(2)
h = h.groupby("k").agg(nom=("nom", "first"), prenom=("prenom", "first"), departement=("departement", "first"), mandats=("qualite", lambda s: " ; ".join(sorted(set(s.dropna())))[:300])).reset_index()
con.register("h", h)
con.execute("CREATE OR REPLACE MACRO nn(x) AS trim(regexp_replace(upper(strip_accents(coalesce(x,''))), '[^A-Z ]', ' ', 'g'))")
el = con.execute(f"""WITH b AS (
  SELECT regexp_replace(nn(identite), ' +', ' ', 'g') || '|' || split_part(regexp_replace(nn(prenom), ' +', ' ', 'g'), ' ', 1) || '|' || lpad(coalesce(dep_code,''),2,'0') k,
         identite, prenom, profession_libelle, beneficiaire_identifiant, personne, raison_sociale, montant, lien_interet, year(date) an
  FROM t WHERE {PRS})
SELECT h.nom, h.prenom, h.departement, h.mandats, any_value(b.profession_libelle) profession, any_value(b.beneficiaire_identifiant) rpps,
  round(sum(b.montant)) euros, count(*) versements, count(DISTINCT b.raison_sociale) labos, arg_max(b.raison_sociale, b.montant) principal_labo,
  min(an) premiere_annee, max(an) derniere_annee
FROM b JOIN h USING (k) GROUP BY h.nom, h.prenom, h.departement, h.mandats, b.personne ORDER BY euros DESC""").df()
# plusieurs personnes (RPPS différents) derrière un même élu = homonymie certaine pour au moins l'une d'elles
el["personnes_meme_nom"] = el.groupby(["nom", "prenom", "departement"]).nom.transform("size")
el.to_csv(RACINE/"out/elus_beneficiaires.csv", index=False)
print(f"\nresponsables publics HATVP retrouvés comme professionnels de santé bénéficiaires (nom + prénom + département) : {len(el)} ; {el.euros.sum()/1e6:.2f} M€")
print(el.head(20)[["nom", "prenom", "departement", "mandats", "profession", "euros", "versements", "labos", "principal_labo"]].assign(mandats=lambda d: d.mandats.str[:50]).to_string())
