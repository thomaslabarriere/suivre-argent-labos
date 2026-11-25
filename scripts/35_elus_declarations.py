"""Élus payés par un labo : le labo figure-t-il dans leur déclaration d'intérêts (HATVP) ?

Part de out/elus_beneficiaires.csv (script 24 : responsables publics qui portent le nom, le prénom et le département
d'un professionnel de santé payé). Pour chacun, cherche ses déclarations d'intérêts publiées en open data par la
HATVP (data/ext/hatvp/declarations.xml), puis, pour chaque groupe de labos qui l'a payé, si ce groupe est cité
n'importe où dans ces déclarations.

Ce que la déclaration doit contenir : les activités professionnelles rémunérées et les activités de conseil des cinq
années précédant le dépôt. Sont donc comparées les rémunérations et conventions (contrats d'expert, d'orateur...)
datées des cinq ans avant la dernière déclaration. Les avantages (repas, hébergement, transport) ne sont pas à
déclarer : ils sont donnés à titre indicatif.

Précautions, à rappeler à chaque usage :
- homonymes possibles : l'élu et le soignant ne sont rapprochés que par nom, prénom et département ;
- « non cité » ne veut pas dire « non déclaré à tort » : le soignant peut avoir déclaré son activité sans nommer
  chaque labo (colonnes activite_sante_declaree, mention_generique ; le nom de l'employeur est parfois masqué par la
  HATVP), et seules les déclarations publiées en open data sont lues ;
- un nom de labo court (ROCHE, BAYER) peut être trouvé dans un autre contexte : « cité » est donc généreux.
Sortie : out/elus_declarations_vs_versements.csv (une ligne par élu × groupe de labos)."""
import re, datetime, unidecode, duckdb, pandas as pd
import xml.etree.ElementTree as ET
from commun import RACINE, vues_ts, groupe_labo, cle_labo

n = lambda x: re.sub(r"[^A-Z ]", " ", unidecode.unidecode(str(x or "")).upper()).split()
cle = lambda nom, prenom: " ".join(n(nom)) + "|" + (n(prenom) or [""])[0]
# Autres noms sous lesquels un groupe apparaît dans un texte libre.
ALIAS_TEXTE = {"JOHNSON": r"JOHNSON|JANSSEN|DEPUY|ETHICON", "MSD": r"MSD|MERCK SHARP", "GLAXOSMITHKLINE": r"GLAXO|GSK",
               "BRISTOL": r"BRISTOL|BMS", "LILLY": r"LILLY", "VIATRIS": r"VIATRIS|MYLAN", "SANOFI": r"SANOFI|AVENTIS|GENZYME"}
SANTE = re.compile(r"PHARMACI|MEDECIN|CHIRURG|PRATICIEN|INFIRMI|KINESI|DENTIST|SAGE.FEMME|HOPITAL|HOSPITAL|CLINIQUE|CABINET MEDICAL")
GENERIQUE = re.compile(r"LABORATOIRE|PHARMA|INDUSTRI|CONFERENC|ORATEUR|EXPERTISE|CONSULT|FORMATION MEDICALE|ESSAI")

# --- déclarations d'intérêts (DI, DIA) publiées
decl = []
for _, el in ET.iterparse(RACINE / "data/ext/hatvp/declarations.xml", events=("end",)):
    if el.tag != "declaration":
        continue
    if (el.findtext("general/typeDeclaration/id") or "") in ("DI", "DIA"):
        q = el.findtext("general/qualiteDeclarantForPDF") or ""
        dep = re.search(r"\((\d[\dAB]|97\d)\)", q + " " + (el.findtext("general/organe/labelOrgane") or ""))
        texte = " ".join((x.text or "") for s in el if s.tag != "general" for x in s.iter() if "non publi" not in (x.text or ""))
        consult = el.find("activConsultantDto")
        prof = el.find("activProfCinqDerniereDto")
        prof = unidecode.unidecode(" ".join((x.text or "") for x in prof.iter())).upper() if prof is not None else ""
        decl.append({"k": cle(el.findtext("general/declarant/nom"), el.findtext("general/declarant/prenom")),
                     "dep_decl": dep.group(1) if dep else None, "depot": pd.to_datetime((el.findtext("dateDepot") or "")[:10], dayfirst=True, errors="coerce"),
                     "qualite_decl": q, "texte": re.sub(r"\s+", " ", unidecode.unidecode(texte).upper()),
                     "activite_sante": bool(SANTE.search(prof)),
                     "conseil_neant": consult is not None and (consult.findtext("neant") or "") == "true"})
    el.clear()
D = pd.DataFrame(decl)

# --- élus bénéficiaires et leurs versements, ligne à ligne
E = pd.read_csv(RACINE / "out/elus_beneficiaires.csv", dtype={"departement": str, "rpps": str})
E["dep"] = E.departement.str.split(".").str[0].str.zfill(2)
E["k"] = [cle(a, b) for a, b in zip(E.nom, E.prenom)]
E["kd"] = E.k + "|" + E.dep
con = vues_ts(duckdb.connect())
con.register("e", E[["kd", "rpps"]].drop_duplicates())
con.execute("CREATE MACRO nn(x) AS regexp_replace(trim(regexp_replace(upper(strip_accents(coalesce(x,''))), '[^A-Z ]', ' ', 'g')), ' +', ' ', 'g')")
V = con.execute("""SELECT e.kd, e.rpps, t.raison_sociale, t.lien_interet, t.montant, cast(coalesce(t.date, t.date_debut) AS DATE) d
  FROM ts_net t JOIN e ON nn(t.identite) || '|' || split_part(nn(t.prenom), ' ', 1) || '|' || lpad(coalesce(t.dep_code,''),2,'0') = e.kd
  WHERE t.beneficiaire_categorie_code = 'PRS'
    AND (t.beneficiaire_identifiant = e.rpps OR (e.rpps IS NULL AND t.beneficiaire_identifiant IS NULL))""").df()
V["groupe"] = V.raison_sociale.map(groupe_labo)
V["d"] = pd.to_datetime(V.d)

lignes = []
for _, el in E.iterrows():
    dd = D[(D.k == el.k) & (D.dep_decl.isna() | (D.dep_decl == el.dep))]
    v = V[(V.kd == el.kd) & ((V.rpps == el.rpps) if pd.notna(el.rpps) else V.rpps.isna())]
    texte = " ".join(dd.texte)
    fin = dd.depot.max() if len(dd) else pd.NaT
    for g, vg in v.groupby("groupe"):
        motif = ALIAS_TEXTE.get(g, re.escape(g))
        autres = {cle_labo(r).split()[0] for r in vg.raison_sociale if cle_labo(r)}
        cite = bool(texte) and (re.search(rf"\b({motif})\b", texte) is not None
                                or any(re.search(rf"\b{re.escape(a)}\b", texte) for a in autres if len(a) >= 4))
        contrats = vg[vg.lien_interet.isin(["remuneration", "convention"])]
        fen = contrats[(contrats.d <= fin) & (contrats.d > fin - pd.DateOffset(years=5))] if pd.notna(fin) else contrats.iloc[0:0]
        lignes.append({"nom": el.nom, "prenom": el.prenom, "departement": el.dep, "mandats": el.mandats, "rpps": el.rpps,
                       "personnes_meme_nom": el.personnes_meme_nom, "groupe_labo": g,
                       "labos_declarants": " ; ".join(sorted(set(vg.raison_sociale)))[:200],
                       "declarations_publiees": len(dd), "derniere_declaration": fin.date() if pd.notna(fin) else None,
                       "conseil_declare_neant": bool(dd.sort_values("depot").conseil_neant.iloc[-1]) if len(dd) else None,
                       "contrats_5_ans_avant_declaration": round(fen.montant.sum()), "nb_contrats_5_ans": len(fen),
                       "contrats_apres_declaration": round(contrats[contrats.d > fin].montant.sum()) if pd.notna(fin) else None,
                       "contrats_total": round(contrats.montant.sum()), "avantages_total": round(vg[vg.lien_interet == "avantage"].montant.sum()),
                       "labo_cite_dans_declaration": cite if len(dd) else None,
                       "activite_sante_declaree": bool(dd.activite_sante.any()) if len(dd) else None,
                       "mention_generique": bool(GENERIQUE.search(texte)) if len(dd) else None})
R = pd.DataFrame(lignes).sort_values(["contrats_5_ans_avant_declaration", "contrats_total", "nom", "groupe_labo"], ascending=[False, False, True, True])
R.to_csv(RACINE / "out/elus_declarations_vs_versements.csv", index=False)

el = R.groupby(["nom", "prenom", "departement", "rpps"], dropna=False)
print(f"{len(D):,} déclarations d'intérêts publiées lues ; {E[['nom','prenom','dep']].drop_duplicates().shape[0]} élus "
      f"bénéficiaires, dont {R[R.declarations_publiees > 0][['nom','prenom','departement']].drop_duplicates().shape[0]} avec au moins une déclaration publiée")
x = R[(R.declarations_publiees > 0) & (R.contrats_5_ans_avant_declaration > 0)]
print(f"élus avec déclaration ET contrats d'un labo dans les 5 ans avant : {x[['nom','prenom','departement']].drop_duplicates().shape[0]} "
      f"({len(x)} paires élu × labo, {x.contrats_5_ans_avant_declaration.sum():,.0f} €)")
y = x[~x.labo_cite_dans_declaration.astype(bool)]
print(f"  dont labo NON cité dans la déclaration : {len(y)} paires, {y[['nom','prenom','departement']].drop_duplicates().shape[0]} élus, "
      f"{y.contrats_5_ans_avant_declaration.sum():,.0f} €")
print(y.head(15)[["nom", "prenom", "departement", "mandats", "groupe_labo", "contrats_5_ans_avant_declaration", "nb_contrats_5_ans",
                  "derniere_declaration", "conseil_declare_neant", "activite_sante_declaree", "personnes_meme_nom"]]
      .assign(mandats=lambda d: d.mandats.str[:35]).to_string())
