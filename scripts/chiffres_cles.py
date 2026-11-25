"""Les chiffres cités dans les documents, recalculés depuis les données.

docs/chiffres_cles.json garde, pour chaque chiffre, sa valeur et le texte exact sous lequel les documents le citent.
controle.py échoue si un chiffre a bougé (au-delà de 0,5 %) sans que ce fichier soit mis à jour, ou si son texte
n'apparaît plus dans aucun document. Un changement de méthode devient ainsi visible dans l'historique git.
Usage : .venv/bin/python scripts/chiffres_cles.py [--maj]   (--maj réécrit le fichier après relecture des écarts)"""
import json, pathlib, sys
import duckdb, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from commun import RACINE, vues_ts

FICHIER = pathlib.Path(__file__).resolve().parent.parent / "docs/chiffres_cles.json"
DOCS = ["README.md", "docs/RAPPORT.md", "docs/A_RETENIR.md"]
esp = lambda s: s.replace(",", " ").replace(".", ",")
md = lambda x, d=1: esp(f"{x/1e9:,.{d}f}") + " Md€"
me = lambda x, d=1: esp(f"{x/1e6:,.{d}f}") + " M€"
eur = lambda x: esp(f"{x:,.0f}") + " €"
nb = lambda x, suffixe="": esp(f"{x:,.0f}") + suffixe
pct = lambda x, d=0: esp(f"{x:,.{d}f}") + " %"


def calculer():
    o = lambda f, **k: pd.read_csv(RACINE / "out" / f, low_memory=False, **k)
    con = vues_ts(duckdb.connect())
    q = lambda s: con.execute(s).fetchone()
    brut, net = q("SELECT (SELECT sum(montant) FROM ts), (SELECT sum(montant) FROM ts_net)")
    gros = q("SELECT max(montant), count(*) FILTER (WHERE montant >= 1e7), sum(montant) FILTER (WHERE montant >= 1e7) FROM ts_net")
    rem = q("""SELECT sum(montant), sum(montant) FILTER (WHERE coalesce(motif_lien_interet,'') = '' AND coalesce(autre_motif,'') = ''
               AND coalesce(information_evenement,'') = '') FROM ts_net WHERE beneficiaire_categorie_code = 'PRS' AND lien_interet = 'remuneration'""")
    pers = q("""WITH p AS (SELECT personne, sum(montant) s FROM prs GROUP BY 1)
      SELECT count(*), median(s), count(*) FILTER (WHERE s >= 1e5), 100 * sum(s) FILTER (WHERE s >= (SELECT quantile_cont(s, 0.99) FROM p)) / sum(s) FROM p""")
    conv = q("SELECT sum(montant) FROM prs WHERE lien_interet = 'convention'")[0]
    an = o("anomalies_declarations.csv"); ho = an[an.anomalie.str.startswith("hospitalité")]
    pr = o("prestataires.csv").euros.sum()
    asmr = o("asmr_remboursements.csv").set_index("asmr")
    sp = o("specialites_versements_prescriptions.csv").set_index("categorie")
    el = o("elus_beneficiaires.csv"); ed = o("elus_declarations_vs_versements.csv")
    ex = o("experts_has_versements.csv"); ex = ex[ex.qualite.isin(["sûre", "probable"])]
    di = o("croisement_dirigeants_professionnels.csv"); gr = o("croisement_structures_dirigees_par_labo.csv")
    lo = o("lobbying_groupes.csv"); hp = o("hopitaux_finances_et_acheteurs.csv")
    tv = o("test_verite.csv"); tf = tv[tv.issue.fillna("").str.contains("fiable")]
    ra = o("rattachement_final.csv"); fi = ra[ra.statut2 == "fiable"]
    dep = o("departements_euros_par_medecin.csv", dtype={"dep": str}).set_index("dep")
    C = {  # nom : (valeur, texte cité dans les documents, source)
        "total brut déclaré": (brut, md(brut), "ts"),
        "total net": (net, md(net, 2), "ts_net"),
        "double compte": (brut - net, md(brut - net), "ts - ts_net"),
        "plus grosse ligne": (gros[0], eur(gros[0]), "33"),
        "part de la plus grosse ligne": (100 * gros[0] / net, pct(100 * gros[0] / net, 1), "33"),
        "lignes de 10 M€ ou plus": (gros[1], nb(gros[1], " lignes"), "33"),
        "part des lignes de 10 M€ ou plus": (100 * gros[2] / net, pct(100 * gros[2] / net, 1), "33"),
        "rémunérations aux professionnels": (rem[0], me(rem[0]), "33"),
        "rémunérations sans motif": (rem[1], me(rem[1], 0), "33"),
        "part des rémunérations sans motif": (100 * rem[1] / rem[0], pct(100 * rem[1] / rem[0], 1), "33"),
        "plus gros hébergement": (ho.montant.max(), eur(ho.montant.max()), "33"),
        "avantages d'hospitalité de 20 000 € ou plus": (len(ho), nb(len(ho), " avantages"), "33"),
        "professionnels payés": (pers[0], nb(pers[0]), "24"),
        "médiane par professionnel": (pers[1], eur(pers[1]), "24"),
        "professionnels au-dessus de 100 000 €": (pers[2], nb(pers[2]), "24"),
        "part du 1 % le mieux payé": (pers[3], pct(pers[3]), "24"),
        "conventions non exécutées des professionnels": (conv, me(conv, 0), "24"),
        "prestataires": (pr, md(pr), "34"),
        "hors prestataires": (net - pr, md(net - pr), "34"),
        "remboursé ASMR V": (asmr.loc["V", "rembourse"], md(asmr.loc["V", "rembourse"]), "26"),
        "part ASMR V": (asmr.loc["V", "pct"], pct(asmr.loc["V", "pct"], 1), "26"),
        "euros par spécialiste": (sp.loc["spécialistes (hors MG)", "eur_recus_par_medecin"], eur(sp.loc["spécialistes (hors MG)", "eur_recus_par_medecin"]), "31"),
        "euros par généraliste": (sp.loc["Médecine Générale", "eur_recus_par_medecin"], eur(sp.loc["Médecine Générale", "eur_recus_par_medecin"]), "31"),
        "Gironde, euros par médecin": (dep.loc["33", "eur_par_medecin"], eur(dep.loc["33", "eur_par_medecin"]), "31"),
        "élus bénéficiaires": (el[["nom", "prenom", "departement"]].drop_duplicates().shape[0], nb(el[["nom", "prenom", "departement"]].drop_duplicates().shape[0], " élus"), "24"),
        "élus avec déclaration publiée": (ed[ed.declarations_publiees > 0][["nom", "prenom", "departement"]].drop_duplicates().shape[0],
                                          nb(ed[ed.declarations_publiees > 0][["nom", "prenom", "departement"]].drop_duplicates().shape[0], " élus"), "35"),
        "experts HAS retrouvés": (len(ex), nb(len(ex), " membres"), "27"),
        "experts HAS, pendant le mandat": (ex.pendant_mandat_total.sum(), esp(f"{ex.pendant_mandat_total.sum()/1e3:,.0f}") + " k€", "27"),
        "experts HAS payés pendant le mandat": ((ex.pendant_mandat_total > 0).sum(), nb((ex.pendant_mandat_total > 0).sum(), " ont reçu"), "27"),
        "dirigeants payés à titre personnel": (di[["nom", "prenoms"]].drop_duplicates().shape[0], nb(di[["nom", "prenoms"]].drop_duplicates().shape[0], " dirigeants"), "11"),
        "GERS, net": (gr[gr.siren_beneficiaire == 308296938].montant_du_labo.sum(), me(gr[gr.siren_beneficiaire == 308296938].montant_du_labo.sum()), "09"),
        "groupes lobbyistes": (len(lo), nb(len(lo), " groupes"), "22"),
        "lobbying 2022 à 2025": (lo.lobbying_2022_2025.sum(), me(lo.lobbying_2022_2025.sum(), 0), "22"),
        "paires hôpital × labo": (len(hp), nb(len(hp), " paires"), "28"),
        "hôpitaux": (hp.hopital_siren.nunique(), nb(hp.hopital_siren.nunique(), " hôpitaux"), "28"),
        "structures rattachées de façon fiable": (len(fi), nb(len(fi)), "08"),
        "erreur probable du rattachement": (100 * (tf.type_erreur == "erreur probable de notre part").sum() / len(tf),
                                            pct(100 * (tf.type_erreur == "erreur probable de notre part").sum() / len(tf), 1), "12"),
    }
    return {k: {"valeur": float(v), "texte": t, "source": s} for k, (v, t, s) in C.items()}


def verifier(actuel=None):
    actuel = actuel or calculer()
    if not FICHIER.exists():
        return [("chiffres clés : fichier présent", False, "lancer chiffres_cles.py --maj")]
    ref, res = json.loads(FICHIER.read_text()), []
    docs = " ".join((FICHIER.parent.parent / d).read_text() for d in DOCS)
    for k, a in actuel.items():
        r = ref.get(k)
        if r is None:
            res.append((f"chiffre « {k} » enregistré", False, "absent de docs/chiffres_cles.json")); continue
        ecart = abs(a["valeur"] - r["valeur"]) / max(abs(r["valeur"]), 1e-9)
        res.append((f"chiffre « {k} » inchangé", ecart <= 0.005, f"{r['texte']} -> {a['texte']}" if ecart > 0.005 else a["texte"]))
        res.append((f"chiffre « {k} » cité tel quel", a["texte"] in docs, f"« {a['texte']} » introuvable dans les documents" if a["texte"] not in docs else ""))
    return res


if __name__ == "__main__":
    actuel = calculer()
    if "--maj" in sys.argv:
        FICHIER.write_text(json.dumps(actuel, ensure_ascii=False, indent=1)); print("écrit :", FICHIER)
    res = verifier(actuel)
    for n, ok, d in res:
        if not ok or "--tout" in sys.argv:
            print(f"[{'ok' if ok else 'ÉCHEC'}] {n} {d}")
    print(f"{sum(r[1] for r in res)}/{len(res)} réussis")
    sys.exit(0 if all(r[1] for r in res) else 1)
