"""Remboursements de l'Assurance maladie face aux versements des labos.

Pour chaque labo : ce que l'Assurance maladie rembourse pour ses médicaments en 2025 (Open Medic, CIP13), le labo
titulaire étant lu dans la base publique des médicaments (BDPM : CIP13 -> CIS -> titulaire), face à ce que le même
labo a versé en 2025 (Transparence Santé, vue nette sans double compte) aux structures et aux professionnels.

Limite : le versement couvre toutes les activités du labo (médicament, mais aussi dispositifs, diagnostic,
dermo-cosmétique) alors que le remboursement ne couvre que le médicament de ville et rétrocédé. Le ratio
« € versés pour 1 000 € remboursés » est donc un ordre de grandeur, pas une mesure d'influence.

Sorties : out/labos_remboursements_vs_versements.csv (par entité titulaire), out/groupes_remboursements_vs_versements.csv
"""
import duckdb, pandas as pd
from rapidfuzz import process, fuzz
from commun import RACINE, vues_ts, cle_labo, groupe_labo, lire_bdpm, lire_openmedic, montant_fr

cis = lire_bdpm("CIS_bdpm", {0: "cis", 1: "denomination", 10: "titulaire"})
cis["titulaire"] = cis.titulaire.str.split(";").str[0].str.strip()
cip = lire_bdpm("CIS_CIP_bdpm", {0: "cis", 6: "cip13"}).drop_duplicates("cip13")
om = lire_openmedic()
om["rem"] = montant_fr(om.REM)
m = om.merge(cip, left_on="CIP13", right_on="cip13", how="left").merge(cis, on="cis", how="left")
assert len(m) == len(om), "un CIP13 a plusieurs CIS : la jointure dupliquerait des remboursements"
print(f"Open Medic 2025 : {len(om)} présentations, {om.rem.sum()/1e9:.1f} Md€ remboursés ; titulaire trouvé pour "
      f"{m.loc[m.titulaire.notna(),'rem'].sum()/om.rem.sum():.0%} des euros")
m["k"] = m.titulaire.map(cle_labo); m["g"] = m.titulaire.map(groupe_labo)

con = vues_ts(duckdb.connect())
ts = con.execute("""SELECT raison_sociale, sum(montant) verse,
    sum(montant) FILTER (WHERE beneficiaire_categorie_code <> 'PRS') verse_structures, count(*) n
  FROM ts_net WHERE year(date) = 2025 GROUP BY 1""").df()
ts["k"] = ts.raison_sociale.map(cle_labo); ts["g"] = ts.raison_sociale.map(groupe_labo)

# --- Par entité titulaire : appariement du nom BDPM au nom déclarant de Transparence Santé.
# Score = moyenne token_set / token_sort (token_set seul donne 100 dès qu'un nom est inclus dans l'autre),
# et même premier mot exigé.
tsk = ts.groupby("k").agg(labo_ts=("raison_sociale", lambda s: " / ".join(s.head(3))), verse_2025=("verse", "sum"),
                          verse_structures_2025=("verse_structures", "sum"), versements=("n", "sum")).reset_index()
tsk = tsk[tsk.k.str.len() >= 3]
score = lambda a, b, **_: (fuzz.token_set_ratio(a, b) + fuzz.token_sort_ratio(a, b)) / 2
def apparier(k):
    if not isinstance(k, str) or len(k) < 3:
        return None
    pool = [c for c in tsk.k if c.split()[0] == k.split()[0]]
    r = process.extractOne(k, pool, scorer=score, score_cutoff=92) if pool else None
    return r[0] if r else None
rem = m[m.titulaire.notna()].groupby("k").agg(titulaire=("titulaire", "first"), rembourse=("rem", "sum"),
                                              medicaments=("cis", "nunique")).reset_index()
rem["k_ts"] = rem.k.map(apparier)
out = (rem.merge(tsk.rename(columns={"k": "k_ts"}), on="k_ts", how="left")
          .groupby(lambda i: rem.k_ts.fillna(rem.k)[i])
          .agg(titulaire=("titulaire", "first"), labo_ts=("labo_ts", "first"), rembourse=("rembourse", "sum"),
               medicaments=("medicaments", "sum"), verse_2025=("verse_2025", "first"),
               verse_structures_2025=("verse_structures_2025", "first"), versements=("versements", "first")))
out["euros_verses_pour_1000_rembourses"] = (1000 * out.verse_2025 / out.rembourse).round(1)
out = out.sort_values("rembourse", ascending=False)
out.to_csv(RACINE / "out/labos_remboursements_vs_versements.csv", index=False)
v = out[out.verse_2025.notna()]
print(f"titulaires appariés à Transparence Santé : {len(v)} ; {v.rembourse.sum()/out.rembourse.sum():.0%} des remboursements")

# --- Par groupe (un labo déclare sous plusieurs filiales) : définition commune dans commun.groupe_labo.
G = (m.groupby("g").agg(rembourse=("rem", "sum"), medicaments=("cis", "nunique"), exemple_titulaire=("titulaire", "first"))
      .join(ts.groupby("g").agg(verse_2025=("verse", "sum"), verse_structures_2025=("verse_structures", "sum"),
                                versements=("n", "sum"), exemple_ts=("raison_sociale", "first")), how="left"))
G["euros_verses_pour_1000_rembourses"] = (1000 * G.verse_2025 / G.rembourse).round(1)
G = G.sort_values("rembourse", ascending=False)
G.to_csv(RACINE / "out/groupes_remboursements_vs_versements.csv")
pd.set_option("display.width", 250)
print("\n== Par groupe (2025, versements nets)")
print(G.head(20).assign(rembourse=lambda d: (d.rembourse/1e6).round(0), verse_2025=lambda d: (d.verse_2025/1e6).round(1))
      [["medicaments", "rembourse", "verse_2025", "euros_verses_pour_1000_rembourses", "exemple_ts"]].to_string())
gros = G[G.rembourse > 100e6].dropna(subset=["verse_2025"]).sort_values("euros_verses_pour_1000_rembourses", ascending=False)
print("\nGroupes > 100 M€ remboursés, ratio le plus élevé :")
print(gros.head(8)[["rembourse", "verse_2025", "euros_verses_pour_1000_rembourses"]].to_string())
