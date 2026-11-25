"""Un test par défaut déjà corrigé : la chaîne tourne sur le mini jeu fictif (tests/donnees_test.py) et doit donner
le résultat attendu. Si un ancien bug revient, un de ces tests échoue. Aucune donnée réelle n'est nécessaire."""
import os, pathlib, subprocess, sys
import pandas as pd, pytest
import donnees_test as D

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
ORDRE = ["24_professionnels_elus.py", "35_elus_declarations.py", "27_experts_has.py", "34_prestataires.py",
         "11_croisement_personnes.py", "33_anomalies.py"]


@pytest.fixture(scope="session")
def out(tmp_path_factory):
    racine = D.construire(tmp_path_factory.mktemp("racine"))
    env = {**os.environ, "SUIVRE_RACINE": str(racine), "SUIVRE_MEMBRES_HAS": str(racine / "membres_has.csv")}
    for s in ORDRE:
        r = subprocess.run([sys.executable, s], cwd=SCRIPTS, env=env, capture_output=True, text=True)
        assert r.returncode == 0, f"{s} plante :\n{r.stderr[-2000:]}"
    lire = lambda f: pd.read_csv(racine / "out" / f, dtype={"rpps": str, "dep": str, "departement": str, "siren": str})
    return lire


def test_double_compte_convention_remuneration(out):
    top = out("professionnels_top.csv")
    dupont = top[top.rpps == D.R_DUPONT].iloc[0]
    # 1 000 (convention exécutée, comptée une fois) + 2 x 150 + 30 000 ; la ligne sans montant ne compte pas
    assert dupont.euros == 31_300


def test_nom_affiche_le_plus_frequent(out):
    dupont = out("professionnels_top.csv").query("rpps == @D.R_DUPONT").iloc[0]
    assert dupont.nom == "DUPONT" and dupont.noms_declares == 2


def test_labo_principal_jamais_une_ligne_sans_montant(out):
    dupont = out("professionnels_top.csv").query("rpps == @D.R_DUPONT").iloc[0]
    assert dupont.principal_labo == "LABO BETA"     # 30 300 € contre 1 000 € pour ALPHA ; ZETA n'a qu'un montant vide


def test_identifiant_factice_ne_fusionne_pas(out):
    top = out("professionnels_top.csv")
    assert set(top[top.nom.isin(["MARTIN", "BERNARD"])].euros) == {500, 700}
    assert not (top.euros == 1200).any()


def test_elu_sans_departement_jamais_rapproche(out):
    assert "SANSDEP" not in set(out("elus_beneficiaires.csv").nom)


def test_elu_outre_mer_retrouve(out):
    e = out("elus_beneficiaires.csv")
    assert list(e[e.nom == "OUTREMER"].departement) == ["974"]


def test_elu_sans_doublon_malgre_la_casse(out):
    e = out("elus_beneficiaires.csv")
    d = e[e.nom == "DURAND"]
    assert len(d) == 1 and d.euros.iloc[0] == 1300


def test_declaration_invitation_exclue_et_homonyme_ecarte(out):
    r = out("elus_declarations_vs_versements.csv")
    d = r[r.nom == "DURAND"].iloc[0]
    assert d.contrats_5_ans_avant_declaration == 800              # l'invitation à un congrès (500 €) n'est pas un contrat
    assert d.labo_cite_dans_declaration == False                   # le texte d'un homonyme (né en 1980) n'est pas lu
    assert d.declarations_publiees == 1


def test_declaration_labo_cite(out):
    o = out("elus_declarations_vs_versements.csv").query("nom == 'OUTREMER'").iloc[0]
    assert o.groupe_labo == "BETA" and o.labo_cite_dans_declaration == True and o.contrats_5_ans_avant_declaration == 900


def test_expert_un_seul_rpps(out):
    e = out("experts_has_versements.csv")
    c = e[e.nom == "Testexpert"].iloc[0]
    assert c.qualite == "sûre" and c.total_recu == 400 and c.rpps == D.R_EXPERT_33   # pas 400 + 900


def test_expert_homonyme_sans_total(out):
    h = out("experts_has_versements.csv").query("nom == 'Homonyme'").iloc[0]
    assert h.qualite == "homonyme possible" and pd.isna(h.total_recu)


def test_prestataires(out):
    p = out("prestataires.csv")
    classes = dict(zip(p.beneficiaire, p.type_prestataire))
    assert classes.get("IQVIA RDS FRANCE") == "recherche sous contrat (CRO)"
    assert "ASSO RECHERCHE TEST" not in classes            # association de recherche : bénéficiaire
    assert "AMBASSADE TEST" not in classes                 # État étranger (3210) : pas une société
    assert "CABINET CONSEIL INNOCENT" not in classes       # un SIREN à 10 chiffres n'est pas tronqué sur un autre


def test_dirigeant_prenom_exact_et_montant_net(out):
    d = out("croisement_dirigeants_professionnels.csv")
    assert len(d) == 1
    assert d.recu_personnellement.iloc[0] == 3000           # convention + rémunération liée = 3 000, et pas JEANNE
    assert d.verse_a_la_structure.iloc[0] == 5000


def test_anomalies(out):
    a = out("anomalies_declarations.csv")
    assert (a.montant == 444_947_450).any()
    assert ((a.montant == 30_000) & a.anomalie.str.startswith("hospitalité")).any()
