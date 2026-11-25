"""Copie dans resultats/ les sorties publiées : agrégats ET fichiers nominatifs.

Les fichiers nominatifs (professionnels de santé, élus, experts de la HAS, dirigeants) reprennent des données
publiques de transparence.sante.gouv.fr, de la HATVP, de la HAS et du registre des entreprises. Les croisements
par nom comportent des homonymes possibles (colonnes `qualite`, `personnes_meme_nom`) et un lien d'intérêt n'est
pas une irrégularité : resultats/LISEZMOI.md le rappelle en tête du dossier.
"""
import pathlib, shutil, sys, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from commun import RACINE
OUT, PUB = RACINE / "out", RACINE / "resultats"

PUBLIABLES = [
    # agrégats
    "asmr_remboursements.csv", "asmr_par_groupe.csv",
    "labos_remboursements_vs_versements.csv", "groupes_remboursements_vs_versements.csv",
    "lobbying_groupes.csv", "lobbying_actions_sante.csv", "professionnels_par_profession.csv",
    "specialites_versements_prescriptions.csv", "labos_cibles_specialites.csv",
    "departements_euros_par_medecin.csv", "essais_par_labo.csv", "essais_par_etablissement.csv",
    "essais_vs_conventions.csv", "hopitaux_finances_et_acheteurs.csv", "marches_hopitaux_labos.csv",
    "marques_labos.csv", "groupes_fiche.csv",
    # nominatifs (données publiques, homonymes possibles)
    "professionnels_top.csv", "elus_beneficiaires.csv", "elus_liens_labos.csv",
    "experts_has_versements.csv", "experts_has_detail_labos.csv",
    "croisement_dirigeants_professionnels.csv", "croisement_structures_dirigees_par_labo.csv",
    # contrôle qualité
    "anomalies_declarations.csv", "test_verite.csv", "controle_100.csv", "journal_decisions.csv",
]

if __name__ == "__main__":
    PUB.mkdir(exist_ok=True)
    for f in PUBLIABLES:
        shutil.copy2(OUT / f, PUB / f); print("ok", f)
    for f in ["carte_euros_par_medecin.png"]:
        shutil.copy2(OUT / f, PUB / f); print("ok", f)

    # Le livrable principal : le rattachement de chaque structure à son SIREN / RNA.
    r = pd.read_csv(OUT / "rattachement_final.csv", dtype=str)
    cols = ["nom_declare", "categorie", "dep", "nb_lignes", "montant", "statut2", "identifiant2", "methode2",
            "confiance_ia", "nom_officiel", "ape", "cat_juridique", "alerte"]
    r[cols].rename(columns={"statut2": "statut", "identifiant2": "identifiant", "methode2": "methode"}) \
        .to_csv(PUB / "rattachement_structures.csv", index=False)
    print("ok rattachement_structures.csv", len(r), "structures")

    # Lots et décisions d'arbitrage IA : de quoi rejouer l'étape 08 sans relancer d'IA.
    A, PA = RACINE / "data/arbitrage", PUB / "arbitrage"
    PA.mkdir(exist_ok=True)
    for f in sorted(p for motif in ("lot_", "decision_", "revlot_", "revision_") for p in A.glob(motif + "*.jsonl")):
        shutil.copy2(f, PA / f.name)
    for f in ["CONSIGNES.md", "MANIFESTE.json"]:
        shutil.copy2(A / f, PA / f)
    print("ok arbitrage/", len(list(PA.glob("*.jsonl"))), "fichiers")
