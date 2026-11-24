"""Étape 7b : un dirigeant (personne physique) d'une structure payée par un labo reçoit-il AUSSI de l'argent
de ce même labo à titre personnel, comme professionnel de santé ? Interroge l'API Transparence Santé.
Attention : correspondance par nom + premier prénom, donc des homonymes sont possibles. Chaque cas est à vérifier."""
import json, time, urllib.request, urllib.parse, unicodedata
import pandas as pd
from commun import connexion, RACINE
con = connexion()
API = "https://www.transparence.sante.gouv.fr/api/explore/v2.1/catalog/datasets/declarations/records"
cache_f = RACINE/"data"/"personnes_cache_v2.json"   # v2 : la réponse inclut le département d'exercice
cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
def maj(x): x = x if isinstance(x, str) else ""; return unicodedata.normalize("NFKD", x).encode("ascii","ignore").decode().upper().strip()
def cle(r):
    pre = r.prenoms if isinstance(r.prenoms, str) else ""
    return maj(r.nom) + "|" + maj(pre.split(" ")[0].split(",")[0])
def q(nom, prenom):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')   # un guillemet dans un nom ne casse pas la requête
    where = f'identite="{esc(nom)}" and startswith(prenom,"{esc(prenom)}") and beneficiaire_categorie_code="PRS"'
    p = {"select": "raison_sociale, profession_libelle, dep_code, sum(montant) as m, count(*) as n", "group_by": "raison_sociale, profession_libelle, dep_code",
         "where": where, "limit": 200}
    for i in range(5):
        try:
            with urllib.request.urlopen(API+"?"+urllib.parse.urlencode(p), timeout=60) as r: return json.load(r)["results"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503): time.sleep(3+3*i); continue
            return None
        except Exception: time.sleep(3)
    return None
pers = con.execute("""SELECT DISTINCT d.siren, d.nom, d.prenoms FROM dirigeants d JOIN final2 f ON f.identifiant2=d.siren
WHERE d.type_dirigeant='personne physique' AND d.nom IS NOT NULL AND f.statut2='fiable'""").df()
print("personnes :", len(pers))
for i, r in enumerate(pers.itertuples()):
    k = cle(r); nom, pre = k.split("|")
    if not nom or not pre or k in cache: continue
    r_ = q(nom, pre); time.sleep(0.3)
    if r_ is None: continue                    # échec : pas de mise en cache, on réessaiera
    cache[k] = r_
    if i % 100 == 0: cache_f.write_text(json.dumps(cache, ensure_ascii=False)); print(" ", i, flush=True)
cache_f.write_text(json.dumps(cache, ensure_ascii=False))
rows = []
for r in pers.itertuples():
    for x in cache.get(cle(r)) or []:
        rows.append({"siren": r.siren, "nom": r.nom, "prenoms": r.prenoms, "labo_perso": x["raison_sociale"], "profession": x["profession_libelle"],
                     "dep_perso": x.get("dep_code"), "montant_perso": x["m"] or 0, "nb_perso": x["n"]})
pp = pd.DataFrame(rows, columns=["siren","nom","prenoms","labo_perso","profession","dep_perso","montant_perso","nb_perso"])
con.register("pp", pp)
# Labo regroupé par son nom normalisé sans formes juridiques (ROCHE = ROCHE SAS). Montants agrégés AVANT la jointure
# pour ne rien compter deux fois. dep_identique : la personne est payée dans le département de la structure (moins de risque d'homonyme).
con.execute("""CREATE OR REPLACE TABLE croisement_personnes AS
WITH perso AS (
  SELECT siren, nom, prenoms, norm(labo_perso) AS labo, string_agg(DISTINCT profession, ', ') AS profession,
         list(DISTINCT dep_perso) AS deps_perso, sum(montant_perso) AS recu_personnellement, sum(nb_perso) AS nb_versements_perso
  FROM pp GROUP BY 1,2,3,4),
struct AS (
  SELECT f.identifiant2 AS siren, any_value(f.nom_officiel) AS structure, any_value(f.dep) AS dep_structure,
         norm(l.raison_sociale) AS labo, any_value(l.raison_sociale) AS laboratoire, sum(l.montant) AS verse_a_la_structure
  FROM final2 f JOIN lignes l ON l.struct_id=f.struct_id WHERE f.statut2='fiable' GROUP BY f.identifiant2, norm(l.raison_sociale))
SELECT s.siren, s.structure, p.nom, p.prenoms, p.profession, s.laboratoire,
  round(p.recu_personnellement) AS recu_personnellement, p.nb_versements_perso, round(s.verse_a_la_structure) AS verse_a_la_structure,
  list_contains(p.deps_perso, s.dep_structure) AS dep_identique
FROM perso p JOIN struct s USING (siren, labo)
ORDER BY dep_identique DESC, verse_a_la_structure DESC""")
con.execute("""CREATE OR REPLACE TABLE croisement_groupe AS
SELECT siren_beneficiaire, any_value(f.nom_officiel) AS nom_beneficiaire, norm(laboratoire) AS labo, any_value(laboratoire) AS laboratoire,
  any_value(dirigeant) AS dirigeant, max(montant_du_labo) AS montant_du_labo
FROM croisement_groupe g LEFT JOIN final2 f ON f.identifiant2=g.siren_beneficiaire GROUP BY 1, 3 ORDER BY montant_du_labo DESC""")
print(con.execute("""SELECT count(*) lignes, count(DISTINCT siren) structures, count(DISTINCT nom||coalesce(prenoms,'')) personnes,
  count(*) FILTER (WHERE dep_identique) lignes_meme_dep, count(DISTINCT siren) FILTER (WHERE dep_identique) structures_meme_dep,
  count(DISTINCT siren) FILTER (WHERE dep_identique AND recu_personnellement>=5000) structures_meme_dep_5k FROM croisement_personnes""").df().to_string())
print(con.execute("SELECT count(*), count(DISTINCT siren_beneficiaire) FROM croisement_groupe").fetchone(), "lignes / structures dirigées par un labo payeur")
con.execute(f"COPY croisement_personnes TO '{RACINE}/out/croisement_dirigeants_professionnels.csv' (HEADER)")
con.execute(f"COPY croisement_groupe TO '{RACINE}/out/croisement_structures_dirigees_par_labo.csv' (HEADER)")
