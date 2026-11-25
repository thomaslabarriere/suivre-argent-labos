"""Contrôle avant publication : le dépôt ne part pas si une règle est violée.

Chaque contrôle vient d'un défaut réellement rencontré (voir docs/RAPPORT.md, section 8) :
  A. reproductibilité : deux exécutions des scripts nominatifs donnent les mêmes fichiers ;
  B. identité : aucun identifiant factice ou partagé ne sert de clé personne dans un fichier publié ;
  C. doublons : une personne n'apparaît qu'une fois par fichier ;
  D. montants : totaux nets cohérents, et montants publiés recalculés ligne à ligne depuis `ts_net` ;
  E. publication : resultats/ est à jour, pas de secret, pas de tiret cadratin, chiffres clés présents dans les docs ;
  F. contrôle humain : out/controle_humain.csv, les 20 premiers noms de chaque fichier nominatif, à relire à la main ;
  G. sources : contrat sur les données d'entrée (contrat_entrees.py) ;
  H. chiffres : les chiffres des documents n'ont pas bougé (chiffres_cles.py) ; erreur du rattachement sous 3 % ;
  I. recoupements : chaque fichier publié retombe sur les totaux des fichiers voisins ;
  J. avertissement (non bloquant) : personnes coupées en deux (lignes avec et sans RPPS), dans out/personnes_coupees.csv.
Usage : .venv/bin/python scripts/controle.py [--rapide]   (--rapide saute A, qui relance les scripts, ~2 min)
Code de sortie 1 si un contrôle échoue."""
import hashlib, re, subprocess, sys, pathlib
import duckdb, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from commun import RACINE, connexion, vue_lignes_net, RPPS_VALIDES

OUT, PUB, SCR = RACINE / "out", RACINE / "resultats", RACINE / "scripts"
res, avertissements = [], []
def ok(groupe, nom, cond, detail=""):
    res.append((groupe, nom, bool(cond), detail)); print(f"[{'ok' if cond else 'ÉCHEC'}] {groupe} {nom} {detail}", flush=True)
def avertir(groupe, nom, detail):
    avertissements.append((groupe, nom, detail)); print(f"[avertissement] {groupe} {nom} {detail}", flush=True)
md5 = lambda f: hashlib.md5(f.read_bytes()).hexdigest()
lire = lambda f, **k: pd.read_csv(PUB / f, dtype={"rpps": str, "dep": str, "departement": str, "siren": str}, **k)

# --- A. reproductibilité (avant d'ouvrir la base : certains scripts y écrivent)
NOMINATIFS = {"24_professionnels_elus.py": ["professionnels_top.csv", "elus_beneficiaires.csv", "professionnels_par_profession.csv"],
              "27_experts_has.py": ["experts_has_versements.csv", "experts_has_detail_labos.csv"],
              "11_croisement_personnes.py": ["croisement_dirigeants_professionnels.csv", "croisement_structures_dirigees_par_labo.csv"],
              "33_anomalies.py": ["anomalies_declarations.csv"], "34_prestataires.py": ["prestataires.csv"],
              "35_elus_declarations.py": ["elus_declarations_vs_versements.csv"]}
if "--rapide" not in sys.argv:
    for script, fichiers in NOMINATIFS.items():
        empreintes = []
        for _ in range(2):
            r = subprocess.run([sys.executable, script], cwd=SCR, capture_output=True, text=True)
            if r.returncode:
                ok("A", script, False, "plante : " + r.stderr.strip().splitlines()[-1][:150]); break
            empreintes.append([md5(OUT / f) for f in fichiers])
        else:
            ok("A", f"{script} déterministe", empreintes[0] == empreintes[1], ", ".join(fichiers))

# --- T. tests automatiques (fonctions, régressions sur le mini jeu fictif, contrat)
r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(RACINE / "tests")], cwd=RACINE, capture_output=True, text=True)
ok("T", "tests automatiques (pytest)", r.returncode == 0, (r.stdout.strip().splitlines() or [""])[-1])

con = vue_lignes_net(connexion())
valides = set(pd.read_parquet(RPPS_VALIDES).rpps)

# --- B. identité
for f, col in [("professionnels_top.csv", "rpps"), ("elus_beneficiaires.csv", "rpps"), ("experts_has_versements.csv", "rpps"),
               ("elus_declarations_vs_versements.csv", "rpps")]:
    v = lire(f)[col].dropna().astype(str).str.replace(r"\.0$", "", regex=True)
    mauvais = sorted(set(v) - valides)
    ok("B", f"{f} : rpps tous valides", not mauvais, f"{len(mauvais)} invalides {mauvais[:3]}" if mauvais else f"{len(v)} RPPS")
x = con.execute("SELECT max(n) FROM (SELECT personne, count(DISTINCT regexp_replace(nom_n, ' ', '', 'g')) n FROM prs WHERE rpps IS NOT NULL GROUP BY 1)").fetchone()[0]
ok("B", "aucun RPPS retenu ne porte plus de 5 noms", x <= 5, f"max {x}")
e = lire("experts_has_versements.csv")
ok("B", "un seul RPPS par expert", not e.rpps.dropna().str.contains(";").any())
ok("B", "aucun total publié pour un homonyme possible", e[e.qualite == "homonyme possible"].total_recu.isna().all())
el = lire("elus_beneficiaires.csv")
ok("B", "élus : département toujours renseigné, jamais 00", el.departement.notna().all() and not (el.departement == "00").any())
ok("B", "élus : outre-mer pris en compte", (el.departement.str.len() == 3).any(), str(sorted(el[el.departement.str.len() == 3].departement.unique())))

# --- C. doublons
for f, cles in [("professionnels_top.csv", ["nom", "prenom", "dep", "rpps"]), ("elus_beneficiaires.csv", ["nom", "prenom", "departement", "personne"]),
                ("experts_has_versements.csv", ["id"]), ("elus_declarations_vs_versements.csv", ["nom", "prenom", "departement", "rpps", "groupe_labo"]),
                ("croisement_dirigeants_professionnels.csv", ["siren", "nom", "prenoms", "laboratoire"])]:
    d = lire(f); n = d.duplicated(cles).sum()
    ok("C", f"{f} sans doublon", n == 0, f"{n} doublons sur {cles}" if n else f"{len(d)} lignes")

# --- D. montants
brut, net = con.execute("SELECT (SELECT sum(montant) FROM ts), (SELECT sum(montant) FROM ts_net)").fetchone()
ok("D", "double compte retiré (brut - net ≈ 6,4 Md€)", 6.3e9 < brut - net < 6.5e9, f"{(brut-net)/1e9:.2f} Md€")
tp = con.execute("SELECT sum(montant) FROM prs").fetchone()[0]
pp = lire("professionnels_par_profession.csv").meur.sum() * 1e6
ok("D", "par profession = total des professionnels", abs(pp - tp) / tp < 0.001, f"{pp/1e9:.3f} / {tp/1e9:.3f} Md€")
# 20 lignes du classement recalculées depuis prs (clé personne) : un montant brut ou fusionné ne passerait pas
t = lire("professionnels_top.csv").head(20)
ecarts = []
for _, r in t.iterrows():
    if pd.notna(r.rpps):
        m = con.execute("SELECT sum(montant) FROM prs WHERE personne = ?", [r.rpps]).fetchone()[0]
    else:
        m = con.execute("SELECT sum(montant) FROM prs WHERE rpps IS NULL AND nom_n = nn(?) AND prenom_n = split_part(nn(?), ' ', 1) AND dep = ?",
                        [r.nom, r.prenom, r.dep]).fetchone()[0]
    if abs((m or 0) - r.euros) > 1: ecarts.append((r.nom, r.euros, m))
ok("D", "top 20 professionnels recalculés en net", not ecarts, str(ecarts[:3]))
# dirigeants : 10 lignes recalculées (montant perso net, même labo normalisé)
d = lire("croisement_dirigeants_professionnels.csv").sort_values("recu_personnellement", ascending=False).head(10)
ecarts = []
for _, r in d.iterrows():
    m = con.execute("""SELECT sum(montant) FROM prs WHERE nom_n = nn(?) AND prenom_n = split_part(nn(replace(coalesce(?, ''), ',', ' ')), ' ', 1)
                       AND norm(raison_sociale) = norm(?)""", [r.nom, r.prenoms, r.laboratoire]).fetchone()[0]
    if abs((m or 0) - r.recu_personnellement) > 1: ecarts.append((r.nom, r.recu_personnellement, m))
ok("D", "top 10 dirigeants recalculés en net", not ecarts, str(ecarts[:3]))
g = lire("croisement_structures_dirigees_par_labo.csv")
gn = con.execute("""SELECT sum(l.montant) FROM lignes_net l JOIN final2 f USING (struct_id) WHERE f.statut2 = 'fiable' AND f.identifiant2 = '308296938'
                    AND norm(l.raison_sociale) IN (SELECT norm(laboratoire) FROM g WHERE siren_beneficiaire = 308296938)""").fetchone()[0]
ok("D", "GERS en net", abs(g[g.siren_beneficiaire == 308296938].montant_du_labo.sum() - gn) < 10, f"{gn/1e6:.1f} M€")
pr = lire("prestataires.csv").euros.sum()
ok("D", "prestataires : moins que le total net", 0 < pr < net, f"{pr/1e9:.2f} Md€ sur {net/1e9:.2f}")

# --- E. publication
sys.path.insert(0, str(SCR)); import importlib; exp = importlib.import_module("99_exporter_public")
perimes = [f for f in exp.PUBLIABLES if md5(OUT / f) != md5(PUB / f)]
ok("E", "resultats/ identique à out/ (exporter relancé)", not perimes, str(perimes[:4]))
suivis = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True).stdout.split()
ok("E", "aucun .env versionné", not any(pathlib.Path(f).name.startswith(".env") for f in suivis))
SECRET = re.compile("sk-" + "ant-" + r"|ghp_[A-Za-z0-9]{20}|BEGIN (RSA|OPENSSH) PRIVATE|ANTHROPIC_API_KEY\s*=\s*\S")
fuites = [f for f in suivis if f.endswith((".py", ".md", ".sh", ".json", ".txt")) and SECRET.search((RACINE / f).read_text(errors="ignore"))]
ok("E", "aucun secret dans les fichiers versionnés", not fuites, str(fuites))
docs = {f: (RACINE / f).read_text() for f in ["README.md", "docs/RAPPORT.md", "docs/A_RETENIR.md", "resultats/LISEZMOI.md"]}
ok("E", "pas de tiret cadratin dans les documents", not any("—" in s for s in docs.values()))
fr = lambda x: f"{x:,.0f}".replace(",", " ")
attendus = {"total net": f"{net/1e9:.2f}".replace(".", ","),
            "professionnels": fr(con.execute("SELECT count(DISTINCT personne) FROM prs").fetchone()[0]),
            "élus": str(el[["nom", "prenom", "departement"]].drop_duplicates().shape[0]) + " élus",
            "experts sûrs ou probables": str(e.qualite.isin(["sûre", "probable"]).sum()) + " membres",
            "dirigeants": str(d.shape[0] and lire("croisement_dirigeants_professionnels.csv")[["nom", "prenoms"]].drop_duplicates().shape[0]) + " dirigeants"}
for k, v in attendus.items():
    ok("E", f"A_RETENIR ou RAPPORT cite le bon chiffre : {k}", v in docs["docs/A_RETENIR.md"] or v in docs["docs/RAPPORT.md"], f"« {v} »")

# --- G. sources
import contrat_entrees, chiffres_cles
for nom, r, detail in contrat_entrees.verifier():
    ok("G", nom, r, detail)

# --- H. chiffres des documents et seuil de qualité
for nom, r, detail in chiffres_cles.verifier():
    ok("H", nom, r, detail)
tv = pd.read_csv(OUT / "test_verite.csv", low_memory=False); tf = tv[tv.issue.fillna("").str.contains("fiable")]
taux = 100 * (tf.type_erreur == "erreur probable de notre part").sum() / len(tf)
ok("H", "erreur probable du rattachement sous 3 %", taux < 3, f"{taux:.1f} % sur {len(tf)} réponses « fiables »")

# --- I. recoupements entre fichiers publiés
proche = lambda a, b, tol=0.001: abs(a - b) <= tol * max(abs(a), abs(b), 1)
rb = {f: lire(f)[c].sum() for f, c in [("asmr_remboursements.csv", "rembourse"), ("asmr_par_groupe.csv", "total"),
      ("groupes_remboursements_vs_versements.csv", "rembourse"), ("labos_remboursements_vs_versements.csv", "rembourse")]}
ok("I", "remboursements identiques dans les 4 fichiers Open Medic", all(proche(v, rb["asmr_remboursements.csv"]) for v in rb.values()),
   " ; ".join(f"{k.split('.')[0]} {v/1e9:.2f}" for k, v in rb.items()))
sp = lire("specialites_versements_prescriptions.csv").set_index("categorie")
detail_sp = sp.drop(index=["TOUS", "spécialistes (hors MG)"])
ok("I", "spécialités : la somme des spécialités = TOUS", proche(detail_sp.verse_2025.sum(), sp.loc["TOUS", "verse_2025"])
   and detail_sp.medecins.sum() == sp.loc["TOUS", "medecins"], f"{detail_sp.verse_2025.sum()/1e6:.1f} / {sp.loc['TOUS', 'verse_2025']/1e6:.1f} M€")
ok("I", "spécialistes + généralistes + sans spécialité = TOUS", proche(sp.loc["spécialistes (hors MG)", "verse_2025"] + sp.loc["Médecine Générale", "verse_2025"]
   + sp.loc["sans spécialité renseignée", "verse_2025"], sp.loc["TOUS", "verse_2025"]))
dp = lire("departements_euros_par_medecin.csv")
ok("I", "départements : pas plus que le total des médecins", dp.euros_2025.sum() <= sp.loc["TOUS", "verse_2025"] * 1.001
   and dp.medecins.sum() <= sp.loc["TOUS", "medecins"], f"{dp.euros_2025.sum()/1e6:.1f} M€, {dp.medecins.sum():,.0f} médecins")
ok("I", "labos ciblant des spécialités : parts ≤ 100 % par groupe", (lire("labos_cibles_specialites.csv").groupby("g").part.sum() <= 100.5).all())
pq = con.execute(f"SELECT sum(t.montant) FROM ts_net t JOIN read_parquet('{RACINE / 'data/ext/prestataires.parquet'}') p USING (id)").fetchone()[0]
ok("I", "prestataires.csv = lignes marquées prestataires", proche(lire("prestataires.csv").euros.sum(), pq))
rs = lire("rattachement_structures.csv").montant.sum(); f2 = con.execute("SELECT sum(montant) FROM final2").fetchone()[0]
ok("I", "rattachement publié = toutes les structures", proche(rs, f2), f"{rs/1e9:.3f} Md€")
dt = lire("experts_has_detail_labos.csv").groupby(["nom", "prenom"]).total.sum()
ev = e[e.total_recu.notna()].set_index(["nom", "prenom"]).total_recu
ok("I", "experts : détail par labo = total par expert", all(abs(dt.get(k, 0) - v) <= 2 for k, v in ev.items()))
ed = lire("elus_declarations_vs_versements.csv").fillna({"rpps": ""}).groupby(["nom", "prenom", "departement", "rpps"], dropna=False)[["contrats_total", "avantages_total"]].sum().sum(axis=1)
eb = el.fillna({"rpps": ""}).groupby(["nom", "prenom", "departement", "rpps"]).euros.sum()
ok("I", "élus : versements par labo ≤ total de l'élu", all(v <= eb.get(k, 0) + 2 for k, v in ed.items()))

# --- J. personnes coupées en deux (avertissement)
cp = con.execute("""WITH a AS (SELECT nom_n, prenom_n, dep, count(DISTINCT rpps) n_rpps, sum(montant) FILTER (WHERE rpps IS NULL) sans_rpps,
    sum(montant) FILTER (WHERE rpps IS NOT NULL) avec_rpps FROM prs GROUP BY 1, 2, 3)
  SELECT * FROM a WHERE n_rpps = 1 AND sans_rpps >= 10000 ORDER BY sans_rpps DESC, nom_n, prenom_n, dep""").df()
cp.to_csv(OUT / "personnes_coupees.csv", index=False)
avertir("J", "personnes probablement coupées en deux (≥ 10 000 € sans RPPS, un seul RPPS au même nom)", f"{len(cp)} cas, {cp.sans_rpps.sum()/1e6:.1f} M€ -> out/personnes_coupees.csv")

# --- F. extrait pour relecture humaine
parts = []
for f, cols, tri in [("professionnels_top.csv", ["nom", "prenom", "dep", "rpps", "euros", "principal_labo", "alerte"], "euros"),
                     ("elus_beneficiaires.csv", ["nom", "prenom", "departement", "mandats", "rpps", "euros", "personnes_meme_nom"], "euros"),
                     ("experts_has_versements.csv", ["nom", "prenom", "commission", "qualite", "rpps", "total_recu", "pendant_mandat_total"], "total_recu"),
                     ("croisement_dirigeants_professionnels.csv", ["nom", "prenoms", "structure", "laboratoire", "recu_personnellement"], "recu_personnellement"),
                     ("elus_declarations_vs_versements.csv", ["nom", "prenom", "mandats", "groupe_labo", "contrats_5_ans_avant_declaration", "labo_cite_dans_declaration"], "contrats_5_ans_avant_declaration")]:
    x = lire(f).sort_values(tri, ascending=False).head(20)[cols]
    parts.append(x.assign(fichier=f, verifie_par="", correct_oui_non="", commentaire=""))
pd.concat(parts).to_csv(OUT / "controle_humain.csv", index=False)
print(f"\nrelecture humaine : {OUT / 'controle_humain.csv'} ({sum(len(p) for p in parts)} lignes ; vérifier chaque nom sur transparence.sante.gouv.fr)")

echecs = [r for r in res if not r[2]]
print(f"\n{len(res) - len(echecs)}/{len(res)} contrôles réussis, {len(avertissements)} avertissement(s)" + ("" if not echecs else " ; ÉCHECS : " + " | ".join(f"{g} {n}" for g, n, _, _ in echecs)))
sys.exit(1 if echecs else 0)
