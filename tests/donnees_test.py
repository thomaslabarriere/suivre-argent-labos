"""Mini jeu de données fictif qui reproduit chaque piège rencontré dans les vraies données.

Tous les noms sont inventés. Chaque bloc porte le défaut qu'il reproduit ; tests/test_regressions.py vérifie
que la chaîne donne le bon résultat sur chacun."""
import pathlib, duckdb, pandas as pd


def rpps(n):
    """RPPS fictif valide : 10 + 8 chiffres + clé de Luhn."""
    base = f"10{n:08d}"
    for c in "0123456789":
        s = base + c
        t = sum((int(d) * (2 if k % 2 else 1)) - (9 if int(d) * (2 if k % 2 else 1) > 9 else 0) for k, d in enumerate(reversed(s)))
        if t % 10 == 0:
            return s


R_DUPONT, R_OUTREMER, R_EXPERT_33, R_EXPERT_13, R_HOMO_13, R_HOMO_75 = (rpps(i) for i in (11, 22, 33, 44, 55, 66))
COLS = ["id", "entreprise_id", "raison_sociale", "lien_interet", "identifiant_unique", "convention_liee", "motif_lien_interet",
        "autre_motif", "information_evenement", "montant", "date", "date_debut", "identite", "prenom",
        "beneficiaire_categorie_code", "beneficiaire_categorie", "beneficiaire_type_code", "beneficiaire_identifiant",
        "profession_libelle", "dep_code", "ville", "numero_siren"]
L = []
def ligne(labo, lien, montant, nom, prenom=None, ident=None, dep=None, cat="PRS", type_id="RPPS/ADELI", date="2025-03-10",
          ident_unique=None, liee=None, motif=None, prof="Médecin", ville="BORDEAUX", info=None):
    L.append([f"T{len(L)+1}", "E-" + labo, labo, lien, ident_unique, liee, motif, None, info, montant,
              pd.Timestamp(date, tz="UTC"), pd.Timestamp(date).date(), nom, prenom, cat,
              {"PRS": "Professionnel de santé", "FON": "Académie, fondation, société savante, organisme de conseils",
               "ETA": "Etablissement de santé"}[cat], type_id, ident, prof if cat == "PRS" else None, dep, ville, None])

# 1. Double compte : une convention et la rémunération qui l'exécute ne font qu'un seul paiement de 1 000 €.
ligne("LABO ALPHA SAS", "convention", 1000, "DUPONT", "Jean", R_DUPONT, "33", ident_unique="C-1", motif="Contrat d'orateur")
ligne("LABO ALPHA SAS", "remuneration", 1000, "DUPONT", "Jean", R_DUPONT, "33", liee="C-1")
# 2. Labo principal : une ligne au montant vide (LABO ZETA) ne doit jamais être choisie.
ligne("LABO BETA", "avantage", 150, "DUPONT", "Jean", R_DUPONT, "33", motif="Repas")
ligne("LABO BETA", "avantage", 150, "Dupont", "JEAN", R_DUPONT, "33", motif="Repas")
# 3. Un RPPS porte une ligne au nom d'une autre personne : le nom affiché reste DUPONT.
ligne("LABO ZETA", "avantage", None, "AUTRENOM", "Paul", R_DUPONT, "33", motif="Repas")
# 4. Identifiant factice partagé par deux personnes : elles restent deux personnes.
ligne("LABO ALPHA SAS", "avantage", 500, "MARTIN", "Paul", "[SO]", "33", motif="Repas")
ligne("LABO ALPHA SAS", "avantage", 700, "BERNARD", "Luc", "[SO]", "75", motif="Repas")
# 5. Élus : un déclarant HATVP sans département ne doit jamais être rapproché.
ligne("LABO ALPHA SAS", "avantage", 200, "SANSDEP", "Marc", None, None, motif="Repas")
# 6. Élue d'outre-mer (974) : doit être retrouvée ; son labo BETA est cité dans sa déclaration.
ligne("LABO BETA", "remuneration", 900, "OUTREMER", "Léa", R_OUTREMER, "974", date="2024-06-01")
# 7. Même personne sans RPPS, casse différente : une seule ligne d'élue. Une invitation à un congrès n'est pas un
#    contrat à déclarer (seuls les 800 € de rémunération comptent).
ligne("LABO GAMMA", "remuneration", 800, "DURAND", "Anne", None, "69", date="2024-03-01")
ligne("LABO GAMMA", "convention", 500, "Durand", "anne", None, "69", date="2024-04-01", ident_unique="C-7",
      motif="Contrat de participation à une manifestation")
# 8. Experts HAS : deux RPPS homonymes ne s'additionnent jamais.
ligne("LABO ALPHA SAS", "avantage", 200, "TESTEXPERT", "Claire", R_EXPERT_33, "33", motif="Repas")
ligne("LABO ALPHA SAS", "avantage", 200, "TESTEXPERT", "Claire", R_EXPERT_33, "33", motif="Repas")
ligne("LABO BETA", "remuneration", 450, "TESTEXPERT", "Claire", R_EXPERT_13, "13")
ligne("LABO BETA", "remuneration", 450, "TESTEXPERT", "Claire", R_EXPERT_13, "13")
#    ... et aucun total n'est publié quand aucun groupe ne concorde avec la page HAS.
ligne("LABO BETA", "avantage", 300, "HOMONYME", "Paul", R_HOMO_13, "13", motif="Repas")
ligne("LABO BETA", "avantage", 300, "HOMONYME", "Paul", R_HOMO_75, "75", motif="Repas")
# 9. Anomalies : une ligne géante, un hébergement invraisemblable.
ligne("CRO TEST", "convention", 444_947_450, "CENTRE TEST", None, "111111111", None, cat="ETA", type_id="FINESS", ident_unique="C-9")
ligne("LABO BETA", "avantage", 30_000, "DUPONT", "Jean", R_DUPONT, "33", motif="Hospitalité - hébergement")
# 10. Prestataires (structures avec SIREN).
ligne("LABO ALPHA SAS", "remuneration", 10_000, "IQVIA RDS FRANCE", None, "400892105", None, cat="FON", type_id="SIREN")
ligne("LABO ALPHA SAS", "remuneration", 4_000, "ASSO RECHERCHE TEST", None, "222222222", None, cat="FON", type_id="SIREN")
ligne("LABO ALPHA SAS", "remuneration", 3_000, "AMBASSADE TEST", None, "333333333", None, cat="FON", type_id="SIREN")
ligne("LABO ALPHA SAS", "remuneration", 2_000, "SOCIETE MAL SAISIE", None, "1234567890", None, cat="FON", type_id="SIREN")
# 11. Dirigeant payé à titre personnel : JEAN ne doit pas attraper JEANNE ; montants nets.
ligne("LABO DELTA", "convention", 3000, "TESTDIR", "Jean", rpps(77), "33", ident_unique="C-11", motif="Contrat d'expert")
ligne("LABO DELTA", "remuneration", 3000, "TESTDIR", "Jean", rpps(77), "33", liee="C-11")
ligne("LABO DELTA", "avantage", 999, "TESTDIR", "Jeanne", rpps(88), "33", motif="Repas")
ligne("LABO DELTA", "remuneration", 5000, "SOCIETE DIRIGEE TEST", None, None, "33", cat="FON", type_id="AUTRE")

DECLARATIONS = """<?xml version="1.0" encoding="UTF-8"?><declarations>
<declaration><dateDepot>15/01/2025 10:00:00</dateDepot><general><typeDeclaration><id>DI</id></typeDeclaration>
 <qualiteDeclarantForPDF>Conseillère municipale/Rhône(69)</qualiteDeclarantForPDF>
 <declarant><nom>DURAND</nom><prenom>Anne</prenom><dateNaissance>01/01/1970</dateNaissance></declarant></general>
 <activProfCinqDerniereDto><items><motif>CREATION</motif><description>Médecin libéral</description></items></activProfCinqDerniereDto>
 <activConsultantDto><items/><neant>true</neant></activConsultantDto></declaration>
<declaration><dateDepot>01/02/2025 10:00:00</dateDepot><general><typeDeclaration><id>DI</id></typeDeclaration>
 <qualiteDeclarantForPDF>Membre de cabinet</qualiteDeclarantForPDF>
 <declarant><nom>DURAND</nom><prenom>Anne</prenom><dateNaissance>02/02/1980</dateNaissance></declarant></general>
 <activConsultantDto><items><motif>CREATION</motif><description>Conseil pour LABO GAMMA</description></items></activConsultantDto></declaration>
<declaration><dateDepot>01/09/2024 10:00:00</dateDepot><general><typeDeclaration><id>DI</id></typeDeclaration>
 <qualiteDeclarantForPDF>Conseillère départementale/La Réunion(974)</qualiteDeclarantForPDF>
 <declarant><nom>OUTREMER</nom><prenom>Léa</prenom><dateNaissance>03/03/1975</dateNaissance></declarant></general>
 <activConsultantDto><items><motif>CREATION</motif><description>Expertise pour LABO BETA</description></items></activConsultantDto></declaration>
</declarations>"""


def construire(racine):
    racine = pathlib.Path(racine)
    for d in ["data/ext/ts_annees", "data/ext/hatvp", "data/ext/has", "out"]:
        (racine / d).mkdir(parents=True, exist_ok=True)
    pd.DataFrame(L, columns=COLS).to_parquet(racine / "data/ext/ts_annees/2025.parquet", index=False)
    pd.DataFrame([dict(nom="SANSDEP", prenom="Marc", departement="", qualite="Adjoint au maire"),
                  dict(nom="OUTREMER", prenom="Léa", departement="974", qualite="Conseillère départementale de La Réunion"),
                  dict(nom="DURAND", prenom="Anne", departement="69", qualite="Conseillère municipale de Lyon")]) \
        .to_csv(racine / "data/ext/hatvp/liste_declarants.csv", sep=";", index=False)
    (racine / "data/ext/hatvp/declarations.xml").write_text(DECLARATIONS, encoding="utf-8")
    membres = pd.DataFrame([
        dict(commission="CT", prenom="Claire", nom="Testexpert", role="membre", specialite="cardiologie", dep_has="33",
             mandat_debut="2024-11-06", mandat_fin="2027-11-05", source_url="test"),
        dict(commission="CT", prenom="Paul", nom="Homonyme", role="membre", specialite="cardiologie", dep_has="59",
             mandat_debut="2024-11-06", mandat_fin="2027-11-05", source_url="test")])
    membres.to_csv(racine / "membres_has.csv", index=False)
    # base de travail minimale : lignes « AUTRE » rattachées, SIRENE, dirigeants
    ids = {r[12]: r[0] for r in L}
    con = duckdb.connect(str(racine / "data/travail.duckdb"))
    con.execute("CREATE TABLE ref_ul (siren VARCHAR, denomination VARCHAR, ape VARCHAR, cat_juridique BIGINT)")
    con.execute("""INSERT INTO ref_ul VALUES ('400892105', 'IQVIA RDS FRANCE', '74.90B', 5710), ('222222222', 'ASSO RECHERCHE TEST', '72.19Z', 9220),
      ('333333333', 'AMBASSADE TEST', '70.22Z', 3210), ('123456789', 'CABINET CONSEIL INNOCENT', '70.22Z', 5710),
      ('444444444', 'SOCIETE DIRIGEE TEST', '70.22Z', 5710)""")
    con.execute("CREATE TABLE lignes (id VARCHAR, struct_id INTEGER, raison_sociale VARCHAR, montant DOUBLE, lien_interet VARCHAR, siren_declarant VARCHAR)")
    con.execute("INSERT INTO lignes VALUES (?, 1, 'LABO DELTA', 5000, 'remuneration', NULL)", [ids["SOCIETE DIRIGEE TEST"]])
    con.execute("""CREATE TABLE final2 AS SELECT 1 struct_id, '444444444' identifiant2, 'fiable' statut2, 'SOCIETE DIRIGEE TEST' nom_officiel,
      '33' dep, 'SOCIETE DIRIGEE TEST' nom_declare, 'Académie, fondation, société savante, organisme de conseils' categorie""")
    con.execute("""CREATE TABLE dirigeants AS SELECT '444444444' siren, 'personne physique' type_dirigeant, 'TESTDIR' nom, 'JEAN' prenoms,
      NULL denomination, NULL siren_dirigeant, 'Président' qualite""")
    con.execute("""CREATE TABLE croisement_groupe (siren_beneficiaire VARCHAR, nom_beneficiaire VARCHAR, dirigeant VARCHAR,
      siren_dirigeant VARCHAR, laboratoire VARCHAR, montant_du_labo DOUBLE)""")
    con.close()
    return racine
