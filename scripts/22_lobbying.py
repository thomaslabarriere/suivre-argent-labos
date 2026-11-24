"""Croisement 24/11 : lobbying déclaré à la HATVP (répertoire des représentants d'intérêts) par les entreprises
qui versent de l'argent aux structures de santé (Transparence Santé). Les dépenses sont déclarées par tranche :
on retient le milieu de la tranche (« < 10 000 » -> 5 000 ; « >= 10 000 000 » -> 10 000 000, borne basse).
L'année d'un exercice est celle de sa date de fin (un exercice juillet 2024 - juin 2025 compte pour 2025).
Pré-requis : 21 (lit out/groupes_remboursements_vs_versements.csv).
Sorties : out/lobbying_groupes.csv, out/lobbying_actions_sante.csv"""
import json, re, pandas as pd, duckdb
from commun import RACINE, vues_ts, groupe_labo
P = json.load(open(RACINE/"data/ext/hatvp/repertoire_lobbies.json"))["publications"]
def tranche(s):
    if not s: return None
    n = [float(x.replace(" ", "")) for x in re.findall(r"\d[\d ]*", s)]
    if not n: return None
    if len(n) >= 2: return (n[0] + n[1]) / 2
    return n[0] / 2 if "<" in s and ">" not in s else n[0]
org, act = [], []
for o in P:
    for e in o.get("exercices") or []:
        c = e.get("publicationCourante") or {}
        an = (c.get("dateFin") or c.get("dateDebut") or "")[-4:]
        acts = c.get("activites") or []
        org.append({"categorie": (o.get("categorieOrganisation") or {}).get("categorie"), "denomination": o["denomination"], "siren": o.get("identifiantNational"), "annee": an,
                    "depense": tranche(c.get("montantDepense")), "tranche": c.get("montantDepense"), "salaries": c.get("nombreSalaries"), "fiches": len(acts)})
        for a in acts:
            a = a.get("publicationCourante") or {}
            cibles = sorted({r for x in a.get("actionsRepresentationInteret") or [] for r in x.get("reponsablesPublics") or []})
            act.append({"denomination": o["denomination"], "siren": o.get("identifiantNational"), "annee": an, "objet": a.get("objet"),
                        "domaines": " ; ".join(a.get("domainesIntervention") or []), "cibles": " ; ".join(cibles)})
org, act = pd.DataFrame(org), pd.DataFrame(act)
print(f"HATVP : {org.denomination.nunique()} organisations, {len(act)} fiches d'activité")
# entreprises de Transparence Santé (toutes, y compris celles qui ne versent qu'aux professionnels quand la base complète sera là)
con = vues_ts(duckdb.connect())
ts = con.execute("""SELECT raison_sociale, any_value(numero_siren) siren, sum(montant) FILTER (WHERE year(date)=2025) verse25,
                            sum(montant) verse_total FROM ts_net GROUP BY 1""").df()
groupe = groupe_labo
ts["g"] = ts.raison_sociale.map(groupe); org["g"] = org.denomination.map(groupe); act["g"] = act.denomination.map(groupe)
# Appariement d'une organisation HATVP à un déclarant Transparence Santé :
#  - son SIREN est celui d'un déclarant (l'entité elle-même verse de l'argent aux acteurs de santé), ou
#  - son groupe (premier mot du nom) est celui d'un labo dont des médicaments sont remboursés (Open Medic, via 21).
# Le second critère seul ramenait des homonymes hors santé (Thales, Samsung, Nestlé) : il est réservé aux labos.
rem = pd.read_csv(RACINE/"out/groupes_remboursements_vs_versements.csv").set_index("g")[["rembourse", "medicaments"]]
pharma = set(rem.index[rem.rembourse > 0]) & set(ts.g.dropna())
# Un groupe générique (« SOCIETE », « ASSOCIATION »…) n'est pas un groupe : on garde alors le nom de l'entité.
GENERIQUE = {"ASSOCIATION","SOCIETE","CENTRE","FONDATION","GROUPEMENT","INSTITUT","ALLIANCE","FEDERATION","SYNDICAT","UNION",
             "COMPAGNIE","CONSEIL","CLUB","COLLECTIF","COMITE","CHAMBRE","NATIONAL","NATIONALE","FRENCH","EUROPEAN","GENERAL",
             "GENERALE","OFFICE","AGENCE","MUTUELLE","CAISSE","BANQUE","ORDRE","ACADEMIE","CONFEDERATION","ASS"}
for d in (org, act):
    d.loc[d.g.isin(GENERIQUE) | (d.g.str.len() < 3), "g"] = d.denomination
org["labo"] = (org.categorie == "ENTREPRISE") & (org.siren.isin(set(ts.siren.dropna())) | org.g.isin(pharma))
act = act.merge(org.groupby("denomination", as_index=False).labo.any(), on="denomination")   # une ligne par dénomination
L = org[org.labo & org.annee.isin(["2022", "2023", "2024", "2025"])]
G = L.groupby("g").agg(entites_hatvp=("denomination", lambda s: " / ".join(sorted(set(s))[:3])), lobbying_2022_2025=("depense", "sum"),
                       fiches=("fiches", "sum"), salaries_max=("salaries", "max"))
G = G.join(ts.groupby("g").agg(verse_2025=("verse25", "sum"), verse_total_2012_2026=("verse_total", "sum")), how="left")
G = G.join(rem, how="left").sort_values("lobbying_2022_2025", ascending=False)
G.to_csv(RACINE/"out/lobbying_groupes.csv")
S = act[act.labo & act.domaines.str.contains("Santé|Médicament|médic|Sécurité sociale|Recherche", case=False, na=False)]
S.to_csv(RACINE/"out/lobbying_actions_sante.csv", index=False)
print(f"entreprises de Transparence Santé présentes au registre des lobbies : {L.g.nunique()} groupes")
print(f"dépense de lobbying déclarée 2022-2025 (milieu de tranche) : {G.lobbying_2022_2025.sum()/1e6:.1f} M€ ; fiches d'activité santé : {len(S)}")
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 45)
print(G.head(20).assign(lobbying_2022_2025=lambda d: (d.lobbying_2022_2025/1e6).round(2), verse_2025=lambda d: (d.verse_2025/1e6).round(1),
      rembourse=lambda d: (d.rembourse/1e6).round(0))[["entites_hatvp", "lobbying_2022_2025", "fiches", "verse_2025", "rembourse"]].to_string())
print("\nCibles les plus visées par les labos (fiches santé) :")
print(S.cibles.str.split(" ; ").explode().value_counts().head(8).to_string())
