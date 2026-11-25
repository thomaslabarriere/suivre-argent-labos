"""Tests des fonctions partagées. Chaque cas vient d'une erreur réelle ou d'un piège vu dans les données."""
import duckdb, pandas as pd, pytest
from commun import (cle_labo, groupe_labo, luhn, montant_fr, cle_structure, empreinte, macros_structures, MACROS)


@pytest.fixture(scope="module")
def sql():
    con = duckdb.connect()
    macros_structures(con)
    con.execute(MACROS)
    return lambda q, *a: con.execute(q, list(a)).fetchone()[0]


@pytest.mark.parametrize("nom, groupe", [
    ("MSD FRANCE", "MSD"), ("MSD VACCINS", "MSD"), ("MERCK SHARP & DOHME", "MSD"),   # le ratio MSD aberrant venait de là
    ("MERCK SERONO", "MERCK"), ("MERCK SANTE SAS", "MERCK"),
    ("JANSSEN-CILAG", "JOHNSON"), ("JOHNSON & JOHNSON MEDICAL SAS", "JOHNSON"),
    ("MYLAN MEDICAL SAS", "VIATRIS"), ("VIATRIS SANTE", "VIATRIS"),
    ("ELI LILLY AND COMPANY", "LILLY"), ("LILLY FRANCE", "LILLY"),
    ("LABORATOIRE GLAXOSMITHKLINE", "GLAXOSMITHKLINE"), ("GSK VACCINES", "GLAXOSMITHKLINE"),
    ("SANOFI-AVENTIS FRANCE", "SANOFI"), ("SANOFI WINTHROP INDUSTRIE", "SANOFI"),
    ("Les Laboratoires Servier", "SERVIER"), ("Laboratoires Théa", "THEA"),
    ("LABO BETA", "BETA"), ("LABORATORIOS FARMACEUTICOS ROVI, S.A.", "FARMACEUTICOS"), ("ABBOTT LABORATORIES", "ABBOTT"),
    ("", None), (None, None),
])
def test_groupe_labo(nom, groupe):
    assert groupe_labo(nom) == groupe


def test_cle_labo_retire_formes_juridiques_et_accents():
    assert cle_labo("Laboratoires Pierre Fabre S.A.") == "PIERRE FABRE"
    assert cle_labo("BIOGARAN SAS") == cle_labo("Biogaran")


@pytest.mark.parametrize("numero, valide", [
    ("10002764529", True), ("10003061412", True),          # RPPS réels publiés
    ("10000000000", False), ("10002764528", False),        # placeholder ; dernier chiffre faux
    ("552082273", True), ("552082274", False),             # SIREN (même clé de Luhn)
])
def test_luhn(numero, valide):
    assert luhn(numero) is valide


def test_montant_fr():
    s = montant_fr(pd.Series(["8.739.219,66", "12,5", "0", "", None, "abc"]))
    assert s.iloc[0] == pytest.approx(8739219.66) and s.iloc[1] == 12.5 and s.iloc[2] == 0
    assert s.iloc[3:].isna().all()


@pytest.mark.parametrize("brut, attendu", [
    ("PEYRIN-BIROULET", "PEYRIN BIROULET"), ("Peyrin  Biroulet", "PEYRIN BIROULET"),
    ("Gonçalves", "GONCALVES"), ("D'Artagnan", "D ARTAGNAN"), (None, ""), ("  ", ""),
])
def test_nn_normalise_les_noms(sql, brut, attendu):
    assert sql("SELECT nn(?)", brut) == attendu


@pytest.mark.parametrize("brut, attendu", [
    ("33", "33"), ("974", "974"),      # lpad('974', 2) donnait '97' : l'outre-mer disparaissait
    ("2A", "2A"), ("2b", "2B"), ("1", "01"), ("", None), (None, None), (" 6", "06"),
])
def test_dep_norm(sql, brut, attendu):
    assert sql("SELECT dep_norm(?)", brut) == attendu


@pytest.mark.parametrize("cp, dep", [("33000", "33"), ("97400", "974"), ("20000", "20"), ("1000", None), (None, None)])
def test_dep_depuis_code_postal(sql, cp, dep):
    assert sql("SELECT dep(?)", cp) == dep


def test_chiffres(sql):
    assert sql("SELECT chiffres(?)", "795 083 336") == "795083336"
    assert sql("SELECT chiffres(?)", "[SO]") == ""
    assert sql("SELECT chiffres(?)", None) == ""


def test_norm_structure_retire_mots_vides(sql):
    assert sql("SELECT norm(?)", "Association des Amis de l'Hôpital") == sql("SELECT norm(?)", "AMIS HOPITAL")
    assert sql("SELECT norm(?)", "SAS") is None


def test_sigle_et_parentheses(sql):
    assert sql("SELECT sigle(?)", "Association régionale (ARMDC)") == "ARMDC"
    assert sql("SELECT sans_parentheses(?)", "Association régionale (ARMDC)") == sql("SELECT norm(?)", "Association régionale")


def test_empreinte_ignore_ordre_des_candidats():
    a = {"cle_structure": "X|33", "candidats": [{"cle": "siren:1"}, {"cle": "rna:W2"}]}
    b = {"cle_structure": "X|33", "candidats": [{"cle": "rna:W2"}, {"cle": "siren:1"}]}
    assert empreinte(a) == empreinte(b)
    assert empreinte(a) != empreinte({**a, "cle_structure": "X|34"})
    assert cle_structure("X", None) == "X|"
