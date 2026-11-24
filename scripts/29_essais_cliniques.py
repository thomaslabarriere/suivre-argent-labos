"""Piste 5 : essais cliniques industriels en France (ClinicalTrials.gov v2) vs conventions Transparence Santé.
Télécharge (une fois) data/ext/essais/ctgov_fr.json, puis écrit 3 CSV dans out/. Ne touche pas travail.duckdb."""
import json, re, time, urllib.request, urllib.parse
import duckdb, pandas as pd
from unidecode import unidecode
from commun import RACINE, vues_ts, groupe_labo

DOSSIER = RACINE / "data" / "ext" / "essais"; DOSSIER.mkdir(parents=True, exist_ok=True)
OUT = RACINE / "out"; OUT.mkdir(exist_ok=True)
CACHE = DOSSIER / "ctgov_fr.json"

def telecharger():
    if CACHE.exists(): return json.load(open(CACHE, encoding="utf-8"))
    base = "https://clinicaltrials.gov/api/v2/studies"
    p = {"query.locn": "France",
         "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY AND AREA[StartDate]RANGE[2019-01-01,MAX]",
         "pageSize": 500, "countTotal": "true",
         "fields": "NCTId|LeadSponsorName|Phase|Condition|LocationFacility|LocationCity|LocationCountry|StartDate|OverallStatus"}
    res, tok = [], None
    while True:
        q = dict(p); 
        if tok: q["pageToken"] = tok
        for essai in range(4):
            try:
                d = json.load(urllib.request.urlopen(base + "?" + urllib.parse.urlencode(q), timeout=120)); break
            except Exception as e: print("retry", e); time.sleep(3)
        else:
            raise SystemExit("ClinicalTrials.gov ne répond pas après 4 essais")
        for s in d["studies"]:
            pr = s["protocolSection"]
            locs = [l for l in pr.get("contactsLocationsModule", {}).get("locations", []) if l.get("country") == "France"]
            res.append({"nct": pr["identificationModule"]["nctId"],
                        "sponsor": pr["sponsorCollaboratorsModule"]["leadSponsor"]["name"],
                        "phases": pr.get("designModule", {}).get("phases", []),
                        "conditions": pr.get("conditionsModule", {}).get("conditions", []),
                        "debut": pr["statusModule"].get("startDateStruct", {}).get("date"),
                        "statut": pr["statusModule"].get("overallStatus"),
                        "sites": [{"facility": l.get("facility"), "city": l.get("city")} for l in locs]})
        tok = d.get("nextPageToken"); print(len(res), "/", d.get("totalCount"))
        if not tok: break
    json.dump(res, open(CACHE, "w"), ensure_ascii=False); return res

def groupe(nom):   # définition commune à tous les scripts (commun.groupe_labo)
    return groupe_labo(nom) or "?"
def ville_norm(v):
    v = re.sub(r"\bCEDEX\b.*|\bCEDEX\b|\d+", " ", unidecode(str(v or "")).upper().replace("-", " ").replace("'", " "))
    v = re.sub(r"\bSAINT\b", "ST", v); v = re.sub(r"\bSAINTE\b", "STE", v)
    return re.sub(r"\s+", " ", v).strip()
def facility_norm(f):
    f = re.sub(r"[^A-Z0-9 ]+", " ", unidecode(str(f or "")).upper())
    f = re.sub(r"\b(CENTRE HOSPITALIER UNIVERSITAIRE|UNIVERSITY HOSPITAL|HOPITAL UNIVERSITAIRE)\b", "CHU", f)
    f = re.sub(r"\b(CENTRE HOSPITALIER REGIONAL UNIVERSITAIRE|CHRU)\b", "CHU", f)
    f = re.sub(r"\b(CENTRE HOSPITALIER|HOPITAL|HOSPITAL|HOPITAUX|SERVICE|DEPARTMENT|DEPARTEMENT|DE|DU|DES|LA|LE|LES|ET|D|L)\b", " ", f)
    return re.sub(r"\s+", " ", f).strip()

essais = telecharger()
rows = []
for e in essais:
    g = groupe(e["sponsor"])
    for s in e["sites"]:
        rows.append({"nct": e["nct"], "sponsor": e["sponsor"], "groupe": g, "facility": s["facility"] or "",
                     "ville": ville_norm(s["city"]), "fac_norm": facility_norm(s["facility"])})
sites = pd.DataFrame(rows).drop_duplicates(["nct", "fac_norm", "ville"])
print(len(essais), "essais ;", len(sites), "couples essai x site")

# 1. par labo
lab = (pd.DataFrame([{"nct": e["nct"], "groupe": groupe(e["sponsor"]), "n_sites": len(e["sites"])} for e in essais])
       .groupby("groupe").agg(nb_essais_fr=("nct", "nunique"), nb_sites_fr=("n_sites", "sum")).reset_index())
nb_etab = sites.groupby("groupe").apply(lambda d: d[["fac_norm", "ville"]].drop_duplicates().shape[0]).rename("nb_etablissements_distincts")
lab = lab.merge(nb_etab, on="groupe")

# 2. par établissement
etab = (sites.groupby(["fac_norm", "ville"]).agg(nb_essais=("nct", "nunique"), nb_labos=("groupe", "nunique"),
        exemple_nom=("facility", "first"), top_labos=("groupe", lambda s: ", ".join(s.value_counts().head(5).index))).reset_index())
etab = etab[etab.fac_norm != ""].sort_values("nb_essais", ascending=False)
etab["bordeaux"] = etab.ville.str.startswith("BORDEAUX") | etab.fac_norm.str.contains("BERGONIE")
etab.to_csv(OUT / "essais_par_etablissement.csv", index=False)

# 3. Transparence Santé : conventions labo -> ETA
con = vues_ts(duckdb.connect())   # vue brute `ts` : on compte des conventions, pas des euros nets
ts = con.sql("""
 SELECT upper(strip_accents(raison_sociale)) AS rs,
        upper(strip_accents(coalesce(ville_sanscedex, ville))) AS ville, identite,
        concat_ws(' ', motif_lien_interet, autre_motif) AS motif, montant
 FROM ts WHERE lien_interet='convention' AND beneficiaire_categorie_code='ETA'""").df()
ts["groupe"] = ts.rs.map(groupe)
ts["ville"] = ts.ville.map(ville_norm)
ts["recherche"] = ts.motif.str.upper().map(lambda m: unidecode(str(m))).str.contains("RECHERCHE|ESSAI|ETUDE|CLINIQUE", regex=True)
print(len(ts), "conventions vers ETA")

conv_lab = ts.groupby("groupe").agg(conv_eta=("rs", "size"), conv_eta_recherche=("recherche", "sum"), montant_eta=("montant", "sum")).reset_index()
conv_lab["part_recherche"] = (conv_lab.conv_eta_recherche / conv_lab.conv_eta).round(3)
lab = lab.merge(conv_lab, on="groupe", how="left").sort_values("nb_essais_fr", ascending=False)
lab.to_csv(OUT / "essais_par_labo.csv", index=False)

# croisement labo x ville
ess_lv = sites.groupby(["groupe", "ville"]).agg(nb_essais=("nct", "nunique"), nb_etab_essais=("fac_norm", "nunique")).reset_index()
cv = ts.groupby(["groupe", "ville"]).agg(nb_conventions=("rs", "size"), nb_conv_recherche=("recherche", "sum"),
                                         nb_eta_conventionnes=("identite", "nunique")).reset_index()
x = ess_lv.merge(cv, on=["groupe", "ville"], how="outer").fillna(0)
for c in x.columns[2:]: x[c] = x[c].astype(int)
x["essais_et_conventions"] = (x.nb_essais > 0) & (x.nb_conventions > 0)
x["bordeaux"] = x.ville.str.startswith("BORDEAUX")
x = x.sort_values(["bordeaux", "nb_essais"], ascending=[False, False])
x.to_csv(OUT / "essais_vs_conventions.csv", index=False)

# bilan
a = x[x.nb_essais > 0]
print("paires labo x ville avec essais:", len(a), "dont avec conventions ETA:", int((a.nb_conventions > 0).sum()))
sans_motif = ts.motif.str.strip().eq("")
print("part conventions ETA recherche : en nombre", round(ts.recherche.mean(), 3), "; en euros",
      round(ts.loc[ts.recherche, "montant"].sum() / ts.montant.sum(), 3), "; sans motif renseigné", round(sans_motif.mean(), 3),
      "; parmi celles avec motif", round(ts.loc[~sans_motif, "recherche"].mean(), 3))
print("part essais-couples dans villes avec convention du meme labo:", round((a.nb_conventions > 0).mean(), 3))
print(lab.head(10).to_string()); print(etab.head(10)[["exemple_nom", "ville", "nb_essais", "nb_labos"]].to_string())
print(etab[etab.bordeaux].head(8)[["exemple_nom", "ville", "nb_essais", "nb_labos"]].to_string())
bx = x[x.bordeaux & (x.nb_essais > 0)].head(8); print(bx.to_string())
