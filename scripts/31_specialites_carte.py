"""Pistes 3 et 4 (24/11) grâce à l'annuaire RPPS (spécialité, mode d'exercice, département de chaque médecin) :
3. ce que les labos versent à chaque spécialité, face à ce que cette spécialité prescrit (Open Medic 2025 par prescripteur) ;
4. carte : euros reçus par médecin dans chaque département.
Sorties : out/specialites_versements_prescriptions.csv, out/labos_cibles_specialites.csv, out/departements_euros_par_medecin.csv

Choix de méthode (tous déterministes) :
- Montants : vue `ts_net` de commun (sans double compte convention + rémunération liée), année 2025 seulement.
- Médecins retenus : personnes distinctes (Identifiant PP) de profession « Médecin » ayant au moins une ligne d'activité
  en cours (mode d'exercice renseigné) et qui ne sont pas étudiantes (internes, docteurs juniors). Le fichier
  Personne_activite contient une ligne par activité, et aussi des inscrits sans aucune activité : ils sont écartés.
- Spécialité : savoir-faire de type S (spécialité ordinale) du fichier SavoirFaire, classé par la table explicite
  CATEGORIE ci-dessous (alignée sur les codes PSP_SPE d'Open Medic). Si un médecin a plusieurs S (546 cas) : on garde
  une catégorie autre que la médecine générale si elle existe (la spécialité acquise en plus), puis le plus petit code
  savoir-faire. Sans S : « sans spécialité renseignée ».
- Département : département le plus fréquent parmi ses lieux d'activité (égalité : le plus petit code), calculé comme
  la macro dep() de commun (97x sur 3 caractères, Corse = 20). Monaco, collectivités d'outre-mer et étranger : écartés.
- Moyenne fragile (un inventeur touche des millions en redevances) : on donne aussi la médiane parmi les payés et la
  moyenne hors 1 % des médecins les plus payés du groupe (les floor(1 % x effectif) premiers montants retirés)."""
import warnings, pandas as pd, duckdb
warnings.filterwarnings("ignore", category=DeprecationWarning)
from commun import RACINE, vues_ts, groupe_labo, lire_openmedic, montant_fr, sql_chemin
E = RACINE/"data/ext"
fa = sorted((E/"rpps").glob("PS_LibreAcces_Personne_activite*.txt"))[-1]
fs = sorted((E/"rpps").glob("PS_LibreAcces_SavoirFaire*.txt"))[-1]
con = duckdb.connect()  # en mémoire : commun.connexion() ouvrirait data/travail.duckdb en écriture
con.execute("SET memory_limit='8GB'; SET preserve_insertion_order=false;")
vues_ts(con)
# même logique que la macro dep() de commun ; 98x sur 3 caractères aussi, pour pouvoir écarter Monaco et les COM
con.execute("""CREATE MACRO dep(cp) AS CASE
  WHEN regexp_matches(coalesce(cp,''), '^9[78][0-9]') THEN substr(cp,1,3)
  WHEN regexp_matches(coalesce(cp,''), '^20[0-9]') THEN '20'
  WHEN regexp_matches(coalesce(cp,''), '^[0-9]{5}') THEN substr(cp,1,2)
  ELSE NULL END""")
DEPS = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["20", "971", "972", "973", "974", "976"]
con.execute("CREATE TABLE deps AS SELECT unnest(?) dep", [DEPS])

# --- table explicite libellé de spécialité ordinale RPPS -> catégorie (= libellés des codes PSP_SPE d'Open Medic)
MG, AU = "Médecine Générale", "autres spécialités"
CATEGORIE = {
 "Spécialiste en Médecine Générale": MG, "Qualifié en Médecine Générale": MG, "Médecine Générale": MG,
 "Anesthesie-réanimation": "Anesthesie-réanimation", "Anesthésie-réanimation opt réanimation-pédiatrique": "Anesthesie-réanimation",
 "Cardiologie et maladies vasculaires": "Cardiologie", "Méd cardiovasculaire opt imagerie cardio d'expert": "Cardiologie",
 "Méd cardiovasculaire opt card interventionnelle": "Cardiologie", "Méd cardiovasculaire opt rythmo inter stimu card": "Cardiologie",
 **{l: "Chirurgie" for l in ["Chirurgie générale", "Chirurgie orthopédique et traumatologie", "Chirurgie urologique",
    "Chirurgie viscérale et digestive", "Chirurgie plastique reconstructrice et esthétique", "Chirurgie vasculaire", "Neuro-chirurgie",
    "Chirurgie thoracique et cardio-vasculaire", "Chirurgie infantile", "Chirurgie pédiatrique option orthopédie pédiatrique",
    "Chirurgie pédiatrique option chirurgie viscérale pédiatrique", "Chirurgie viscérale et digestive opt endo chir"]},
 **{l: "Stomatologie" for l in ["Stomatologie", "Chirurgie maxillo-faciale et stomatologie", "Chirurgie maxillo-faciale",
    "Chirurgie maxillo-faciale (réforme 2017)", "CHIRURGIE ORALE"]},
 "Dermatologie et vénéréologie": "Dermatologie et vénéréologie",
 "Radio-diagnostic": "Radio-diagnostic", "Radiologie et imagerie médicale opt radio inter av": "Radio-diagnostic",
 **{l: "Gynécologie-obstétrique" for l in ["Gynécologie-obstétrique", "Gynécologie médicale",
    "Gynéco-obstétrique et Gynéco médicale option Gynéco-obst", "Gynéco-obstétrique et Gynéco médicale option Gynéco-médicale"]},
 "Gastro-entérologie et hépatologie": "Gastro-entérologie et hépatologie",
 "Médecine interne": "Médecine interne", "Médecine interne et immunologie clinique": "Médecine interne",
 "Oto-rhino-laryngologie": "Oto-rhino-laryngologie", "O.R.L et chirurgie cervico faciale": "Oto-rhino-laryngologie",
 "ORL - chir cervico-faciale opt audiophonologie": "Oto-rhino-laryngologie",
 **{l: "Pédiatrie" for l in ["Pédiatrie", "Pédiatrie option néonatologie", "Pédiatrie option neuropédiatrie",
    "Pédiatrie option pneumopédiatrie", "Pédiatrie option réanimation pédiatrique"]},
 "Pneumologie": "Pneumologie", "Pneumologie option soins intensifs respiratoires": "Pneumologie",
 "Rhumatologie": "Rhumatologie",
 "Ophtalmologie": "Ophtalmologie", "Ophtalmologie opt chir ophtalmopéd strabologique": "Ophtalmologie",
 **{l: "Psychiatrie" for l in ["Psychiatrie", "Psychiatrie option enfant & adolescent", "Psychiatrie option enfant et adolescent",
    "Psychiatrie option psychiatrie de la personne âgée", "Neuro-psychiatrie"]},
 "Neurologie": "Neurologie", "Neurologie opt trait interv ischémie céréb aigüe": "Neurologie",
 "Néphrologie": "Néphrologie", "Néphrologie option soins intensifs néphrologiques": "Néphrologie",
 "Endocrinologie et métabolisme": "Endocrinologie et métabolisme", "Endocrinologie, diabétologie, nutrition": "Endocrinologie et métabolisme",
 "Médecine physique et réadaptation": "Médecine physique et réadaptation",
 "Anatomie et cytologie pathologiques": "Anatomie et cytologie pathologiques",
 **{l: "Biologie médicale" for l in ["Biologie médicale", "Biologie médicale option biologie générale",
    "Biologie médicale option hématologie et immunologie", "Biologie médicale option médecine moléculaire, génétique et pharmacologie",
    "Biologie médicale option biologie de la reproduction", "Biologie médicale option agents infectieux"]},
 # sans code PSP_SPE propre dans Open Medic : regroupées, pas de ratio prescrit
 **{l: AU for l in ["Médecine du travail", "Gériatrie", "Médecine d'urgence", "Santé publique et médecine sociale",
    "Santé publique option administration de la santé", "Oncologie option médicale", "Oncologie option radiothérapie",
    "Oncologie (option onco-hématologie)", "Radio-thérapie", "Médecine vasculaire", "Médecine intensive-réanimation",
    "Médecine intensive-réanimation opt réa pédiatrique", "Médecine nucléaire", "Allergologie", "Maladies infectieuses et tropicales",
    "Hématologie", "Hématologie (option Maladie du sang)", "Hématologie (réforme 2017)", "Hématologie (option Onco-hématologie)",
    "Génétique médicale", "Médecine légale et expertises médicales", "Recherche médicale"]},
}
# codes PSP_SPE d'Open Medic -> mêmes catégories (90 salariés/hôpital, 98 autres prescripteurs, 99 inconnu : hors tableau)
SPE = {"1": MG, "2": "Anesthesie-réanimation", "3": "Cardiologie", "4": "Chirurgie", "5": "Dermatologie et vénéréologie",
 "6": "Radio-diagnostic", "7": "Gynécologie-obstétrique", "8": "Gastro-entérologie et hépatologie", "9": "Médecine interne",
 "11": "Oto-rhino-laryngologie", "12": "Pédiatrie", "13": "Pneumologie", "14": "Rhumatologie", "15": "Ophtalmologie", "17": "Psychiatrie",
 "18": "Stomatologie", "31": "Médecine physique et réadaptation", "32": "Neurologie", "35": "Néphrologie",
 "37": "Anatomie et cytologie pathologiques", "38": "Biologie médicale", "42": "Endocrinologie et métabolisme"}

sf = con.execute(f"""SELECT DISTINCT "Identifiant PP" rpps, "Code savoir-faire" code, "Libellé savoir-faire" libelle
  FROM read_csv('{sql_chemin(fs)}', delim='|', header=true, all_varchar=true, quote='', ignore_errors=true)
  WHERE "Libellé profession"='Médecin' AND "Code type savoir-faire"='S'""").df()
sf["libelle"] = sf.libelle.str.strip()  # ex. « Radio-thérapie » porte une espace finale dans le fichier
inconnus = set(sf.libelle) - set(CATEGORIE)
if inconnus: print("ATTENTION libellés S non classés (mis en autres spécialités) :", sorted(inconnus))
sf["categorie"] = sf.libelle.map(CATEGORIE).fillna(AU)
sf["pas_mg"] = (sf.categorie != MG).astype(int)
sf = sf.sort_values(["rpps", "pas_mg", "code"], ascending=[True, False, True]).drop_duplicates("rpps")
con.register("sf_df", sf[["rpps", "libelle", "categorie"]])

con.execute(f"""CREATE TABLE act AS SELECT "Identifiant PP" rpps, "Libellé catégorie professionnelle" cat_pro, "Code mode exercice" mode,
  dep(CASE WHEN length("Code postal (coord. structure)")=4 THEN '0'||"Code postal (coord. structure)" ELSE "Code postal (coord. structure)" END) dep
  FROM read_csv('{sql_chemin(fa)}', delim='|', header=true, all_varchar=true, quote='', ignore_errors=true) WHERE "Libellé profession"='Médecin'""")
n_pers, n_act = con.execute("SELECT count(DISTINCT rpps), count(DISTINCT rpps) FILTER (WHERE mode IS NOT NULL) FROM act").fetchone()
con.execute("""CREATE TABLE rpps AS
  WITH a AS (SELECT * FROM act WHERE mode IS NOT NULL AND rpps NOT IN (SELECT rpps FROM act WHERE cat_pro='Etudiant')),
  d AS (SELECT rpps, arg_min(dep, (-n, dep)) dep FROM (SELECT rpps, dep, count(*) n FROM a WHERE dep IN (SELECT dep FROM deps) GROUP BY 1,2) GROUP BY 1)
  SELECT a.rpps, bool_or(a.mode='L') liberal, min(d.dep) dep, coalesce(min(s.categorie), 'sans spécialité renseignée') categorie
  FROM a LEFT JOIN d USING (rpps) LEFT JOIN sf_df s USING (rpps) GROUP BY a.rpps""")
n_ret, n_mg = con.execute(f"SELECT count(*), count(*) FILTER (WHERE categorie='{MG}') FROM rpps").fetchone()
print(f"RPPS médecins : {n_pers} personnes, {n_act} avec une activité en cours, {n_ret} retenus hors étudiants, dont {n_mg} généralistes")

# versements 2025 (nets) aux médecins
con.execute("""CREATE TABLE v AS SELECT beneficiaire_identifiant rpps, raison_sociale, montant FROM ts_net
  WHERE beneficiaire_categorie_code='PRS' AND profession_libelle='Médecin' AND year(date)=2025""")
print(con.execute("""SELECT round(100*avg((r.rpps IS NOT NULL)::INT),1) pct_lignes, round(100*sum(montant) FILTER (WHERE r.rpps IS NOT NULL)/sum(montant),1) pct_euros,
  round(sum(montant)/1e6,1) total_meur FROM v LEFT JOIN rpps r USING (rpps)""").df().to_string(index=False), "(rattachés aux médecins retenus, 2025 net)")
# un montant par médecin retenu (0 si rien reçu)
M = con.execute("""SELECT r.*, coalesce(p.eur, 0) eur FROM rpps r LEFT JOIN (SELECT rpps, sum(montant) eur FROM v GROUP BY 1) p USING (rpps)""").df()

def resume(g):
    n = len(g); e = g.eur.sort_values(ascending=False); payes = g.eur[g.eur > 0]
    return pd.Series({"medecins": n, "liberaux": int(g.liberal.sum()), "medecins_payes": len(payes),
        "verse_2025": round(e.sum()), "verse_2025_liberaux": round(g.eur[g.liberal].sum()),
        "pct_medecins_payes_2025": round(100 * len(payes) / n, 1), "eur_recus_par_medecin": round(e.sum() / n),
        "eur_median_payes": round(payes.median()) if len(payes) else None,
        "eur_moyen_hors_top1pct": round(e.iloc[n // 100:].mean()), "eur_max": round(e.iloc[0])})

# --- 3. spécialités
om = lire_openmedic("NB_2025_cip13_age_sexe_spe.CSV.gz"); om["rem"] = montant_fr(om.REM)
P = om.groupby("PSP_SPE").rem.sum().rename(index=lambda c: SPE.get(str(int(c)), f"code {c}")).groupby(level=0).sum()
print("\nRemboursements 2025 par prescripteur (Md€) :"); print((P.sort_values(ascending=False)/1e9).round(2).head(12).to_string())
T = M.groupby("categorie").apply(resume).join(P.rename("prescrit_liberal_2025"))
T.loc["TOUS"] = resume(M); T.loc["spécialistes (hors MG)"] = resume(M[~M.categorie.isin([MG, "sans spécialité renseignée"])])
# ratio des spécialistes : seulement sur les catégories qui ont un code Open Medic (sinon on divise des euros sans prescrit)
avec_code = [c for c in set(SPE.values()) if c != MG]
T.loc["spécialistes (hors MG)", "prescrit_liberal_2025"] = P[P.index.isin(avec_code)].sum()
T.loc["spécialistes (hors MG)", "verse_2025_liberaux"] = round(M[M.categorie.isin(avec_code) & M.liberal].eur.sum())
T["eur_recus_liberaux_pour_1000_prescrits"] = (1000 * T.verse_2025_liberaux / T.prescrit_liberal_2025).round(1)
T = T.sort_values("verse_2025", ascending=False); T.to_csv(RACINE/"out/specialites_versements_prescriptions.csv")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 200); print("\n"); print(T.to_string())

# --- labos : quelles spécialités chaque grand groupe paie-t-il le plus ? (2025 net)
LS = con.execute("SELECT v.raison_sociale, r.categorie, sum(v.montant) eur FROM v JOIN rpps r USING (rpps) GROUP BY 1,2").df()
LS["g"] = LS.raison_sociale.map(groupe_labo)
LG = LS.groupby(["g", "categorie"]).eur.sum().reset_index()
LG["part"] = (100 * LG.eur / LG.groupby("g").eur.transform("sum")).round(1)
tot = LG.groupby("g").eur.sum().sort_values(ascending=False).head(20).index
top = LG.sort_values("eur", ascending=False).groupby("g").head(3)
top = top[top.g.isin(tot)].sort_values(["g", "eur"], ascending=[True, False]); top.to_csv(RACINE/"out/labos_cibles_specialites.csv", index=False)
print("\nSpécialités les plus payées par les 20 plus gros groupes (2025, %) :")
print(top.groupby("g").apply(lambda d: " ; ".join(f"{r.categorie} {r.part:.0f} %" for r in d.itertuples())).loc[tot].to_string())

# --- 4. carte : euros reçus par médecin et par département (2025, médecins actifs rattachés au département)
D = M[M.dep.notna()].groupby("dep").apply(resume)
D = D[D.medecins >= 100][["medecins", "medecins_payes", "verse_2025", "eur_recus_par_medecin", "eur_median_payes", "eur_moyen_hors_top1pct", "pct_medecins_payes_2025", "eur_max"]]
D = D.rename(columns={"medecins_payes": "payes", "verse_2025": "euros_2025", "eur_recus_par_medecin": "eur_par_medecin", "pct_medecins_payes_2025": "pct_payes"})
D = D.sort_values("eur_par_medecin", ascending=False).reset_index()
D["rang"] = range(1, len(D) + 1); D["rang_hors_top1pct"] = D.eur_moyen_hors_top1pct.rank(ascending=False, method="min").astype(int)
D["rang_median"] = D.eur_median_payes.rank(ascending=False, method="min").astype(int)
D.to_csv(RACINE/"out/departements_euros_par_medecin.csv", index=False)
print(f"\nDépartements ({len(D)}, dont DOM), € reçus par médecin en 2025 :"); print(D.head(10).to_string(index=False)); print("..."); print(D.tail(5).to_string(index=False))
print("DOM :"); print(D[D.dep.str.len() == 3].to_string(index=False))
g = D[D.dep == "33"].iloc[0]
print(f"Gironde : {g.eur_par_medecin:.0f} € par médecin (rang {g.rang} sur {len(D)}), médiane des payés {g.eur_median_payes:.0f} € "
      f"(rang {g.rang_median}), hors 1 % : {g.eur_moyen_hors_top1pct:.0f} € (rang {g.rang_hors_top1pct}), {g.pct_payes} % payés, max {g.eur_max:,.0f} €")
