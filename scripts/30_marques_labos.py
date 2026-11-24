"""Qui est qui : chaque marque de médicament -> labo titulaire -> groupe -> ce que ce groupe verse (Transparence Santé complète),
son lobbying (HATVP) et ce que la Sécu rembourse pour la marque (Open Medic 2025). Sorties : out/marques_labos.csv, out/groupes_fiche.csv
Montants versés : vue nette (sans double compte convention / rémunération). Pré-requis : 22 (lobbying_groupes.csv)."""
import pandas as pd, duckdb
from commun import RACINE, vues_ts, groupe_labo as groupe, lire_bdpm, lire_openmedic, montant_fr
rd = lambda f, cols, names: lire_bdpm(f.removesuffix(".txt"), dict(zip(cols, names)))
cis = rd("CIS_bdpm.txt", [0, 1, 2, 3, 6, 10], ["cis", "denomination", "forme", "voie", "commercialise", "titulaire"])
cis["titulaire"] = cis.titulaire.str.strip()
# marque = début du nom avant le premier chiffre ou la première virgule (ELIQUIS 5 mg, comprimé -> ELIQUIS)
cis["marque"] = cis.denomination.str.upper().str.extract(r"^([^,0-9]+?)(?:\s+\d|,|$)")[0].str.strip()
comp = rd("CIS_COMPO_bdpm.txt", [0, 3], ["cis", "substance"]).groupby("cis").substance.apply(lambda s: " + ".join(sorted(set(s.str.strip().str.lower())))[:120]).reset_index()
cip = rd("CIS_CIP_bdpm.txt", [0, 6], ["cis", "cip13"])
a = rd("CIS_HAS_ASMR_bdpm.txt", [0, 4], ["cis", "asmr"]); a["asmr"] = a.asmr.str.strip()
a = a[a.asmr.isin(["I", "II", "III", "IV", "V"])].assign(r=lambda d: d.asmr.map({"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5})).sort_values("r").drop_duplicates("cis")
gen = rd("CIS_GENER_bdpm.txt", [2, 3], ["cis", "type_gen"]).drop_duplicates("cis")
om = lire_openmedic(); om["rem"] = montant_fr(om.REM)
rem = om.merge(cip, left_on="CIP13", right_on="cip13").groupby("cis").rem.sum().reset_index()
m = cis.merge(comp, on="cis", how="left").merge(a[["cis", "asmr"]], on="cis", how="left").merge(rem, on="cis", how="left").merge(gen, on="cis", how="left")
m["groupe"] = m.titulaire.map(groupe)
M = m.groupby(["marque", "groupe"]).agg(titulaire=("titulaire", "first"), substance=("substance", "first"), presentations=("cis", "nunique"),
      generique=("type_gen", lambda s: "générique" if (s == "1").any() else ""), meilleur_asmr=("asmr", lambda s: min(s.dropna(), key=lambda x: ["I", "II", "III", "IV", "V"].index(x)) if s.notna().any() else ""),
      rembourse_2025=("rem", "sum"), commercialise=("commercialise", lambda s: "oui" if (s == "Commercialisée").any() else "non")).reset_index()
# ce que verse chaque groupe (2012-2026 et 2025, tous bénéficiaires, vue nette)
con = vues_ts(duckdb.connect())
ent = con.execute("SELECT DISTINCT raison_sociale FROM ts_net").df()
ent["groupe"] = ent.raison_sociale.map(groupe); con.register("ent", ent)
G = con.execute("""SELECT e.groupe, string_agg(DISTINCT e.raison_sociale, ' / ') entites_declarantes, sum(montant) verse_total,
   sum(montant) FILTER (WHERE beneficiaire_categorie_code='PRS') verse_pro, sum(montant) FILTER (WHERE year(date)=2025) verse_2025,
   count(DISTINCT beneficiaire_identifiant) FILTER (WHERE beneficiaire_categorie_code='PRS') professionnels_payes   -- distincts au niveau du groupe
   FROM ts_net t JOIN ent e USING (raison_sociale) GROUP BY 1""").df().set_index("groupe")
G["entites_declarantes"] = G.entites_declarantes.str[:300]
L = pd.read_csv(RACINE/"out/lobbying_groupes.csv").set_index("g")[["lobbying_2022_2025", "fiches"]]
R = M.groupby("groupe").agg(rembourse_2025_groupe=("rembourse_2025", "sum"), marques=("marque", "nunique"))
G = G.join(L, how="left").join(R, how="outer")
G.to_csv(RACINE/"out/groupes_fiche.csv")
M = M.merge(G[["verse_total", "verse_2025", "lobbying_2022_2025"]].rename(columns={"verse_total": "verse_groupe_2012_2026", "verse_2025": "verse_groupe_2025"}), left_on="groupe", right_index=True, how="left").sort_values("rembourse_2025", ascending=False)
M.to_csv(RACINE/"out/marques_labos.csv", index=False)
print(f"{M.marque.nunique()} marques, {M.groupe.nunique()} groupes titulaires ; marques avec remboursements 2025 : {(M.rembourse_2025 > 0).sum()}")
T_ = G[G.rembourse_2025_groupe.notna()]; print(f"groupes titulaires retrouvés comme payeurs dans Transparence Santé : {T_.verse_total.notna().sum()} sur {len(T_)}")
pd.set_option("display.width", 250)
print(M.head(20)[["marque", "groupe", "substance", "meilleur_asmr", "rembourse_2025", "verse_groupe_2025"]].assign(rembourse_2025=lambda d: (d.rembourse_2025/1e6).round(0), verse_groupe_2025=lambda d: (d.verse_groupe_2025/1e6).round(1), substance=lambda d: d.substance.str[:30]).to_string(index=False))
