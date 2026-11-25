"""Étape 7 : dirigeants des structures fiables (sociétés inscrites au RNE, via recherche-entreprises.api.gouv.fr),
puis deux croisements :
  a) un dirigeant personne morale qui est lui-même un laboratoire déclarant (l'argent revient au groupe) ;
  b) un dirigeant personne physique qui reçoit aussi, à titre personnel, de l'argent du même laboratoire.
Les associations et hôpitaux n'ont pas de dirigeants dans les données ouvertes : on le signale, sans inventer."""
import json, sys, time, urllib.request, urllib.parse
import pandas as pd
from commun import connexion, RACINE, vue_lignes_net
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
con = vue_lignes_net(connexion())
cache_f = RACINE/"data"/"dirigeants_cache.json"
cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
def get(url, essais=5):
    for i in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "hackathon-transparence-sante"}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(2 + 2*i); continue
            if e.code >= 500: time.sleep(2); continue
            return None
        except Exception: time.sleep(2)
    return None

sirens = con.execute(f"""SELECT f.identifiant2 siren, sum(f.montant) m FROM final2 f JOIN ref_ul u ON u.siren=f.identifiant2
WHERE f.statut2='fiable' AND NOT (CAST(u.cat_juridique AS VARCHAR) LIKE '92%' OR CAST(u.cat_juridique AS VARCHAR) LIKE '7%')
GROUP BY 1 ORDER BY m DESC LIMIT {N}""").df().siren.tolist()
print("sociétés à interroger :", len(sirens), "; déjà en cache :", sum(s in cache for s in sirens))
for i, s in enumerate(sirens):
    if s in cache: continue
    d = get(f"https://recherche-entreprises.api.gouv.fr/search?q={s}&per_page=1")
    if d is None: continue                             # échec réseau ou API : on réessaiera au prochain passage, rien en cache
    res = [r for r in d.get("results", []) if r.get("siren") == s]
    cache[s] = res[0].get("dirigeants", []) if res else None
    time.sleep(0.16)                                   # ~6 requêtes/s, sous la limite publique de 7/s
    if i % 100 == 0: cache_f.write_text(json.dumps(cache, ensure_ascii=False)); print(" ", i, flush=True)
cache_f.write_text(json.dumps(cache, ensure_ascii=False))
# dans le JSON de l'API, le SIREN d'un dirigeant personne morale est dans le champ « siren » du dirigeant
rows = [{"siren": s, "type_dirigeant": d.get("type_dirigeant"), "nom": d.get("nom"), "prenoms": d.get("prenoms"),
         "denomination": d.get("denomination"), "siren_dirigeant": d.get("siren") if d.get("type_dirigeant")=="personne morale" else None,
         "qualite": d.get("qualite")} for s in sirens for d in (cache.get(s) or [])]
dir_ = pd.DataFrame(rows, columns=["siren","type_dirigeant","nom","prenoms","denomination","siren_dirigeant","qualite"])
con.register("dd", dir_)
con.execute("CREATE OR REPLACE TABLE dirigeants AS SELECT * FROM dd WHERE coalesce(qualite,'') NOT ILIKE '%commissaire aux comptes%'")
print(con.execute("SELECT type_dirigeant, count(*), count(DISTINCT siren) FROM dirigeants GROUP BY 1").fetchall())

# a) dirigeant personne morale = groupe d'un laboratoire déclarant de cette même structure
con.execute("""CREATE OR REPLACE TABLE croisement_groupe AS
SELECT f.identifiant2 AS siren_beneficiaire, min(f.nom_officiel) nom_beneficiaire, d.denomination AS dirigeant, d.siren_dirigeant,
  l.raison_sociale AS laboratoire, round(sum(l.montant)) AS montant_du_labo
FROM (SELECT DISTINCT siren, denomination, siren_dirigeant, type_dirigeant FROM dirigeants) d   -- un dirigeant aux qualités multiples ne double pas les montants
JOIN final2 f ON f.identifiant2=d.siren
JOIN lignes_net l ON l.struct_id=f.struct_id
WHERE d.type_dirigeant='personne morale' AND (l.siren_declarant=d.siren_dirigeant
   OR norm(l.raison_sociale)=norm(d.denomination))
GROUP BY ALL ORDER BY montant_du_labo DESC""")
print("\n== a) structure dirigée par le groupe d'un labo qui la paie")
print(con.execute("SELECT * FROM croisement_groupe LIMIT 20").df().to_string())
