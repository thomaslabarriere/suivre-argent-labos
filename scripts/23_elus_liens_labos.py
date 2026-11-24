"""Croisement 24/11 : déclarations d'intérêts des responsables publics (HATVP) qui citent un laboratoire ou une
entreprise de santé qui verse de l'argent dans Transparence Santé (actions détenues, emploi, conseil, direction,
conjoint...). Ce sont des déclarations faites par les intéressés eux-mêmes : un lien déclaré n'est pas une irrégularité.
Sortie : out/elus_liens_labos.csv"""
import re, unidecode, pandas as pd
import xml.etree.ElementTree as ET
from commun import RACINE
LABOS = {"SANOFI": r"SANOFI", "PFIZER": r"PFIZER", "NOVARTIS": r"NOVARTIS", "ASTRAZENECA": r"ASTRA ?ZENECA", "GSK": r"GLAXO|\bGSK\b",
 "MSD": r"MSD (FRANCE|VACCINS|CHIBRET)|MERCK SHARP", "MERCK": r"\bMERCK\b(?! SHARP)", "ROCHE": r"HOFFMANN.?LA.?ROCHE|ROCHE (SAS|PHARMA|DIAGNOSTICS|DIABETES|FRANCE)|LABORATOIRES? ROCHE|\bPRODUITS ROCHE",
 "JANSSEN / J&J": r"JANSSEN|JOHNSON (&|ET|AND) JOHNSON", "BRISTOL MYERS SQUIBB": r"BRISTOL.?MYERS|\bBMS\b", "BAYER": r"\bBAYER\b", "LILLY": r"\bLILLY\b",
 "ABBVIE": r"ABBVIE", "ABBOTT": r"\bABBOTT\b", "AMGEN": r"\bAMGEN\b", "GILEAD": r"\bGILEAD\b", "NOVO NORDISK": r"NOVO.?NORDISK", "BOEHRINGER": r"BOEHRINGER",
 "TAKEDA": r"\bTAKEDA\b", "ASTELLAS": r"\bASTELLAS\b", "IPSEN": r"\bIPSEN\b", "SERVIER": r"\bSERVIER\b", "PIERRE FABRE": r"PIERRE.?FABRE", "VIATRIS / MYLAN": r"VIATRIS|\bMYLAN\b",
 "BIOGARAN": r"BIOGARAN", "SANDOZ": r"\bSANDOZ\b", "TEVA": r"(^|\| )TEVA( SANTE| PHARMA| FRANCE)?( \||$)", "ZENTIVA": r"ZENTIVA", "BIOMERIEUX": r"BIO ?MERIEUX", "MEDTRONIC": r"MEDTRONIC",
 "BOSTON SCIENTIFIC": r"BOSTON SCIENTIFIC", "STRYKER": r"\bSTRYKER\b", "BIOGEN": r"\bBIOGEN\b", "VERTEX": r"VERTEX PHARMA", "LFB": r"\bLFB\b", "OCTAPHARMA": r"OCTAPHARMA",
 "BIOCODEX": r"BIOCODEX", "BESINS": r"\bBESINS\b", "GUERBET": r"GUERBET", "VALNEVA": r"VALNEVA", "LEEM (syndicat)": r"\bLEEM\b|LES ENTREPRISES DU MEDICAMENT",
 "UCB": r"\bUCB (PHARMA|FRANCE|SA)\b", "ALCON": r"\bALCON\b", "ESSILOR": r"ESSILOR", "DANONE NUTRICIA": r"NUTRICIA", "NESTLE HEALTH": r"NESTLE HEALTH"}
PAT = {k: re.compile(v) for k, v in LABOS.items()}
SECTIONS = {"participationFinanciereDto": "actions / parts détenues", "activConsultantDto": "activité de conseil", "activProfCinqDerniereDto": "emploi (5 dernières années)",
 "participationDirigeantDto": "direction d'un organisme", "fonctionBenevoleDto": "fonction bénévole", "activProfConjointDto": "emploi du conjoint",
 "activCollaborateursDto": "activité des collaborateurs", "mandatElectifDto": None, "observationInteretDto": "observation"}
norm = lambda t: re.sub(r"\s+", " ", unidecode.unidecode(t or "").upper())
rows, n = [], 0
for ev, el in ET.iterparse(RACINE/"data/ext/hatvp/declarations.xml", events=("end",)):
    if el.tag != "declaration": continue
    n += 1
    g = el.find("general"); d = g.find("declarant") if g is not None else None
    ident = {"nom": (d.findtext("nom") or "").strip() if d is not None else "", "prenom": (d.findtext("prenom") or "").strip() if d is not None else "",
             "qualite": (g.findtext("qualiteDeclarantForPDF") or "").strip() if g is not None else "",
             "type": (g.findtext("typeDeclaration/label") or "") if g is not None else "", "depot": (el.findtext("dateDepot") or "")[:10]}
    for tag, lib in SECTIONS.items():
        s = el.find(tag)
        if s is None or lib is None: continue
        for it in s.iter("items"):
            if it.find("motif") is None: continue
            champs = {c.tag: (c.text or "").strip() for c in it if len(c) == 0 and c.tag != "nom" and (c.text or "").strip() and "non publi" not in (c.text or "")}
            txt = norm(" | ".join(champs.values()))
            for labo, p in PAT.items():
                if p.search(txt):
                    rows.append({**ident, "labo": labo, "section": lib, "detail": " | ".join(f"{k}={v}" for k, v in champs.items())[:400]})
    el.clear()
df = pd.DataFrame(rows)
df["qualite_courte"] = df.qualite.str.split("/").str[:2].str.join(" / ")
df = df.sort_values("depot").drop_duplicates(["nom", "prenom", "labo", "section", "detail"], keep="last")
df.to_csv(RACINE/"out/elus_liens_labos.csv", index=False)
print(f"{n} déclarations lues ; {len(df)} mentions d'un labo ; {df[['nom','prenom']].drop_duplicates().shape[0]} responsables publics distincts")
print(df.groupby("section").size().sort_values(ascending=False).to_string())
print(df.groupby("labo")[["nom", "prenom"]].apply(lambda x: x.drop_duplicates().shape[0]).sort_values(ascending=False).head(12).to_string())
print(df.qualite.str.split("/").str[0].value_counts().head(8).to_string())
