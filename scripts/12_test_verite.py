"""Défaut 6 : mesurer le taux d'erreur SANS humain et SANS IA juge.
Vérité terrain gratuite : les structures dont l'identifiant officiel était écrit dans le texte (étape 2).
On efface cet identifiant (et tout numéro du nom), on refait tourner les règles des étapes 3 à 5 sur ces structures,
et on compare avec la vraie réponse. Biais connu : ces structures sont plutôt « bien remplies », le vrai taux
d'erreur sur le reste de la base est sans doute un peu plus élevé.
Sortie : table test_verite, out/test_verite.csv, et data/test_verite/lot_test.jsonl (cas douteux à faire arbitrer par l'IA)."""
import json, re, sys, unidecode
from rapidfuzz import fuzz
from commun import connexion, RACINE, sql_chemin
con = connexion()
TOK = "list_filter(string_split(nom_norm,' '), lambda t: length(t)>=3 AND NOT regexp_matches(t,'^[0-9]+$'))"
NUM = "'\\b(W[0-9A-Z][0-9]{8}|[0-9][0-9 ]{7,}[0-9])\\b'"   # RNA, SIREN/SIRET (avec ou sans espaces)

# 1. La vérité : un seul identifiant écrit dans le texte, vérifié au registre.
con.execute("""CREATE OR REPLACE TEMP TABLE verite AS
SELECT r.struct_id, r.cle AS vraie_cle FROM rattachements r
WHERE r.methode='identifiant écrit dans le texte' AND r.statut='rattaché'""")
# 2. Les mêmes structures, numéros effacés.
con.execute(f"""CREATE OR REPLACE TEMP TABLE ts AS
SELECT s.struct_id, s.dep, s.categorie, s.montant, s.variantes, s.cp, s.adresses,
  nullif(trim(regexp_replace(regexp_replace(s.nom_norm, {NUM}, ' ', 'g'), '\\s+', ' ', 'g')), '') AS nom_norm,
  nullif(trim(regexp_replace(regexp_replace(s.nom_sans_par, {NUM}, ' ', 'g'), '\\s+', ' ', 'g')), '') AS nom_sans_par,
  nullif(trim(regexp_replace(coalesce(s.sigle_norm,''), {NUM}, ' ', 'g')), '') AS sigle_norm
FROM structures s JOIN verite USING (struct_id)""")
n, m = con.execute("SELECT count(*), sum(montant) FROM ts").fetchone()
print(f"Jeu de vérité : {n} structures, {m/1e6:.0f} M€")

# 3. Étape 3 rejouée (mêmes règles que 04_rapprochement_exact.py).
con.execute("""CREATE OR REPLACE TEMP TABLE t_exact AS
WITH r AS (SELECT *, (type_id='rna' OR coalesce(etat,'A') NOT IN ('C','F','D','S')) AS actif FROM ref_noms),
c AS (
  SELECT s.struct_id, r.type_id, r.ident, r.actif, 0.9 AS confiance, 'nom + département' AS methode
  FROM ts s JOIN r ON r.nom_norm IN (s.nom_norm, s.nom_sans_par) AND r.dep = s.dep
  UNION ALL SELECT s.struct_id, r.type_id, r.ident, r.actif, 0.85, 'sigle + département'
  FROM ts s JOIN r ON s.sigle_norm IS NOT NULL AND r.nom_norm = s.sigle_norm AND r.dep = s.dep
  UNION ALL SELECT s.struct_id, r.type_id, r.ident, r.actif, 0.8, 'nom, unique en France'
  FROM ts s JOIN r ON r.nom_norm IN (s.nom_norm, s.nom_sans_par)),
c2 AS (SELECT c.*, coalesce(u.siren, c.ident) AS cle FROM c LEFT JOIN ref_ul u ON c.type_id='rna' AND u.rna=c.ident),
best AS (SELECT * FROM c2 QUALIFY confiance = max(confiance) OVER (PARTITION BY struct_id)),
ch AS (SELECT struct_id, min(methode) methode, count(DISTINCT cle) nb, count(DISTINCT cle) FILTER (WHERE actif) nba,
              min(cle) cle, min(cle) FILTER (WHERE actif) cle_a, list(DISTINCT type_id||':'||ident) idents FROM best GROUP BY 1)
SELECT struct_id, methode, idents, CASE WHEN nb=1 THEN cle WHEN nba=1 THEN cle_a END AS cle,
       CASE WHEN nb=1 OR nba=1 THEN 'rattaché' ELSE 'ambigu' END AS statut FROM ch""")
# 4. Contrôle « fiable » de l'étape 3 (mêmes règles que 05_bilan.py + garde-fous de 08).
df = con.execute("""SELECT e.struct_id, e.cle, e.methode, t.variantes[1] AS declare, t.nom_norm, t.categorie,
  coalesce(u.denomination, rn.titre) AS officiel, u.sigle, u.ape, CAST(u.cat_juridique AS VARCHAR) cj
FROM t_exact e JOIN ts t USING (struct_id) LEFT JOIN ref_ul u ON u.siren=e.cle LEFT JOIN ref_rna rn ON rn.rna=e.cle
WHERE e.statut='rattaché'""").df()
def n_(x): return re.sub(r"[^A-Z0-9 ]+", " ", unidecode.unidecode(str(x or "")).upper())
SANTE = ('86','87','88','71','72','94','21','32','46','47.73','70','73','82','85','58','63','62','74')
def fiable(r):
    coh = max(fuzz.token_set_ratio(n_(r.declare), n_(r.officiel)), fuzz.ratio(n_(r.declare), n_(r.sigle)) if isinstance(r.sigle, str) else 0)
    if coh < 80 or r.categorie in ('Etudiant','Influenceur','Vétérinaire'): return False
    nn = r.nom_norm or ""
    if r.methode.startswith('nom, unique en France') and len(nn) < 8 and ' ' not in nn: return False
    ape, cj = (r.ape if isinstance(r.ape, str) else None), (r.cj if isinstance(r.cj, str) else "")
    if (cj.startswith('65') or (ape or '').startswith('68')) and not re.search(r'\bSCI\b|CIVILE|IMMOB', str(r.declare).upper()): return False
    if ' ' not in nn and len(nn) < 8 and ape and ape[:2] not in SANTE and ape[:5] not in SANTE: return False
    return True
df["fiable"] = [fiable(r) for r in df.itertuples()]
con.register("fx", df[["struct_id", "fiable"]])

# 5. Étape 4 rejouée sur ce qui reste (mêmes règles que 06_rapprochement_approx.py).
con.execute("CREATE OR REPLACE TEMP TABLE pool AS SELECT struct_id, nom_norm, dep FROM ts WHERE struct_id NOT IN (SELECT struct_id FROM t_exact) AND nom_norm IS NOT NULL AND dep IS NOT NULL")
con.execute(f"CREATE OR REPLACE TEMP TABLE pool_tok AS SELECT struct_id, dep, unnest({TOK}) AS tok FROM pool")
con.execute(f"CREATE OR REPLACE TEMP TABLE dfreq AS SELECT tok, count(*) n FROM (SELECT unnest({TOK}) tok FROM ref_noms) WHERE tok IN (SELECT DISTINCT tok FROM pool_tok) GROUP BY 1")
con.execute("CREATE OR REPLACE TEMP TABLE choix AS SELECT struct_id, dep, tok FROM (SELECT p.*, row_number() OVER (PARTITION BY struct_id ORDER BY d.n, p.tok) rk FROM pool_tok p JOIN dfreq d USING (tok)) WHERE rk<=2")
con.execute(f"CREATE OR REPLACE TEMP TABLE ref_tok AS SELECT * FROM (SELECT type_id, ident, nom_norm, dep, unnest({TOK}) tok FROM ref_noms WHERE dep IN (SELECT DISTINCT dep FROM choix)) WHERE (tok, dep) IN (SELECT tok, dep FROM choix)")
pa = con.execute("SELECT DISTINCT p.struct_id, p.nom_norm a, r.type_id, r.ident, r.nom_norm b FROM choix c JOIN pool p USING (struct_id) JOIN ref_tok r ON r.tok=c.tok AND r.dep=c.dep").df()
pa["score"] = [fuzz.token_set_ratio(a, b) for a, b in zip(pa.a, pa.b)]
pa["strict"] = [fuzz.token_sort_ratio(a, b) for a, b in zip(pa.a, pa.b)]
pa["mix"] = (pa.score + pa.strict) / 2
pa = pa[(pa.score >= 70) & (pa["mix"] >= 60)].sort_values(["struct_id", "mix", "type_id", "ident"], ascending=[True, False, True, True])
pa = pa.drop_duplicates(["struct_id", "type_id", "ident"]).groupby("struct_id").head(6).copy()
pa["rang"] = pa.groupby("struct_id").cumcount() + 1
con.register("pa", pa)
con.execute("""CREATE OR REPLACE TEMP TABLE t_approx AS SELECT c1.struct_id, coalesce(u.siren, c1.ident) cle FROM pa c1
LEFT JOIN pa c2 ON c2.struct_id=c1.struct_id AND c2.rang=2 LEFT JOIN ref_ul u ON c1.type_id='rna' AND u.rna=c1.ident
WHERE c1.rang=1 AND c1.strict>=95 AND (c2.mix IS NULL OR c2.mix < c1.mix-5)""")

# 6. Verdict par structure.
con.execute("""CREATE OR REPLACE TABLE test_verite AS
SELECT t.struct_id, t.variantes[1] AS nom_declare, t.categorie, t.montant, v.vraie_cle,
  coalesce(CASE WHEN fx.fiable THEN e.cle END, a.cle) AS cle_trouvee,
  CASE WHEN fx.fiable THEN 'étape 3 (nom exact), fiable' WHEN a.cle IS NOT NULL THEN 'étape 4 (nom quasi identique), fiable'
       WHEN e.statut='rattaché' THEN 'étape 3, mis à vérifier' WHEN e.statut='ambigu' THEN 'plusieurs candidats'
       WHEN t.struct_id IN (SELECT struct_id FROM pa) THEN 'candidats approximatifs (IA)' ELSE 'rien trouvé' END AS issue
FROM ts t JOIN verite v USING (struct_id) LEFT JOIN t_exact e USING (struct_id) LEFT JOIN fx USING (struct_id)
LEFT JOIN t_approx a ON a.struct_id=t.struct_id AND e.struct_id IS NULL""")
con.execute("""CREATE OR REPLACE TEMP TABLE tv AS SELECT *, CASE WHEN cle_trouvee IS NULL THEN 'pas de réponse automatique'
  WHEN cle_trouvee=vraie_cle THEN 'juste' ELSE 'faux' END AS verdict FROM test_verite""")
print("\n== Ce que donnent les règles automatiques (étapes 3 et 4) sur des cas dont on connaît la réponse")
print(con.execute("""SELECT issue, verdict, count(*) structures, round(sum(montant)/1e6,1) meur FROM tv GROUP BY ALL ORDER BY 1,2""").df().to_string())
r = con.execute("""SELECT count(*) FILTER (WHERE verdict='juste'), count(*) FILTER (WHERE verdict='faux'),
  sum(montant) FILTER (WHERE verdict='juste'), sum(montant) FILTER (WHERE verdict='faux') FROM tv""").fetchone()
print(f"\nPrécision des « fiable » automatiques : {r[0]}/{r[0]+r[1]} justes ({100*r[0]/(r[0]+r[1]):.1f} %), "
      f"en euros {100*r[2]/(r[2]+r[3]):.1f} %")
print("\nExemples d'erreurs (à regarder : souvent la même entité sous deux numéros) :")
print(con.execute("""SELECT tv.nom_declare, coalesce(u1.denomination, r1.titre) vrai, coalesce(u2.denomination, r2.titre) trouve, round(montant/1e3) keur
FROM tv LEFT JOIN ref_ul u1 ON u1.siren=vraie_cle LEFT JOIN ref_rna r1 ON r1.rna=vraie_cle
LEFT JOIN ref_ul u2 ON u2.siren=cle_trouvee LEFT JOIN ref_rna r2 ON r2.rna=cle_trouvee
WHERE verdict='faux' ORDER BY montant DESC LIMIT 12""").df().to_string())
# Les « faux » ne sont pas tous des erreurs : la vérité elle-même (le numéro écrit par le labo) peut être fausse.
fx2 = con.execute("""SELECT struct_id, nom_declare, montant, coalesce(u1.denomination, r1.titre) vrai, coalesce(u2.denomination, r2.titre) trouve
FROM tv LEFT JOIN ref_ul u1 ON u1.siren=vraie_cle LEFT JOIN ref_rna r1 ON r1.rna=vraie_cle
LEFT JOIN ref_ul u2 ON u2.siren=cle_trouvee LEFT JOIN ref_rna r2 ON r2.rna=cle_trouvee WHERE verdict='faux'""").df()
def type_err(r):
    if fuzz.token_set_ratio(n_(r.vrai), n_(r.trouve)) >= 90: return "même nom, autre numéro (doublon probable du registre)"
    if fuzz.token_set_ratio(n_(r.nom_declare), n_(r.vrai)) < 60 and fuzz.token_set_ratio(n_(r.nom_declare), n_(r.trouve)) >= 90:
        return "le numéro écrit par le labo semble faux (notre réponse colle au nom)"
    return "erreur probable de notre part"
fx2["type_erreur"] = [type_err(r) for r in fx2.itertuples()]
print("\n== Nature des « faux »")
print(fx2.groupby("type_erreur").agg(structures=("struct_id", "size"), meur=("montant", lambda x: round(x.sum()/1e6, 1))).to_string())
con.register("fx2", fx2[["struct_id", "type_erreur"]])
con.execute("CREATE OR REPLACE TEMP TABLE tv AS SELECT tv.*, fx2.type_erreur FROM tv LEFT JOIN fx2 USING (struct_id)")
e = fx2[fx2.type_erreur == "erreur probable de notre part"]
print(f"Taux d'erreur probable des « fiable » automatiques : {len(e)}/{r[0]+r[1]} ({100*len(e)/(r[0]+r[1]):.1f} %), "
      f"en euros {100*e.montant.sum()/(r[2]+r[3]):.1f} %")
con.execute(f"COPY (SELECT * FROM tv ORDER BY montant DESC) TO '{RACINE}/out/test_verite.csv' (HEADER)")

# 7. Lot de test pour l'IA : les cas qui seraient partis en arbitrage, avec leurs candidats, dans le même format que 07.
FORME = {"92":"association","93":"fondation","73":"établissement public (hôpital, université…)","71":"administration de l'État",
         "72":"collectivité territoriale","74":"autre établissement public","57":"SAS","54":"SARL","55":"SA","56":"SCA",
         "65":"société civile","62":"GIE","63":"coopérative","94":"autre personne morale de droit privé","83":"comité d'entreprise / CSE",
         "84":"organisme professionnel","85":"organisme de retraite","81":"organisme de sécurité sociale","82":"mutuelle","91":"syndicat de propriétaires","99":"autre"}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
cands = con.execute(f"""
WITH q AS (SELECT struct_id FROM tv WHERE issue IN ('plusieurs candidats','candidats approximatifs (IA)','étape 3, mis à vérifier')
           ORDER BY hash(struct_id) LIMIT {N}),
c AS (SELECT e.struct_id, unnest(e.idents) k, 0 src FROM t_exact e JOIN q USING (struct_id)
      UNION ALL SELECT p.struct_id, p.type_id||':'||p.ident, p.rang FROM pa p JOIN q USING (struct_id))
SELECT c.struct_id, split_part(k,':',1) type, split_part(k,':',2) ident, min(src) src FROM c GROUP BY ALL""").df()
con.register("cc", cands)
det = con.execute("""SELECT cc.*, coalesce(u.denomination, rn.titre) nom, coalesce(u.sigle, rn.titre_court) sigle, CAST(u.cat_juridique AS VARCHAR) cj,
  u.ape, coalesce(u.etat, rn.position) etat, dep(rn.cp) dep_rna, (SELECT count(*)>0 FROM ref_etab e WHERE e.siren=cc.ident AND e.dep=t.dep) emd, t.dep
FROM cc JOIN ts t USING (struct_id) LEFT JOIN ref_ul u ON cc.type='siren' AND u.siren=cc.ident LEFT JOIN ref_rna rn ON cc.type='rna' AND rn.rna=cc.ident""").df()
cas = con.execute("SELECT t.* FROM ts t WHERE struct_id IN (SELECT struct_id FROM cc) ORDER BY hash(struct_id)").df()
L = RACINE/"data"/"test_verite"; L.mkdir(parents=True, exist_ok=True)
# Le lot de test et ses réponses sont figés dès que l'IA y a répondu (decision_test.jsonl) : sinon les numéros changeraient sous ses réponses.
FIGE = (L/"decision_test.jsonl").exists()
if FIGE: print("\nLot de test IA déjà arbitré : conservé tel quel (supprimer data/test_verite/decision_test.jsonl pour le refaire)")
with open(L/("lot_test.jsonl" if not FIGE else "lot_test_nouveau.jsonl"), "w", encoding="utf-8") as f:
    for r in cas.itertuples():
        d = det[det.struct_id == r.struct_id].sort_values(["src", "type", "ident"]).head(8)
        f.write(json.dumps({"id": int(r.struct_id), "nom_declare": [re.sub(r"\b(W[0-9A-Z][0-9]{8}|[0-9][0-9 .]{7,}[0-9])\b", "", v).strip() for v in list(r.variantes)[:3]],
          "categorie": r.categorie if isinstance(r.categorie, str) else None, "departement": r.dep if isinstance(r.dep, str) else None,
          "code_postal": r.cp if isinstance(r.cp, str) else None, "adresse": None, "montant_eur": round(r.montant),
          "candidats": [{"cle": f"{c.type}:{c.ident}", "nom": c.nom, "nom_rapproche": None, "sigle": c.sigle if isinstance(c.sigle, str) else None,
             "forme": FORME.get((c.cj or "")[:2], c.cj) if c.type == "siren" else "association (RNA)", "ape": c.ape if isinstance(c.ape, str) else None,
             "actif": c.etat in ("A", "Active"), "etablissement_dans_le_departement": bool(c.emd) if c.type == "siren" else (isinstance(c.dep_rna, str) and c.dep_rna == r.dep)}
             for c in d.itertuples()]}, ensure_ascii=False) + "\n")
# la vraie réponse, rangée à part (l'IA ne la voit jamais)
if not FIGE:
    con.execute(f"COPY (SELECT struct_id AS id, vraie_cle FROM tv WHERE struct_id IN (SELECT struct_id FROM cc)) TO '{sql_chemin(L/'reponses.csv')}' (HEADER)")
print(f"\nLot de test IA : {len(cas)} cas -> data/test_verite/lot_test.jsonl (réponses à part dans reponses.csv)")
