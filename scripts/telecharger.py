"""Télécharge toutes les sources publiques utilisées par le projet, en résolvant les URL à jour.

Les fichiers de data.gouv.fr changent d'URL à chaque mise à jour (horodatage dans le chemin) : on interroge
l'API data.gouv (`/api/1/datasets/<slug>/`) et on prend la ressource la plus récente dont le titre correspond.
Un fichier déjà présent et non vide n'est pas retéléchargé (supprimez-le pour forcer).

Usage : python scripts/telecharger.py [--force] [base ...]   (--force : retélécharge même si le fichier existe)
  bases : ts_autre sirene rna  (chaîne de rattachement, ~6 Go)
          ts_annees bdpm hatvp rpps decp geo  (analyses 21 à 32, ~5 Go)
  sans argument : tout.
Open Medic n'est pas automatisable (lien à jeton généré par le site) : voir README, section Données.
Essais cliniques (29) et pages HAS (27) sont récupérés par leurs scripts.
"""
import json, pathlib, re, shutil, subprocess, sys, urllib.parse, urllib.request, zipfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
D = RACINE / "data"
UA = {"User-Agent": "transparence-sante-rattachement (projet open source)"}
TS_API = "https://www.transparence.sante.gouv.fr/api/explore/v2.1/catalog/datasets/declarations/exports/parquet"


def ressource(slug, motif):
    """URL de la ressource la plus récente du jeu `slug` dont le titre correspond à l'expression `motif`."""
    req = urllib.request.Request(f"https://www.data.gouv.fr/api/1/datasets/{slug}/", headers=UA)
    res = json.load(urllib.request.urlopen(req, timeout=60))["resources"]
    ok = [r for r in res if re.search(motif, r["title"], re.I)]
    if not ok:
        raise SystemExit(f"Aucune ressource « {motif} » dans {slug}")
    return max(ok, key=lambda r: r.get("last_modified") or r.get("created_at") or "")["url"]


FORCE = False


def dl(url, dest, verifier_parquet=False):
    dest = pathlib.Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    if FORCE and dest.exists():
        dest.unlink()
    if dest.exists() and dest.stat().st_size > 0 and (not verifier_parquet or parquet_complet(dest)):
        print(f"déjà là  {dest.relative_to(RACINE)}"); return dest
    part = dest.with_suffix(dest.suffix + ".part")
    for essai in range(1, 6):
        r = subprocess.run(["curl", "-fsSL", "-A", UA["User-Agent"], "--retry", "5", "--retry-all-errors",
                            "-C", "-", "-o", str(part), url])
        if r.returncode == 0 and (not verifier_parquet or parquet_complet(part)):
            part.rename(dest); print(f"ok       {dest.relative_to(RACINE)}"); return dest
        print(f"reprise {essai} de {dest.name}")
        if verifier_parquet: part.unlink(missing_ok=True)   # export tronqué : on repart de zéro
    raise SystemExit(f"ÉCHEC {url}")


def parquet_complet(p):
    """Le serveur Transparence Santé coupe parfois l'export : un parquet complet finit par les octets PAR1."""
    with open(p, "rb") as f:
        f.seek(-4, 2); return f.read() == b"PAR1"


def ts_export(where):
    return TS_API + "?where=" + urllib.parse.quote(where)


def ts_autre():
    dl(ts_export('beneficiaire_type="AUTRE" and beneficiaire_categorie_code!="PRS"'),
       D / "raw/ts_autre_structures.parquet", verifier_parquet=True)

def sirene():
    s = "base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret"
    dl(ressource(s, r"StockUniteLegale - .*parquet"), D / "ref/sirene_ul.parquet")
    dl(ressource(s, r"StockEtablissement - .*parquet"), D / "ref/sirene_etab.parquet")

def rna():
    z = dl(ressource("repertoire-national-des-associations", r"^rna_waldec_\d+\.zip$"), D / "ref/rna_waldec.zip")
    if FORCE or not (D / "ref/rna").exists():
        shutil.rmtree(D / "ref/rna", ignore_errors=True)
        zipfile.ZipFile(z).extractall(D / "ref/rna")

def ts_annees():
    # L'export complet (10,5 M lignes) est tronqué par le serveur : une requête par année.
    import datetime
    for a in range(2012, datetime.date.today().year + 1):
        dl(ts_export(f"year(date)={a}"), D / f"ext/ts_annees/ts_{a}.parquet", verifier_parquet=True)

def bdpm():
    b = "https://base-donnees-publique.medicaments.gouv.fr/download/file"
    for f in ["CIS_bdpm", "CIS_CIP_bdpm", "CIS_COMPO_bdpm", "CIS_HAS_SMR_bdpm", "CIS_HAS_ASMR_bdpm",
              "CIS_GENER_bdpm", "CIS_CPD_bdpm", "HAS_LiensPageCT_bdpm"]:
        dl(f"{b}/{f}.txt", D / f"ext/bdpm/{f}.txt")

def hatvp():
    dl("https://www.hatvp.fr/agora/opendata/agora_repertoire_opendata.json", D / "ext/hatvp/repertoire_lobbies.json")
    dl("https://www.hatvp.fr/livraison/opendata/liste.csv", D / "ext/hatvp/liste_declarants.csv")
    dl("https://www.hatvp.fr/livraison/merge/declarations.xml", D / "ext/hatvp/declarations.xml")

def rpps():
    s = "annuaire-sante-extractions-des-donnees-en-libre-acces-des-professionnels-intervenant-dans-le-systeme-de-sante-rpps"
    dl(ressource(s, r"personne-activite"), D / "ext/rpps/PS_LibreAcces_Personne_activite.txt")
    dl(ressource(s, r"savoirfaire"), D / "ext/rpps/PS_LibreAcces_SavoirFaire.txt")

def decp():
    dl(ressource("donnees-essentielles-de-la-commande-publique-fichiers-consolides", r"^decp-global\.json$"),
       D / "ext/decp/decp-global.json")

def geo():
    dl("https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements-version-simplifiee.geojson",
       D / "ext/geo/departements.geojson")


BASES = {f.__name__: f for f in [ts_autre, sirene, rna, ts_annees, bdpm, hatvp, rpps, decp, geo]}

if __name__ == "__main__":
    if not shutil.which("curl"):
        raise SystemExit("curl est requis")
    args = sys.argv[1:]
    if "--force" in args:
        FORCE = True; args.remove("--force")
    choix = args or list(BASES)
    inconnues = [c for c in choix if c not in BASES]
    if inconnues:
        raise SystemExit(f"Bases inconnues : {inconnues}. Choix : {', '.join(BASES)}")
    for c in choix:
        print(f"== {c}"); BASES[c]()
