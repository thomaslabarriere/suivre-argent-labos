"""Étape 5b : intègre les décisions des agents (decision_XX.jsonl, puis revision_XX.jsonl s'il y en a).
Contrôles : le choix doit être une clé proposée dans le lot ; un nom proposé n'est retenu que s'il existe
dans le registre (même département, ou nom unique en France). Produit la table final2.

Identité des cas : un lot et sa décision se répondent par (numéro de lot, id), puis le cas est retrouvé dans la
table `structures` actuelle par `cle_structure` (nom normalisé + département), jamais par le numéro struct_id seul,
qui change à chaque mise à jour des données. Une décision dont la structure a disparu est « orpheline »."""
import json, hashlib, datetime
from collections import Counter
import pandas as pd, re, unidecode
from rapidfuzz import fuzz
ABBR = {'SOC':'SOCIETE','FR':'FRANCAISE','ASSOC':'ASSOCIATION','ASSO':'ASSOCIATION','RECH':'RECHERCHE'}
def nrm(x):
    t = re.sub(r'[^A-Z0-9 ]+', ' ', unidecode.unidecode(str(x or '')).upper()).split()
    return ' '.join(ABBR.get(w, w) for w in t if w not in ('DE','DU','DES','LA','LE','LES','L','D','ET','EN','CONTRE'))
from commun import connexion, RACINE, empreinte, cle_structure, PERSONNES, sql_chemin
con = connexion()
actuel = {cle_structure(n, d): i for i, n, d in con.execute("SELECT struct_id, nom_norm, dep FROM structures").fetchall()}
A = RACINE/"data"/"arbitrage"
# Figeage (défaut 7) : un cas peut apparaître dans plusieurs lots s'il a changé ; le dernier lot fait foi.
# Une décision n'est retenue que si elle porte sur la version actuelle du cas (même empreinte), sinon elle est « périmée ».
# cas[k] = dernière version du cas k (k = cle_structure) ; par_lot[(fichier, id)] = k
cas, lot_de, emp, par_lot = {}, {}, {}, {}
for f in sorted(A.glob("lot_*.jsonl")):
    num = f.stem.split("_")[1]
    for l in open(f, encoding="utf-8"):
        x = json.loads(l); k = x["cle_structure"]
        cas[k] = x; lot_de[k] = num; emp[k] = empreinte(x); par_lot[(num, x["id"])] = k
emp_rev, par_revlot = {}, {}
for f in sorted(A.glob("revlot_*.jsonl")):
    num = f.stem.split("_")[1]
    for l in open(f, encoding="utf-8"):
        x = json.loads(l); emp_rev[(num, x["cle_structure"])] = empreinte(x); par_revlot[(num, x["id"])] = x["cle_structure"]
MODELE = {"decision": "Claude Haiku 5.5 (sous-agent Claude Code)", "revision": "Claude Sonnet 5.5 (sous-agent Claude Code, à l'aveugle)"}
dec, rejets, journal = {}, [], []
for pat in ["decision_*.jsonl", "revision_*.jsonl"]:          # les révisions (modèle plus fort) écrasent
    for f in sorted(A.glob(pat)):
        num = f.stem.split("_")[1]
        for n, l in enumerate(open(f, encoding="utf-8"), 1):
            l = l.strip()
            if not l: continue
            try: d = json.loads(l)
            except Exception: rejets.append((f.name, n, "JSON invalide")); continue
            k = (par_lot if pat.startswith("decision") else par_revlot).get((num, d.get("id")))
            if k is None: rejets.append((f.name, n, "id inconnu")); continue
            c = cas[k]
            vu = lot_de[k] == num if pat.startswith("decision") else emp_rev.get((num, k)) == emp[k]
            journal.append({"fichier": f.name, "id": d["id"], "cle_structure": k, "empreinte": emp[k], "modele": MODELE[pat.split("_")[0]],
                            "choix": d.get("choix"), "confiance": d.get("confiance"), "retenue": vu and k in actuel})
            if not vu: rejets.append((f.name, n, "périmée : le cas a changé depuis")); continue
            if k not in actuel: rejets.append((f.name, n, "orpheline : structure absente des données actuelles")); continue
            cles = {x["cle"] for x in c["candidats"]}
            if d.get("choix") != "aucun" and d.get("choix") not in cles:
                rejets.append((f.name, n, f"choix hors liste {d.get('choix')}")); continue
            d["source"] = "revision" if pat.startswith("revision") else "decision"
            # désaccord entre le premier avis (Haiku) et la révision (Sonnet) : on reste prudent
            d["desaccord"] = d["source"] == "revision" and k in dec and (dec[k]["choix"], dec[k].get("nom_propose")) != (d["choix"], d.get("nom_propose"))
            if d["desaccord"] and "aucun" not in (d["choix"], dec[k]["choix"]):
                # même entité inscrite deux fois (SIREN et RNA d'une même association) : ce n'est pas un vrai désaccord
                noms = {x["cle"]: x["nom"] or "" for x in c["candidats"]}
                if fuzz.token_set_ratio(nrm(noms.get(d["choix"])), nrm(noms.get(dec[k]["choix"]))) >= 90:
                    d["desaccord"] = False
            # accord des deux modèles sur le même choix : si l'un est « haute » et aucun « basse », on retient « haute »
            if d["source"] == "revision" and k in dec and not d["desaccord"] and d["choix"] != "aucun":
                cs = {d.get("confiance"), dec[k].get("confiance")}
                if "haute" in cs and "basse" not in cs: d["confiance"] = "haute"; d["accord_2_modeles"] = True
            dec[k] = d
manquants = [k for k in cas if k not in dec and k in actuel]
print(f"cas {len(cas)} ; décisions valides {len(dec)} ; rejetées {len(rejets)} ; manquantes {len(manquants)}")
print("  motifs de rejet :", dict(Counter(r[2].split(" siren")[0].split(" rna")[0] for r in rejets)))
for r in [r for r in rejets if not r[2].startswith(("périmée", "orpheline"))][:10]: print("  rejet", r)
# Journal de toutes les décisions et manifeste : de quoi refaire et vérifier chaque choix plus tard.
pd.DataFrame(journal).to_csv(RACINE/"out"/"journal_decisions.csv", index=False)
(A/"MANIFESTE.json").write_text(json.dumps({
    "integre_le": datetime.datetime.now().isoformat(timespec="seconds"),
    "consignes_sha256": hashlib.sha256((A/"CONSIGNES.md").read_bytes()).hexdigest()[:16],
    "modeles": MODELE, "regle": "décisions figées par empreinte (nom déclaré, département, candidats) ; un cas inchangé n'est jamais réarbitré",
    "lots": {f.name: sum(1 for _ in open(f, encoding="utf-8")) for f in sorted(A.glob("lot_*.jsonl"))},
    "decisions": {f.name: sum(1 for l in open(f, encoding="utf-8") if l.strip()) for f in sorted(A.glob("decision_*.jsonl"))},
    "revisions": {f.name: sum(1 for l in open(f, encoding="utf-8") if l.strip()) for f in sorted(A.glob("revision_*.jsonl"))},
    "cas": len(cas), "decisions_retenues": len(dec), "perimees": sum(1 for r in rejets if r[2].startswith("périmée")),
    "orphelines": sum(1 for r in rejets if r[2].startswith("orpheline")), "manquantes": len(manquants)},
    ensure_ascii=False, indent=1))

df = pd.DataFrame([{"struct_id": actuel[k], "choix": d["choix"], "confiance": d.get("confiance"), "nom_propose": d.get("nom_propose"),
                    "raison": d.get("raison"), "source": d["source"], "desaccord": d["desaccord"]} for k, d in dec.items()],
                  columns=["struct_id", "choix", "confiance", "nom_propose", "raison", "source", "desaccord"])
con.register("d", df)
con.execute("CREATE OR REPLACE TABLE decisions AS SELECT * FROM d")
# noms proposés : recherche exacte dans le registre (même département d'abord, puis unique en France)
con.execute("""CREATE OR REPLACE TEMP TABLE prop AS
WITH p AS (SELECT d.struct_id, norm(d.nom_propose) n, s.dep FROM decisions d JOIN structures s USING (struct_id)
           WHERE d.choix='aucun' AND d.nom_propose IS NOT NULL AND d.confiance IN ('haute','moyenne')),
m1 AS (SELECT p.struct_id, list(DISTINCT r.type_id||':'||r.ident) k FROM p JOIN ref_noms r ON r.nom_norm=p.n AND r.dep=p.dep GROUP BY 1),
m2 AS (SELECT p.struct_id, list(DISTINCT r.type_id||':'||r.ident) k FROM p JOIN ref_noms r ON r.nom_norm=p.n
       WHERE p.struct_id NOT IN (SELECT struct_id FROM m1) GROUP BY 1)
SELECT struct_id, k[1] AS cle FROM (SELECT * FROM m1 UNION ALL SELECT * FROM m2) WHERE len(k)=1""")
print("noms proposés retrouvés dans le registre :", con.execute("SELECT count(*) FROM prop").fetchone()[0])

PERS = "(" + ",".join(f"'{c}'" for c in PERSONNES) + ")"
con.execute(f"""CREATE OR REPLACE TABLE final2 AS
WITH ia AS (
  SELECT d.struct_id,
    coalesce(CASE WHEN d.choix<>'aucun' THEN d.choix END, 'x:'||split_part(p.cle,':',2)) AS k,
    CASE WHEN d.choix<>'aucun' THEN 'arbitrage IA ('||d.source||')' WHEN p.cle IS NOT NULL THEN 'nom proposé par IA, trouvé au registre' END AS methode_ia,
    d.confiance, d.raison, d.desaccord
  FROM decisions d LEFT JOIN prop p USING (struct_id))
SELECT f.*,
  CASE WHEN f.statut_final='fiable' THEN f.identifiant
       WHEN aa.ident IS NOT NULL THEN aa.ident
       WHEN ia.methode_ia IS NOT NULL THEN split_part(ia.k,':',2) END AS identifiant2,
  CASE WHEN f.statut_final='fiable' THEN f.methode
       WHEN aa.ident IS NOT NULL THEN 'nom quasi identique (approx.)'
       ELSE ia.methode_ia END AS methode2,
  ia.confiance AS confiance_ia, ia.raison AS raison_ia,
  CASE WHEN f.statut_final='fiable' THEN 'fiable'
       -- une catégorie qui désigne souvent une personne physique n'est jamais « fiable » par le nom seul (comme à l'étape 4)
       WHEN f.categorie IN {PERS} AND (aa.ident IS NOT NULL OR ia.methode_ia IS NOT NULL) THEN 'à vérifier'
       WHEN aa.ident IS NOT NULL THEN 'fiable'
       WHEN ia.methode_ia IS NOT NULL AND ia.confiance='haute' AND NOT ia.desaccord THEN 'fiable'
       WHEN ia.methode_ia IS NOT NULL THEN 'à vérifier'
       WHEN ia.struct_id IS NOT NULL THEN 'non rattaché (vu par IA)'
       ELSE f.statut_final END AS statut2
FROM final f LEFT JOIN approx_auto aa USING (struct_id) LEFT JOIN ia USING (struct_id)""")
print(con.execute("""SELECT statut2, count(*) structures, round(sum(montant)/1e9,2) md, round(100*sum(montant)/sum(sum(montant)) OVER (),1) pct
FROM final2 GROUP BY 1 ORDER BY md DESC""").df().to_string())
print(con.execute("""SELECT methode2, count(*) n, round(sum(montant)/1e6) meur FROM final2 WHERE statut2='fiable' GROUP BY 1 ORDER BY meur DESC""").df().to_string())

# --- Corrections du 24/11 ---
# Défaut 4 : nom officiel, activité (APE) et forme juridique pour TOUTES les structures fiables (y compris celles de l'IA).
# Défaut 2 : un rattachement par le nom seul vers une SCI / société immobilière, ou un nom d'un seul mot court
# dont l'activité n'a rien à voir avec la santé, n'est plus « fiable » mais « à vérifier ».
# Garde-fou sigles (test vérité 24/11) : les 2 vraies erreurs de l'IA en confiance haute portaient sur des sigles de 3 lettres ;
# un choix du premier modèle (non révisé) sur un nom de 5 caractères ou moins, différent du nom officiel, passe « à vérifier ».
SANTE = "'86','87','88','71','72','94','21','32','46','47.73','70','73','82','85','58','63','62','74'"
con.execute(f"""CREATE OR REPLACE TABLE final2 AS
WITH f AS (
  SELECT f.* EXCLUDE (nom_officiel), coalesce(u.denomination, rn.titre) AS nom_officiel, u.ape, CAST(u.cat_juridique AS VARCHAR) AS cat_juridique,
    s.nom_norm
  FROM final2 f JOIN structures s USING (struct_id)
  LEFT JOIN ref_ul u ON u.siren=f.identifiant2 LEFT JOIN ref_rna rn ON rn.rna=f.identifiant2),
h AS (SELECT *, statut2='fiable' AND methode2 <> 'identifiant écrit dans le texte' AND coalesce(
         ((cat_juridique LIKE '65%' OR ape LIKE '68%') AND NOT regexp_matches(upper(nom_declare), '\\bSCI\\b|CIVILE|IMMOB'))
      OR (nom_norm NOT LIKE '% %' AND length(nom_norm) < 8 AND ape IS NOT NULL
          AND NOT list_has_any([substr(ape,1,2), substr(ape,1,5)], [{SANTE}]))
      OR (methode2 = 'arbitrage IA (decision)' AND length(replace(nom_norm,' ','')) <= 5
          AND NOT contains(replace(norm(nom_officiel),' ',''), replace(nom_norm,' ',''))), false) AS homonyme
  FROM f)
SELECT * EXCLUDE (statut2, nom_norm, homonyme),
  CASE WHEN homonyme THEN 'à vérifier' ELSE statut2 END AS statut2,
  CASE WHEN homonyme THEN 'homonyme probable (SCI, immobilier, nom court hors santé, ou sigle court choisi par IA)' END AS alerte
FROM h""")
print("\n== Après garde-fous homonymes (défaut 2)")
print(con.execute("SELECT count(*), round(sum(montant)/1e6) FROM final2 WHERE alerte IS NOT NULL").fetchone(), "structures / M€ déclassées")
print(con.execute("""SELECT statut2, count(*) structures, round(sum(montant)/1e9,2) md, round(100*sum(montant)/sum(sum(montant)) OVER (),1) pct
FROM final2 GROUP BY 1 ORDER BY md DESC""").df().to_string())
print("fiables sans nom officiel :", con.execute("SELECT count(*) FROM final2 WHERE statut2='fiable' AND nom_officiel IS NULL").fetchone()[0])
con.execute(f"COPY (SELECT * FROM final2 ORDER BY montant DESC) TO '{sql_chemin(RACINE/'out'/'rattachement_final.csv')}' (HEADER)")
