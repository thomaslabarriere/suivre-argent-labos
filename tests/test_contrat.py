"""Le contrat d'entrée détecte les changements de source qui fausseraient les chiffres sans faire planter."""
import copy, json
import contrat_entrees as C

REF = json.loads(C.REF.read_text())
echecs = lambda m: {n for n, ok, _ in C.verifier(m) if not ok}


def test_reference_conforme_a_elle_meme():
    assert echecs(copy.deepcopy(REF)) == set()


def test_export_tronque():
    m = copy.deepcopy(REF); m["ts ts_2024"]["lignes"] = int(m["ts ts_2024"]["lignes"] * 0.6)
    assert "ts ts_2024 : lignes" in echecs(m)


def test_colonne_disparue_ou_renommee():
    m = copy.deepcopy(REF); m["ts ts_2025"]["colonnes"].pop("convention_liee")
    assert "ts ts_2025 : colonnes" in echecs(m)


def test_type_change():
    m = copy.deepcopy(REF); m["ts ts_2025"]["colonnes"]["montant"] = "VARCHAR"
    assert "ts ts_2025 : colonnes" in echecs(m)


def test_nouvelle_categorie_de_beneficiaire():
    m = copy.deepcopy(REF); m["ts codes"]["valeurs"]["beneficiaire_categorie_code"].append("NOUVEAU")
    assert "ts : valeurs de beneficiaire_categorie_code" in echecs(m)


def test_annee_manquante():
    m = copy.deepcopy(REF); m.pop("ts ts_2019")
    assert {"ts ts_2019 présent", "ts : aucune année manquante"} <= echecs(m)


def test_colonne_nouvelle_signalee_sans_echec():
    m = copy.deepcopy(REF); m["sirene_ul"]["colonnes"]["nouvelle_colonne"] = "VARCHAR"
    assert "sirene_ul : colonnes" not in echecs(m)
