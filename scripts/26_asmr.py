"""Piste 24/11 : la Sécu rembourse-t-elle surtout des médicaments qui apportent un progrès ?
ASMR (amélioration du service médical rendu, HAS) : I majeure ... IV mineure, V aucune. On prend le MEILLEUR avis jamais obtenu par le médicament (hypothèse la plus favorable aux labos).
Sortie : out/asmr_remboursements.csv, out/asmr_par_groupe.csv"""

from commun import RACINE, groupe_labo, lire_bdpm, lire_openmedic, montant_fr
a = lire_bdpm("CIS_HAS_ASMR_bdpm", {0: "cis", 3: "date", 4: "asmr"})
a["asmr"] = a.asmr.str.strip(); a = a[a.asmr.isin(["I", "II", "III", "IV", "V"])]
# meilleur avis obtenu par le médicament (une extension d'indication reçoit souvent V alors que l'indication initiale avait mieux)
a["rang"] = a.asmr.map({"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}); a = a.sort_values("rang").drop_duplicates("cis", keep="first")
cis = lire_bdpm("CIS_bdpm", {0: "cis", 1: "nom", 10: "titulaire"})
cip = lire_bdpm("CIS_CIP_bdpm", {0: "cis", 6: "cip13"}).drop_duplicates("cip13")
om = lire_openmedic(); om["rem"] = montant_fr(om.REM)
m = om.merge(cip, left_on="CIP13", right_on="cip13", how="left").merge(cis, on="cis", how="left").merge(a, on="cis", how="left")
assert len(m) == len(om), "jointure CIP13 -> CIS -> ASMR non unique"
# sans avis : génériques, médicaments anciens, ou présentations absentes de la BDPM actuelle (retirées)
m["asmr"] = m.asmr.where(m.asmr.notna(), m.cis.isna().map({True: "présentation absente de la BDPM", False: "sans avis ASMR (ancien ou générique)"}))
r = m.groupby("asmr").agg(rembourse=("rem", "sum"), medicaments=("cis", "nunique")).sort_values("rembourse", ascending=False)
r["pct"] = (100 * r.rembourse / r.rembourse.sum()).round(1); r.to_csv(RACINE/"out/asmr_remboursements.csv")
print(r.assign(rembourse=lambda d: (d.rembourse/1e9).round(2)).to_string())
m["g"] = m.titulaire.map(groupe_labo)
p = m.pivot_table(index="g", columns="asmr", values="rem", aggfunc="sum").fillna(0)
p["total"] = p.sum(axis=1); p["pct_asmr_V"] = (100 * p.get("V", 0) / p.total).round(1); p["pct_asmr_I_II_III"] = (100 * p[[c for c in ["I", "II", "III"] if c in p]].sum(axis=1) / p.total).round(1)
p = p.sort_values("total", ascending=False); p.to_csv(RACINE/"out/asmr_par_groupe.csv")
print(p.head(20)[["total", "pct_asmr_I_II_III", "pct_asmr_V"]].assign(total=lambda d: (d.total/1e6).round(0)).to_string())
top = m[m.asmr == "V"].groupby(["nom", "titulaire"]).rem.sum().sort_values(ascending=False).head(10)
print("\nMédicaments sans progrès (ASMR V) les plus remboursés :"); print((top/1e6).round(1).to_string())
