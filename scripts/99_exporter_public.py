"""Copie dans resultats/ les sorties AGRÉGÉES publiables (aucune personne physique nommée).

Pourquoi : out/ contient des fichiers nominatifs (professionnels de santé, élus, experts HAS, dirigeants).
Ces données sont publiques sur transparence.sante.gouv.fr, mais l'article R1453-7 du code de la santé publique
protège les données directement identifiantes contre l'indexation par les moteurs de recherche externes :
un dépôt GitHub public est indexé. On ne publie donc que des agrégats (labos, départements, spécialités,
établissements, structures morales). Les fichiers nominatifs se régénèrent localement avec les scripts.
"""
import json, pathlib, shutil, sys, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from commun import RACINE, PERSONNES
OUT, PUB = RACINE / "out", RACINE / "resultats"

PUBLIABLES = [
    "asmr_remboursements.csv", "asmr_par_groupe.csv",
    "labos_remboursements_vs_versements.csv", "groupes_remboursements_vs_versements.csv",
    "lobbying_groupes.csv", "professionnels_par_profession.csv",
    "specialites_versements_prescriptions.csv", "labos_cibles_specialites.csv",
    "departements_euros_par_medecin.csv", "essais_par_labo.csv",
    "hopitaux_finances_et_acheteurs.csv", "marques_labos.csv", "groupes_fiche.csv",
]
# Colonnes qui trahiraient une personne physique : leur présence bloque l'export.
INTERDITES = {"nom", "prenom", "prenoms", "rpps", "identite", "dirigeant", "nom_declare"}

if __name__ == "__main__":
    PUB.mkdir(exist_ok=True)
    for f in PUBLIABLES:
        cols = set(pd.read_csv(OUT / f, nrows=0).columns)
        if cols & INTERDITES:
            raise SystemExit(f"{f} contient {cols & INTERDITES} : export refusé")
        shutil.copy2(OUT / f, PUB / f); print("ok", f)
    for f in ["carte_euros_par_medecin.png"]:
        shutil.copy2(OUT / f, PUB / f); print("ok", f)

    # Le livrable principal : le rattachement de chaque structure à son SIREN / RNA.
    # On retire les catégories qui désignent souvent une personne physique (étudiant, influenceur, vétérinaire).
    r = pd.read_csv(OUT / "rattachement_final.csv", dtype=str)
    r = r[~r.categorie.isin(PERSONNES)]
    cols = ["nom_declare", "categorie", "dep", "nb_lignes", "montant", "statut2", "identifiant2", "methode2",
            "confiance_ia", "nom_officiel", "ape", "cat_juridique", "alerte"]
    r[cols].rename(columns={"statut2": "statut", "identifiant2": "identifiant", "methode2": "methode"}) \
        .to_csv(PUB / "rattachement_structures.csv", index=False)
    print("ok rattachement_structures.csv", len(r), "structures")

    # Lots et décisions d'arbitrage IA, sans les cas « personnes » : de quoi rejouer l'étape 08 sans relancer d'IA.
    A, PA = RACINE / "data/arbitrage", PUB / "arbitrage"
    PA.mkdir(exist_ok=True)
    garder = set()
    for f in sorted(A.glob("lot_*.jsonl")) + sorted(A.glob("revlot_*.jsonl")):
        L = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        num = f.stem.split("_")[1]
        L = [x for x in L if x.get("categorie") not in PERSONNES]
        garder |= {(f.stem.split("_")[0], num, x["id"]) for x in L}
        (PA / f.name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in L), encoding="utf-8")
    for f in sorted(A.glob("decision_*.jsonl")) + sorted(A.glob("revision_*.jsonl")):
        lot = "lot" if f.stem.startswith("decision") else "revlot"; num = f.stem.split("_")[1]
        L = [l for l in open(f, encoding="utf-8") if l.strip() and (lot, num, json.loads(l)["id"]) in garder]
        (PA / f.name).write_text("".join(L), encoding="utf-8")
    for f in ["CONSIGNES.md", "MANIFESTE.json"]:
        shutil.copy2(A / f, PA / f)
    print("ok arbitrage/", len(list(PA.glob("*.jsonl"))), "fichiers")
