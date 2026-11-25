"""Fonctions partagées : connexion DuckDB, normalisation des noms, empreinte des cas d'arbitrage."""
import duckdb, hashlib, json, pathlib
RACINE = pathlib.Path(__file__).resolve().parent.parent
DB = RACINE / "data" / "travail.duckdb"
for _d in ["data/raw", "data/ref", "data/ext", "data/tmp", "data/arbitrage", "data/test_verite", "out"]:
    (RACINE / _d).mkdir(parents=True, exist_ok=True)

# Catégories Transparence Santé qui désignent souvent une personne physique : jamais « fiable » par le nom seul.
PERSONNES = ("Etudiant", "Influenceur", "Vétérinaire")


def sql_chemin(p):
    """Chemin prêt à être inséré entre apostrophes dans du SQL DuckDB."""
    return pathlib.Path(p).as_posix().replace("'", "''")

# Mots qui ne distinguent pas une structure d'une autre (formes juridiques, articles, mots outils).
MOTS_VIDES = ["SAS","SASU","SARL","SA","EURL","SELARL","SELAS","SCM","SCI","SCP","GIE","SNC","SEL",
              "ASSOCIATION","ASSOC","ASSO","STE","CEDEX","LE","LA","LES","L","DE","DU","DES","D","ET","EN","AU","AUX","POUR","SUR","PAR","A"]

def connexion():
    con = duckdb.connect(str(DB))
    con.execute("SET memory_limit='8GB'; SET preserve_insertion_order=false;")
    con.execute(f"SET temp_directory='{sql_chemin(RACINE/'data'/'tmp')}'")
    mots = "|".join(MOTS_VIDES)
    # norm(nom) : majuscules, sans accents, sans ponctuation, sans mots vides, espaces simples.
    con.execute(f"""CREATE OR REPLACE MACRO norm(s) AS
      nullif(trim(regexp_replace(regexp_replace(
        regexp_replace(upper(strip_accents(coalesce(s,''))), '[^A-Z0-9]+', ' ', 'g'),
        '\\b({mots})\\b', ' ', 'g'), '\\s+', ' ', 'g')), '')""")
    # dep(cp) : département à partir d'un code postal (gère la Corse et l'outre-mer de façon simple).
    con.execute("""CREATE OR REPLACE MACRO dep(cp) AS CASE
      WHEN regexp_matches(coalesce(cp,''), '^97[0-9]') THEN substr(cp,1,3)
      WHEN regexp_matches(coalesce(cp,''), '^20[0-9]') THEN '20'
      WHEN regexp_matches(coalesce(cp,''), '^[0-9]{5}') THEN substr(cp,1,2)
      ELSE NULL END""")
    # sigle(s) : texte entre parenthèses, ex. "Association ... (ARMDC)" -> ARMDC
    con.execute("CREATE OR REPLACE MACRO sigle(s) AS norm(regexp_extract(coalesce(s,''), '\\(([^)]{2,40})\\)', 1))")
    con.execute("CREATE OR REPLACE MACRO sans_parentheses(s) AS norm(regexp_replace(coalesce(s,''), '\\([^)]*\\)', ' ', 'g'))")
    return con

# Identité stable d'une structure : nom normalisé + département (la clé de regroupement de l'étape 1).
# Le numéro struct_id, lui, est un rang en euros qui change à chaque mise à jour : les lots d'arbitrage portent
# donc `cle_structure`, et l'intégration (08) retrouve la structure par cette clé, jamais par le numéro seul.
def cle_structure(nom_norm, dep):
    return f"{nom_norm}|{dep or ''}"


# Empreinte d'un cas d'arbitrage : identité de la structure + liste triée des candidats.
# Si elle ne change pas, la décision déjà prise reste valable et on ne redemande rien à l'IA (figeage).
# L'ordre d'affichage des variantes de nom n'y entre pas : il ne change pas la question posée.
def empreinte(cas):
    cle = [cas.get("cle_structure"), sorted(c["cle"] for c in cas.get("candidats", []))]
    return hashlib.sha1(json.dumps(cle, ensure_ascii=False).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------------------------------------------
# Transparence Santé complète (scripts 21 à 32) : une vue brute et une vue NETTE sans double compte.
#
# Une convention (contrat d'orateur, d'étude…) est déclarée avec son montant, puis les rémunérations et avantages
# qui l'exécutent sont déclarés à part avec `convention_liee` = identifiant_unique de la convention. Additionner
# les trois compte deux fois le même argent (6,4 Md€ de conventions sont ainsi liées). La vue `ts_net` garde les
# rémunérations, les avantages, et seulement les conventions auxquelles aucun versement n'est rattaché.
# ---------------------------------------------------------------------------------------------------------------
TS_ANNEES = RACINE / "data/ext/ts_annees"
LIEES = RACINE / "data/ext/conventions_liees.parquet"


def vues_ts(con):
    """Crée les vues `ts` (toutes les déclarations) et `ts_net` (sans double compte) sur une connexion DuckDB."""
    con.execute(f"CREATE OR REPLACE VIEW ts AS SELECT * FROM read_parquet('{sql_chemin(TS_ANNEES)}/*.parquet', union_by_name=true)")
    if not LIEES.exists():
        con.execute(f"""COPY (SELECT DISTINCT entreprise_id, convention_liee AS identifiant_unique FROM ts
                         WHERE convention_liee IS NOT NULL AND lien_interet <> 'convention') TO '{sql_chemin(LIEES)}'""")
    con.execute(f"""CREATE OR REPLACE VIEW ts_net AS SELECT t.* FROM ts t
      ANTI JOIN read_parquet('{sql_chemin(LIEES)}') l
        ON t.lien_interet = 'convention' AND l.entreprise_id = t.entreprise_id AND l.identifiant_unique = t.identifiant_unique""")
    vue_professionnels(con)
    return con


# ---------------------------------------------------------------------------------------------------------------
# Identité d'un professionnel de santé. Le champ identifiant contient aussi des valeurs factices ([SO], 0, NA,
# 00000000000...) partagées par des milliers de personnes : s'en servir comme clé fusionnait ces personnes en une.
# Un RPPS n'est retenu que s'il a 11 chiffres, commence par 10, respecte la clé de Luhn et ne porte pas plus de
# 5 noms de famille différents ; sinon la personne est identifiée par nom + premier prénom + département normalisés.
# ---------------------------------------------------------------------------------------------------------------
RPPS_VALIDES = RACINE / "data/ext/rpps_valides.parquet"
MACROS = """
CREATE OR REPLACE MACRO nn(x) AS regexp_replace(trim(regexp_replace(upper(strip_accents(coalesce(x, ''))), '[^A-Z ]', ' ', 'g')), ' +', ' ', 'g');
CREATE OR REPLACE MACRO dep_norm(x) AS CASE WHEN trim(x) ~ '^[0-9]$' THEN '0' || trim(x) WHEN trim(x) = '' THEN NULL ELSE upper(trim(x)) END;
CREATE OR REPLACE MACRO chiffres(x) AS regexp_replace(coalesce(x, ''), '[^0-9]', '', 'g');
"""


def luhn(s):
    t = 0
    for k, c in enumerate(reversed(s)):
        v = int(c) * (2 if k % 2 else 1)
        t += v - 9 if v > 9 else v
    return t % 10 == 0


def vue_professionnels(con):
    """Vue `prs` : lignes nettes vers des professionnels de santé, avec rpps (valide ou NULL), nom_n, prenom_n,
    dep et la clé `personne`."""
    con.execute(MACROS)
    if not RPPS_VALIDES.exists():
        d = con.execute("""SELECT chiffres(beneficiaire_identifiant) rpps, count(DISTINCT regexp_replace(nn(identite), ' ', '', 'g')) noms
          FROM ts_net WHERE beneficiaire_categorie_code = 'PRS' AND chiffres(beneficiaire_identifiant) ~ '^10[0-9]{9}$' GROUP BY 1""").df()
        d = d[d.rpps.map(luhn) & (d.noms <= 5)][["rpps"]].sort_values("rpps")
        con.register("_rv", d)
        con.execute(f"COPY _rv TO '{sql_chemin(RPPS_VALIDES)}'")
        con.unregister("_rv")
    con.execute(f"""CREATE OR REPLACE VIEW prs AS
      SELECT t.*, v.rpps, nn(t.identite) nom_n, split_part(nn(t.prenom), ' ', 1) prenom_n, dep_norm(t.dep_code) dep,
             coalesce(v.rpps, nn(t.identite) || '|' || split_part(nn(t.prenom), ' ', 1) || '|' || coalesce(dep_norm(t.dep_code), '')) personne
      FROM ts_net t LEFT JOIN read_parquet('{sql_chemin(RPPS_VALIDES)}') v ON v.rpps = chiffres(t.beneficiaire_identifiant)
      WHERE t.beneficiaire_categorie_code = 'PRS'""")


# ---------------------------------------------------------------------------------------------------------------
# Groupes de laboratoires : une seule définition pour tous les scripts.
# Un labo déclare sous plusieurs entités (Lilly France, Eli Lilly and Company…) : le groupe est le premier mot
# significatif du nom, avec des alias pour les cas connus. Limite assumée : Merck KGaA et MSD (Merck Sharp & Dohme)
# sont distingués, mais un nom « MERCK » seul va chez Merck KGaA.
# ---------------------------------------------------------------------------------------------------------------
import re as _re
from unidecode import unidecode as _unidecode

STOP_LABO = (r"\b(SAS|SASU|SA|SARL|SNC|SE|GMBH|AG|BV|NV|LTD|LIMITED|INC|SPA|SL|PLC|FRANCE|FRANCAISE|LABORATOIRES?|LABS?"
             r"|PHARMA(CEUTICALS?|CEUTIQUE|CEUTIQUES)?|HEALTHCARE|SANTE|GROUPE?|EUROPE|INTERNATIONAL|HOLDING|DEUTSCHLAND"
             r"|IRELAND|BELGIUM|THE|ET|DE|DU|DES|LA|LE|LES|AND|CO|COMPANY|S|A|L)\b")
ALIAS_GROUPE = {"ELI": "LILLY", "GLAXO": "GLAXOSMITHKLINE", "GSK": "GLAXOSMITHKLINE", "JANSSEN": "JOHNSON", "JNJ": "JOHNSON",
                "BMS": "BRISTOL", "HOFFMANN": "ROCHE", "WINTHROP": "SANOFI", "AVENTIS": "SANOFI", "MYLAN": "VIATRIS"}


def cle_labo(x):
    """Nom de labo normalisé : majuscules, sans accents ni ponctuation, sans formes juridiques ni mots vides."""
    t = _re.sub(r"[^A-Z0-9 ]", " ", _unidecode(str(x or "")).upper())
    return " ".join(_re.sub(STOP_LABO, " ", t).split())


def groupe_labo(x):
    k = cle_labo(x).split()
    if not k:
        return None
    if k[0] == "MSD" or (k[0] == "MERCK" and k[1:2] == ["SHARP"]):
        return "MSD"
    return ALIAS_GROUPE.get(k[0], k[0])


# ---------------------------------------------------------------------------------------------------------------
# Lecture des fichiers BDPM (latin1, tabulés, sans en-tête) et Open Medic (montants « 8.739.219,66 »).
# ---------------------------------------------------------------------------------------------------------------
def lire_bdpm(nom, colonnes):
    """colonnes : {numéro de colonne: nom}. Ex. lire_bdpm("CIS_CIP_bdpm", {0: "cis", 6: "cip13"})."""
    import pandas as pd
    df = pd.read_csv(RACINE / f"data/ext/bdpm/{nom}.txt", sep="\t", header=None, encoding="latin1", dtype=str, quoting=3)
    return df[list(colonnes)].set_axis(list(colonnes.values()), axis=1)


def montant_fr(s):
    import pandas as pd
    return pd.to_numeric(s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")


def lire_openmedic(nom="NB_2025_cip13.CSV.gz"):
    import pandas as pd
    f = RACINE / "data/ext/openmedic" / nom
    if not f.exists():
        raise SystemExit(f"{f} manquant. Open Medic se télécharge à la main : voir README, section Données.")
    return pd.read_csv(f, sep=";", encoding="latin1", dtype=str)


def vue_lignes_net(con):
    """Sur la base de travail : vue temporaire `lignes_net`, les lignes « AUTRE » (structures) sans les conventions
    déjà comptées par les versements qui les exécutent (même règle que `ts_net`)."""
    vues_ts(con)
    con.execute("CREATE OR REPLACE TEMP VIEW lignes_net AS SELECT l.* FROM lignes l SEMI JOIN ts_net t ON t.id = l.id")
    return con
