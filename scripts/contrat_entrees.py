"""Contrat sur les données d'entrée : détecter qu'une source a changé AVANT qu'elle ne fausse les chiffres.

Compare les fichiers téléchargés à une référence versionnée (tests/reference_entrees.json) :
- un fichier attendu manque, ou une colonne disparaît / change de type          -> échec ;
- le nombre de lignes baisse de plus de 3 % (export tronqué, comme vécu)         -> échec ;
- une valeur inconnue apparaît (ou disparaît) dans un champ codé : type de lien, catégorie ou type d'identifiant
  de bénéficiaire (une nouvelle catégorie serait ignorée en silence par les filtres) -> échec ;
- une année manque dans Transparence Santé                                       -> échec ;
- une colonne nouvelle apparaît                                                  -> signalé, sans échec.
Usage : .venv/bin/python scripts/contrat_entrees.py [--maj]   (--maj réécrit la référence après vérification humaine)"""
import glob, gzip, json, pathlib, sys
import duckdb
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from commun import RACINE, sql_chemin

REF = pathlib.Path(__file__).resolve().parent.parent / "tests/reference_entrees.json"
CODES = ["lien_interet", "beneficiaire_categorie_code", "beneficiaire_type_code"]
con = duckdb.connect()


def colonnes_parquet(f):
    return {r[0]: r[1] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{sql_chemin(f)}')").fetchall()}


def lignes_parquet(f):
    return con.execute(f"SELECT sum(num_rows) FROM parquet_file_metadata('{sql_chemin(f)}')").fetchone()[0]


def entete(f, sep, encodage="utf-8"):
    ouvrir = gzip.open if str(f).endswith(".gz") else open
    with ouvrir(f, "rt", encoding=encodage, errors="replace") as h:
        return {c.strip().strip('"'): "texte" for c in h.readline().rstrip("\n\r").split(sep)}


def un(motif):
    f = sorted(glob.glob(str(RACINE / motif)))
    return f[-1] if f else None


def mesurer():
    m = {}
    ts = sorted(glob.glob(str(RACINE / "data/ext/ts_annees/ts_*.parquet")))
    for f in ts:
        m["ts " + pathlib.Path(f).stem] = {"colonnes": colonnes_parquet(f), "lignes": lignes_parquet(f)}
    if ts:
        liste = "[" + ",".join(f"'{sql_chemin(f)}'" for f in ts) + "]"
        m["ts codes"] = {"valeurs": {c: sorted(x[0] for x in con.execute(
            f"SELECT DISTINCT {c} FROM read_parquet({liste}, union_by_name=true) WHERE {c} IS NOT NULL").fetchall()) for c in CODES}}
    for nom, motif in [("ts_autre", "data/raw/ts_autre_structures.parquet"), ("sirene_ul", "data/ref/sirene_ul.parquet"),
                       ("sirene_etab", "data/ref/sirene_etab.parquet"), ("decp", "data/ext/decp/decp_marches.parquet")]:
        f = un(motif)
        m[nom] = {"colonnes": colonnes_parquet(f), "lignes": lignes_parquet(f)} if f else None
    rna = sorted(glob.glob(str(RACINE / "data/ref/rna/**/*.csv"), recursive=True))
    m["rna"] = {"colonnes": entete(rna[0], ";", "latin1"), "fichiers": len(rna)} if rna else None
    for nom, motif, sep, enc in [("openmedic", "data/ext/openmedic/NB_2025_cip13.CSV.gz", ";", "latin1"),
                                 ("openmedic specialites", "data/ext/openmedic/NB_2025_cip13_age_sexe_spe.CSV.gz", ";", "latin1"),
                                 ("rpps activite", "data/ext/rpps/PS_LibreAcces_Personne_activite_*.txt", "|", "utf-8"),
                                 ("rpps savoir-faire", "data/ext/rpps/PS_LibreAcces_SavoirFaire_*.txt", "|", "utf-8"),
                                 ("hatvp declarants", "data/ext/hatvp/liste_declarants.csv", ";", "utf-8")]:
        f = un(motif)
        m[nom] = {"colonnes": entete(f, sep, enc)} if f else None
    for f in sorted(glob.glob(str(RACINE / "data/ext/bdpm/*.txt"))):   # sans en-tête : nombre de colonnes
        with open(f, encoding="latin1") as h:
            m["bdpm " + pathlib.Path(f).stem] = {"colonnes": {f"c{i}": "texte" for i in range(len(h.readline().split("\t")))}}
    for nom, motif in [("hatvp declarations", "data/ext/hatvp/declarations.xml"), ("hatvp lobbies", "data/ext/hatvp/repertoire_lobbies.json"),
                       ("essais", "data/ext/essais/ctgov_fr.json")]:
        f = un(motif)
        m[nom] = {"octets": pathlib.Path(f).stat().st_size} if f else None
    return m


def verifier(m=None):
    """Liste de (nom du contrôle, réussi, détail)."""
    m = m or mesurer()
    if not REF.exists():
        return [("référence des entrées présente", False, f"{REF} absent : lancer contrat_entrees.py --maj")]
    ref, res = json.loads(REF.read_text()), []
    for nom, r in ref.items():
        a = m.get(nom)
        if r is None:
            continue
        if a is None:
            res.append((f"{nom} présent", False, "fichier manquant")); continue
        if "colonnes" in r:
            manq = sorted(set(r["colonnes"]) - set(a["colonnes"]))
            types = sorted(c for c in r["colonnes"] if c in a["colonnes"] and a["colonnes"][c] != r["colonnes"][c])
            nouv = sorted(set(a["colonnes"]) - set(r["colonnes"]))
            res.append((f"{nom} : colonnes", not manq and not types,
                        (f"manquantes {manq} " if manq else "") + (f"type changé {types} " if types else "") + (f"nouvelles {nouv}" if nouv else "")))
        for k in ("lignes", "octets", "fichiers"):
            if k in r:
                res.append((f"{nom} : {k}", a[k] >= 0.97 * r[k], f"{a[k]:,} contre {r[k]:,} en référence"))
        if "valeurs" in r:
            for c, v in r["valeurs"].items():
                nouv, disp = sorted(set(a["valeurs"][c]) - set(v)), sorted(set(v) - set(a["valeurs"][c]))
                res.append((f"ts : valeurs de {c}", not nouv and not disp, f"nouvelles {nouv} disparues {disp}" if nouv or disp else f"{len(v)} valeurs"))
    ans = sorted(int(k[-4:]) for k in m if k.startswith("ts ts_"))
    res.append(("ts : aucune année manquante", bool(ans) and ans == list(range(ans[0], ans[-1] + 1)), f"{ans[:1]} à {ans[-1:]}"))
    return res


if __name__ == "__main__":
    mesure = mesurer()
    if "--maj" in sys.argv:
        REF.write_text(json.dumps(mesure, ensure_ascii=False, indent=1, sort_keys=True)); print("référence écrite :", REF)
    res = verifier(mesure)
    for nom, ok, d in res:
        print(f"[{'ok' if ok else 'ÉCHEC'}] {nom} {d}")
    sys.exit(0 if all(r[1] for r in res) else 1)
