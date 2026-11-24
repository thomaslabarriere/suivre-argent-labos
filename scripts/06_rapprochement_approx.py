"""Étape 4 : rapprochement approximatif des structures non rattachées.
Blocage : même département + un des 2 mots les plus rares du nom. Score : rapidfuzz.
Sortie : table cand_approx (6 meilleurs candidats par structure) et approx_auto (acceptés sans IA)."""
from commun import connexion
from rapidfuzz import fuzz
import time
t0 = time.time()
con = connexion()
TOK = "list_filter(string_split(nom_norm,' '), lambda t: length(t)>=3 AND NOT regexp_matches(t,'^[0-9]+$'))"

con.execute(f"""CREATE OR REPLACE TEMP TABLE pool AS
SELECT s.struct_id, s.nom_norm, s.dep, s.montant FROM structures s JOIN final f USING (struct_id)
WHERE f.statut_final='non rattaché' AND s.nom_norm IS NOT NULL AND s.dep IS NOT NULL""")
con.execute(f"CREATE OR REPLACE TEMP TABLE pool_tok AS SELECT struct_id, dep, unnest({TOK}) AS tok FROM pool")
print("pool", con.execute("SELECT count(*) FROM pool").fetchone(), round(time.time()-t0))

# fréquence de chaque mot dans le référentiel (uniquement les mots qui nous servent)
con.execute(f"""CREATE OR REPLACE TEMP TABLE df AS
SELECT tok, count(*) n FROM (SELECT unnest({TOK}) tok FROM ref_noms) WHERE tok IN (SELECT DISTINCT tok FROM pool_tok) GROUP BY 1""")
print("df", round(time.time()-t0))
con.execute("""CREATE OR REPLACE TEMP TABLE choix AS
SELECT struct_id, dep, tok FROM (SELECT p.*, d.n, row_number() OVER (PARTITION BY struct_id ORDER BY d.n, p.tok) rk
  FROM pool_tok p JOIN df d USING (tok)) WHERE rk<=2""")
con.execute(f"""CREATE OR REPLACE TEMP TABLE ref_tok AS
SELECT * FROM (SELECT type_id, ident, nom_norm, dep, etat, unnest({TOK}) tok FROM ref_noms
  WHERE dep IN (SELECT DISTINCT dep FROM choix)) r
WHERE (tok, dep) IN (SELECT tok, dep FROM choix)""")
print("ref_tok", con.execute("SELECT count(*) FROM ref_tok").fetchone(), round(time.time()-t0))
paires = con.execute("""SELECT DISTINCT p.struct_id, p.nom_norm AS a, r.type_id, r.ident, r.nom_norm AS b, r.etat
FROM choix c JOIN pool p USING (struct_id) JOIN ref_tok r ON r.tok=c.tok AND r.dep=c.dep""").df()
print("paires", len(paires), round(time.time()-t0))

paires["score"] = [fuzz.token_set_ratio(a, b) for a, b in zip(paires.a, paires.b)]
paires["strict"] = [fuzz.token_sort_ratio(a, b) for a, b in zip(paires.a, paires.b)]
# token_set seul donne 100 à un nom inclus (« PARIS » dans « ESSENCEMEDIACOM PARIS ») : on classe sur la moyenne des deux
paires["mix"] = (paires.score + paires.strict) / 2
paires = paires[(paires.score >= 70) & (paires["mix"] >= 60)]
# tri complet (égalités départagées par le score strict puis l'identifiant) : même résultat à chaque exécution
paires = (paires.sort_values(["struct_id", "mix", "strict", "type_id", "ident"], ascending=[True, False, False, True, True], kind="mergesort")
          .drop_duplicates(["struct_id","type_id","ident"]).groupby("struct_id").head(6))
con.register("p", paires)
con.execute("CREATE OR REPLACE TABLE cand_approx AS SELECT *, row_number() OVER (PARTITION BY struct_id ORDER BY mix DESC, strict DESC, type_id, ident) rang FROM p")
# accepté sans IA : nom quasi identique (ordre des mots compris), et pas de second candidat presque aussi bon
con.execute("""CREATE OR REPLACE TABLE approx_auto AS
SELECT c1.struct_id, c1.type_id, c1.ident, c1.score, c1.strict FROM cand_approx c1
LEFT JOIN cand_approx c2 ON c2.struct_id=c1.struct_id AND c2.rang=2
WHERE c1.rang=1 AND c1.strict>=95 AND (c2.mix IS NULL OR c2.mix < c1.mix-5)""")
print(con.execute("""SELECT 'avec candidat' k, count(DISTINCT struct_id), round(sum(m)/1e6) FROM (SELECT DISTINCT c.struct_id, s.montant m FROM cand_approx c JOIN structures s USING(struct_id))
UNION ALL SELECT 'auto', count(*), round(sum(s.montant)/1e6) FROM approx_auto a JOIN structures s USING(struct_id)""").fetchall())
print("durée", round(time.time()-t0), "s")
