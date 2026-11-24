"""Étape 5a : prépare les cas douteux pour l'arbitrage (les N plus gros montants), en lots JSONL.
Un cas = nom déclaré + variantes + adresse + jusqu'à 8 candidats officiels (SIRENE / RNA) avec leurs infos.
Chaque cas porte `cle_structure` (nom normalisé + département) : son identité stable, `id` n'étant qu'un numéro de rang.
Incrémental (figeage, 24/11) : les lots déjà écrits ne sont jamais réécrits. Un cas déjà arbitré dont l'empreinte
(nom, département, candidats) n'a pas changé est sauté ; seuls les cas nouveaux ou modifiés partent dans de nouveaux lots."""
import json, sys
from commun import connexion, RACINE, empreinte, cle_structure
N, TAILLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2000, 200
con = connexion()
FORME = {"92":"association","93":"fondation","73":"établissement public (hôpital, université…)","71":"administration de l'État",
         "72":"collectivité territoriale","74":"autre établissement public","57":"SAS","54":"SARL","55":"SA","56":"SCA",
         "65":"société civile","62":"GIE","63":"coopérative","94":"autre personne morale de droit privé","83":"comité d'entreprise / CSE",
         "84":"organisme professionnel","85":"organisme de retraite","81":"organisme de sécurité sociale","82":"mutuelle","91":"syndicat de propriétaires","99":"autre"}
con.execute(f"""CREATE OR REPLACE TABLE file_arbitrage AS
SELECT s.struct_id, f.statut_final, s.montant FROM structures s JOIN final f USING (struct_id)
WHERE f.statut_final <> 'fiable'
  AND s.struct_id NOT IN (SELECT struct_id FROM approx_auto)
ORDER BY s.montant DESC, s.struct_id LIMIT {N}""")
cands = con.execute("""
WITH c AS (
  SELECT r.struct_id, unnest(CASE WHEN r.statut='ambigu' THEN r.idents ELSE ['x:'||r.cle] END) AS k, 0 AS src, NULL AS trouve FROM rattachements r JOIN file_arbitrage USING (struct_id)
  UNION ALL SELECT a.struct_id, a.type_id||':'||a.ident, a.rang, a.b FROM cand_approx a JOIN file_arbitrage USING (struct_id))
SELECT struct_id, k, min(src) src, min(trouve) trouve FROM c GROUP BY ALL""").df()
cands["type"] = cands.k.str.split(":").str[0]; cands["ident"] = cands.k.str.split(":").str[1]
# 'x:' = clé exacte : SIREN (9 chiffres) ou RNA (W...)
cands.loc[cands.type=="x","type"] = cands.loc[cands.type=="x","ident"].str.startswith("W").map({True:"rna",False:"siren"})
con.register("cc", cands)
det = con.execute("""
SELECT cc.struct_id, cc.type, cc.ident, cc.src, cc.trouve,
  coalesce(u.denomination, rn.titre) AS nom, coalesce(u.sigle, rn.titre_court) AS sigle,
  CAST(u.cat_juridique AS VARCHAR) AS cj, u.ape, coalesce(u.etat, rn.position) AS etat, dep(rn.cp) AS dep_rna,
  (SELECT count(*)>0 FROM ref_etab e WHERE e.siren=cc.ident AND e.dep=s.dep) AS etab_meme_dep
FROM cc JOIN structures s USING (struct_id)
LEFT JOIN ref_ul u ON cc.type='siren' AND u.siren=cc.ident
LEFT JOIN ref_rna rn ON cc.type='rna' AND rn.rna=cc.ident""").df()
cas = con.execute("""SELECT s.struct_id, s.nom_norm, s.variantes, s.categorie, s.dep, s.cp, s.adresses, s.nb_lignes, s.montant
FROM structures s JOIN file_arbitrage USING (struct_id) ORDER BY s.montant DESC""").df()
A = RACINE/"data"/"arbitrage"
deja = {}
for f in sorted(A.glob("lot_*.jsonl")):
    for l in open(f, encoding="utf-8"): x = json.loads(l); deja[x["cle_structure"]] = empreinte(x)
num0 = max([int(f.stem.split("_")[1]) for f in A.glob("lot_*.jsonl")] or [0])
lots, cur, sautes, modifies = [], [], 0, 0
for r in cas.itertuples():
    d = det[det.struct_id == r.struct_id].sort_values(["src", "type", "ident"]).head(8)   # tri complet : même résultat à chaque relance
    cur.append({"id": int(r.struct_id), "cle_structure": cle_structure(r.nom_norm, r.dep if isinstance(r.dep, str) else None), "nom_declare": list(r.variantes)[:3], "categorie": (r.categorie if isinstance(r.categorie, str) else None), "departement": (r.dep if isinstance(r.dep, str) else None), "code_postal": (r.cp if isinstance(r.cp, str) else None),
        "adresse": (list(r.adresses) or [None])[0], "montant_eur": round(r.montant),
        "candidats": [{"cle": f"{c.type}:{c.ident}", "nom": c.nom, "nom_rapproche": (c.trouve if isinstance(c.trouve, str) else None), "sigle": (c.sigle if isinstance(c.sigle, str) else None),
            "forme": FORME.get((c.cj or "")[:2], c.cj) if c.type=="siren" else "association (RNA)",
            "ape": (c.ape if isinstance(c.ape, str) else None), "actif": c.etat in ("A","Active"), "etablissement_dans_le_departement": bool(c.etab_meme_dep) if c.type=="siren" else (isinstance(c.dep_rna, str) and c.dep_rna == r.dep)}
            for c in d.itertuples()]})
    e = empreinte(cur[-1])
    k = cur[-1]["cle_structure"]
    if deja.get(k) == e: cur.pop(); sautes += 1; continue
    if k in deja: modifies += 1
    cur[-1]["empreinte"] = e
    if len(cur) == TAILLE: lots.append(cur); cur = []
if cur: lots.append(cur)
for i, l in enumerate(lots, num0 + 1):
    (A/f"lot_{i:02d}.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in l)+"\n", encoding="utf-8")
print(len(cas), "cas dans la file ;", sautes, "déjà arbitrés et inchangés (décision gardée) ;", modifies, "modifiés à réarbitrer")
print(sum(map(len, lots)), "cas nouveaux en", len(lots), f"lots (lot_{num0+1:02d} et suivants) ;", "sans candidat :", sum(1 for l in lots for x in l if not x["candidats"]),
      "; montant", round(sum(x["montant_eur"] for l in lots for x in l)/1e6), "M€")
