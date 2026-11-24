"""Défaut 6, suite : mesure de l'IA sur les cas dont on connaît la réponse (lot préparé par 12_test_verite.py).
Compare data/test_verite/decision_test.jsonl à reponses.csv (que l'IA n'a jamais vu)."""
import json, csv
from commun import RACINE, connexion
L = RACINE/"data"/"test_verite"
rep = {int(r["id"]): r["vraie_cle"] for r in csv.DictReader(open(L/"reponses.csv"))}
cas = {json.loads(l)["id"]: json.loads(l) for l in open(L/"lot_test.jsonl")}
con = connexion()
sir = dict(con.execute("SELECT rna, siren FROM ref_ul WHERE rna IS NOT NULL AND rna IN (SELECT unnest(?))",
          [[c["cle"].split(":")[1] for x in cas.values() for c in x["candidats"] if c["cle"].startswith("rna:")]]).fetchall())
def cle(k):  # même règle que le pipeline : RNA -> SIREN quand l'association a les deux
    t, i = k.split(":"); return sir.get(i, i) if t == "rna" else i
from collections import Counter
res = Counter(); conf = Counter()
for l in open(L/"decision_test.jsonl"):
    d = json.loads(l); v = rep[d["id"]]; dispo = v in {cle(c["cle"]) for c in cas[d["id"]]["candidats"]}
    if d["choix"] == "aucun": k = "aucun (bonne réponse dans la liste)" if dispo else "aucun (bonne réponse absente : correct)"
    else: k = "juste" if cle(d["choix"]) == v else "faux"
    res[k] += 1; conf[(d.get("confiance"), k)] += 1
print(dict(res))
for c in ("haute", "moyenne", "basse"):
    j, f = conf[(c, "juste")], conf[(c, "faux")]
    if j + f: print(f"confiance {c} : {j} justes, {f} faux -> précision {100*j/(j+f):.0f} %")
h = conf[("haute", "juste")] + conf[("haute", "faux")]
json.dump({"total": sum(res.values()), **res, "precision_haute": round(100*conf[("haute","juste")]/h, 1) if h else None},
          open(RACINE/"out"/"test_verite_ia.json", "w"), ensure_ascii=False, indent=1)
