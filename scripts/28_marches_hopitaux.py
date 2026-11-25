"""Piste 2 : un hôpital achète-t-il aux labos qui le financent ?
Croise les marchés publics (DECP consolidées, data.gouv.fr) dont l'acheteur est un établissement de santé
avec les versements des labos à ces mêmes établissements (Transparence Santé, vue nette `ts_net` de commun.py).

Entrées  : data/ext/decp/decp-global.json, data/ext/ts_annees/*.parquet, out/rattachement_final.csv,
           data/ref/sirene_ul.parquet, data/travail.duckdb (LECTURE SEULE : table `lignes` = struct_id de chaque ligne TS)
Sorties  : out/marches_hopitaux_labos.csv, out/hopitaux_finances_et_acheteurs.csv

Précautions de lecture :
- Le montant DECP d'un accord-cadre est un PLAFOND (souvent le plafond global répété sur chaque titulaire), pas une dépense.
  On dédoublonne (acheteur, objet, date, montant) en divisant par le nombre de titulaires distincts, et on ne publie
  la somme que dans des colonnes nommées « plafond » ; le total de référence exclut les marchés déclarés >= 100 M€.
- Les versements TS sont restreints aux années couvertes par les marchés retenus (fenêtre affichée dans le log).
Un lien n'est pas une irrégularité : financer et vendre au même hôpital est légal et courant, la loi encadre la transparence, pas l'interdiction.
"""
import json, sys, pathlib, duckdb
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from commun import RACINE, sql_chemin, vues_ts, ALIAS_GROUPE

DECP = RACINE / "data/ext/decp"
SLIM = DECP / "decp_marches.parquet"
OUT = RACINE / "out"
GROS = 1e8  # marchés déclarés >= 100 M€ : plafonds d'accords-cadres, exclus du total de référence

# 1. Aplatir le JSON DECP (un marché par ligne, titulaires sans nom : SIRET seulement)
if not SLIM.exists():
    import pandas as pd
    rows = []
    with open(DECP / "decp-global.json", encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip().rstrip(",")
            if not ligne.startswith('{"id"'):
                continue
            try: m = json.loads(ligne)
            except Exception: continue
            tit = [t.get("titulaire", {}) for t in (m.get("titulaires") or []) if isinstance(t, dict)]
            tit = [t.get("id") for t in tit if t.get("id")]
            tech = ((m.get("techniques") or {}).get("technique") or []) if isinstance(m.get("techniques"), dict) else []
            rows.append(dict(id=str(m.get("id")), acheteur=(m.get("acheteur") or {}).get("id"), titulaires=tit,
                             montant=m.get("montant"), date_notif=m.get("dateNotification"), cpv=m.get("codeCPV"),
                             nature=m.get("nature"), procedure=m.get("procedure"),
                             accord_cadre=("Accord-cadre" in tech) or bool(m.get("idAccordCadre")),
                             objet=(m.get("objet") or "")[:200], vu=m.get("ref__file_date")))
    pd.DataFrame(rows).to_parquet(SLIM)
    print(f"DECP aplaties : {len(rows):,} lignes")

con = duckdb.connect()
con.execute("SET memory_limit='6GB'")
vues_ts(con)
con.execute(f"ATTACH '{sql_chemin(RACINE / 'data/travail.duckdb')}' AS trav (READ_ONLY)")
con.execute("""CREATE MACRO norm(s) AS trim(regexp_replace(regexp_replace(upper(strip_accents(coalesce(s,''))),'[^A-Z0-9]+',' ','g'),'\\s+',' ','g'))""")
# Clé de nom propre à ce script : le titulaire DECP est un fournisseur quelconque (dispositifs, logiciels, services),
# d'où une liste de mots génériques plus large que STOP_LABO de commun.py, qui ne vise que des labos déclarants.
GENERIQUES = ("LABORATOIRE LABORATOIRES LABO LABS PHARMA PHARMACEUTICALS PHARMACEUTICAL PHARMACEUTIQUE PHARMACIE PHARMACEUTIQUES "
 "FRANCE FRANCAIS FRANCAISE EUROPE EUROPEAN INTERNATIONAL INTERNATIONNAL HEALTHCARE HEALTH CARE MEDICAL MEDICALE MEDICALES MEDICAUX MEDICO SANTE SANTES "
 "GROUPE GROUP HOLDING SOCIETE COMPAGNIE COMPANY CORPORATION CORP LIMITED LTD INC GMBH BV AG SPA SRL NV SAS SASU SARL SA THE AND DES DE DU LA LE LES ET "
 "BIO BIOTECH BIOSCIENCES BIOSCIENCE SCIENCES SCIENCE THERAPEUTICS THERAPEUTIQUE THERAPEUTIQUES TECHNOLOGIES TECHNOLOGY TECHNIQUES SYSTEMS SYSTEM SERVICES SERVICE "
 "SOLUTIONS DIAGNOSTICS DIAGNOSTIC DIAGNOSTIQUE INSTRUMENTS DEVICES SURGICAL ORTHOPEDICS ORTHOPAEDICS NEW GLOBAL FRANCO PARIS LYON NORD SUD OUEST EST "
 "DIFFUSION DISTRIBUTION DISTRIB COMMERCE TRADING MANUFACTURING AQUITAINE ATLANTIQUE BRETAGNE OCCITANIE ALSACE LORRAINE AUVERGNE NORMANDIE MIDI PYRENEES CENTRE GRAND BOURGOGNE PROVENCE ALPES RHONE LANGUEDOC ROUSSILLON PICARDIE CHAMPAGNE ARDENNE LOIRE PAYS CORSE OUTRE MER "
 "NATIONAL ANTILLES PRODUCTS PRODUITS CONSUMER GENERIC GENERIQUES GENERICS VET VETERINAIRE ANIMAL BUSINESS UNIT DIVISION INDUSTRIE INDUSTRIES").split()
# mots qui, pris comme clé, donneraient des appariements absurdes avec des fournisseurs non-pharma
INTERDITS = set("BOSTON NOVA UNION ALLIANCE ORANGE ESSENTIEL EXPERT AVENIR ALPHA OMEGA SIGMA DELTA CENTRAL PRIME UNIVERSAL MEDIA DIRECT ULTRA SMART PRO CONCEPT QUANTUM EXPRESSION MARQUE ASTEN INTERACTION ASSISTANCE DENTAL TECHNIQUE NATIONALE SOFTWAY".split())
GEN_SQL = "[" + ",".join(f"'{w}'" for w in GENERIQUES) + "]"
ALIAS_SQL = "MAP {" + ",".join(f"'{k}': '{v}'" for k, v in ALIAS_GROUPE.items()) + "}"
con.execute(f"""CREATE MACRO sig(x) AS list_filter(string_split(norm(x),' '), lambda w: NOT list_contains({GEN_SQL}, w) AND NOT regexp_matches(w,'^[0-9]+$') AND length(w)>0)""")
def cle_sql(col):
    # clé = premier mot significatif (alias de groupe de commun.py appliqués : ELI -> LILLY, GSK -> GLAXOSMITHKLINE...) ;
    # au moins 5 lettres sinon NULL
    w = f"coalesce({ALIAS_SQL}[sig({col})[1]], sig({col})[1])"
    return f"(CASE WHEN length({w})>=5 THEN {w} END)"

# 2. Hôpitaux : rattachement fiable, SIREN à 9 chiffres, catégorie établissement ou groupement sanitaire
con.execute(f"""CREATE TABLE hop AS
SELECT struct_id::BIGINT struct_id, identifiant2 AS siren, min(nom_officiel) nom_officiel
FROM read_csv('{sql_chemin(OUT / 'rattachement_final.csv')}', all_varchar=true)
WHERE statut2='fiable' AND regexp_matches(identifiant2,'^[0-9]{{9}}$')
  AND (categorie IN ('Etablissement de santé','Groupement sanitaire') OR cat_juridique IN ('7364','7361','7362','7363','7365','7366','7367','7368','7369'))
GROUP BY ALL""")
con.execute(f"""CREATE TABLE sir AS SELECT siren, coalesce(nullif(denominationUniteLegale,''), trim(coalesce(prenomUsuelUniteLegale,'')||' '||coalesce(nomUniteLegale,''))) AS nom,
  categorieJuridiqueUniteLegale AS cj FROM read_parquet('{sql_chemin(RACINE / 'data/ref/sirene_ul.parquet')}')""")
# acheteurs additionnels : tout acheteur DECP dont la catégorie juridique SIRENE est un établissement public de santé (7364) + centrales d'achat
con.execute("""CREATE TABLE centrales AS SELECT siren, nom FROM sir
WHERE regexp_matches(upper(strip_accents(nom)),'(^| )(UNIHA|RESAH|CAIH|UGAP)( |$)|CENTRALE D ACHAT|GROUPEMENT D ACHAT|ACHATS HOSPITALIERS|GROUPEMENT HOSPITALIER DE TERRITOIRE|^GHT ')""")

# 3. Marchés : une ligne par (acheteur, marché, titulaire), version la plus récente de chaque marché.
# Accord-cadre multi-attributaire : DECP publie souvent un enregistrement par titulaire avec le plafond GLOBAL.
# On regroupe (acheteur, objet, date, montant déclaré) et on divise le montant par le nombre de titulaires distincts du groupe.
con.execute(f"""CREATE TABLE marches AS
WITH d AS (SELECT * FROM read_parquet('{sql_chemin(SLIM)}') QUALIFY row_number() OVER (PARTITION BY acheteur, id ORDER BY vu DESC)=1),
u AS (SELECT id, left(acheteur,9) AS ach,
      -- montants aberrants (saisies 9999999..., > 1 Md€) mis à NULL : le marché est compté, pas le montant
      CASE WHEN montant>=9.9e8 OR regexp_matches(replace(cast(round(montant) AS VARCHAR),'.0',''),'^9{{6,}}$') OR montant<0 THEN NULL ELSE montant END AS montant_declare,
      try_cast(date_notif AS DATE) AS dn, cpv, accord_cadre, objet,
      unnest(titulaires) AS t FROM d WHERE acheteur IS NOT NULL),
v AS (SELECT DISTINCT ON (ach, coalesce(objet,''), dn, montant_declare, left(t,9))
        id, ach, left(t,9) AS tit, montant_declare, dn, cpv, accord_cadre, objet FROM u ORDER BY id),
g AS (SELECT *, count(*) OVER w AS nb_tit_groupe, min(id) OVER w AS marche_id FROM v
      WINDOW w AS (PARTITION BY ach, coalesce(objet,''), dn, montant_declare))
SELECT marche_id, id AS id_decp, ach, tit, montant_declare, nb_tit_groupe, montant_declare/nb_tit_groupe AS montant_part,
       dn, dn > current_date AS date_future, cpv, accord_cadre, objet FROM g""")
con.execute("""CREATE TABLE ach AS
SELECT s.siren, s.nom, CASE WHEN s.siren IN (SELECT siren FROM centrales) THEN 'centrale' WHEN s.siren IN (SELECT siren FROM hop) THEN 'hopital'
       WHEN s.cj=7364 THEN 'hopital_sirene' END AS type
FROM sir s WHERE s.siren IN (SELECT siren FROM hop) OR s.siren IN (SELECT siren FROM centrales) OR s.cj=7364""")

# 4. Labos payeurs de Transparence Santé (vue nette) : SIREN déclaré + clé de nom (premier mot significatif)
con.execute("""CREATE TABLE labos AS
SELECT raison_sociale, min(numero_siren) FILTER (WHERE regexp_matches(coalesce(numero_siren,''),'^[0-9]{9}$')) siren,
       sum(montant) total_ts FROM ts_net WHERE raison_sociale IS NOT NULL GROUP BY raison_sociale""")
con.execute(f"CREATE TABLE labos_k AS SELECT *, {cle_sql('raison_sociale')} AS cle FROM labos")
con.execute("DELETE FROM labos_k WHERE cle IN (%s)" % ",".join(f"'{w}'" for w in INTERDITS))
# libellé du groupe : la raison sociale la plus lourde parmi celles qui déclarent un SIREN français (sinon ROCHE CANADA l'emporte sur ROCHE SAS)
con.execute("""CREATE TABLE labo_groupes AS SELECT cle,
   coalesce(arg_max(raison_sociale, (total_ts, raison_sociale)) FILTER (WHERE siren IS NOT NULL), arg_max(raison_sociale, (total_ts, raison_sociale))) AS labo, sum(total_ts) AS total_ts
   FROM labos_k WHERE cle IS NOT NULL GROUP BY cle""")
# un SIREN peut porter plusieurs raisons sociales de clés différentes : on garde UNE clé, celle qui pèse le plus en euros
n_multi = con.execute("""SELECT count(*) FROM (SELECT siren FROM labos_k WHERE siren IS NOT NULL AND cle IS NOT NULL
   GROUP BY siren HAVING count(DISTINCT cle)>1)""").fetchone()[0]
con.execute("""CREATE TABLE labo_siren AS SELECT siren, arg_max(cle, (total_ts, cle)) AS cle FROM
   (SELECT siren, cle, sum(total_ts) total_ts FROM labos_k WHERE siren IS NOT NULL AND cle IS NOT NULL GROUP BY ALL) GROUP BY siren""")
n_multi_apres = con.execute("SELECT count(*) FROM (SELECT siren FROM labo_siren GROUP BY siren HAVING count(*)>1)").fetchone()[0]

# 5. Titulaires DECP appariés : par SIREN (sûr) sinon par premier mot significatif de la dénomination SIRENE (plus faible)
con.execute(f"""CREATE TABLE tit_nom AS
SELECT DISTINCT m.tit, s.nom AS nom_sirene, {cle_sql('s.nom')} AS cle, sig(s.nom) AS st
FROM (SELECT DISTINCT tit FROM marches WHERE ach IN (SELECT siren FROM ach)) m JOIN sir s ON s.siren=m.tit""")
# appariement par nom : même premier mot significatif ET (l'un des deux noms n'a qu'un mot significatif, ou le 2e mot est le même)
# (évite FISHER SCIENTIFIC = FISHER & PAYKEL, THERMO ELECTRON = THERMO FISHER)
con.execute("""CREATE TABLE tit_cle AS
SELECT t.tit, coalesce(ls.cle, k.cle) AS cle, CASE WHEN ls.cle IS NOT NULL THEN 'siren' ELSE 'nom' END AS methode, min(t.nom_sirene) AS nom_sirene
FROM tit_nom t LEFT JOIN labo_siren ls ON ls.siren=t.tit
LEFT JOIN (SELECT DISTINCT t2.tit, t2.cle FROM tit_nom t2 JOIN (SELECT cle, sig(raison_sociale) sv FROM labos_k) v ON v.cle=t2.cle
   WHERE len(t2.st)<=1 OR len(v.sv)<=1 OR t2.st[2]=v.sv[2]) k ON k.tit=t.tit
WHERE ls.cle IS NOT NULL OR k.cle IS NOT NULL
GROUP BY ALL""")
n_tit_multi = con.execute("SELECT count(*) FROM (SELECT tit FROM tit_cle GROUP BY tit HAVING count(*)>1)").fetchone()[0]

# marchés retenus : dates futures écartées (signalées dans le log), dates absentes ou avant 2015 écartées
con.execute("""CREATE TABLE mh_tout AS
SELECT m.*, a.type AS type_acheteur, a.nom AS acheteur_nom, c.cle, c.methode, c.nom_sirene
FROM marches m JOIN ach a ON a.siren=m.ach JOIN tit_cle c ON c.tit=m.tit""")
con.execute("CREATE TABLE mh AS SELECT * FROM mh_tout WHERE NOT date_future AND dn >= DATE '2015-01-01'")

# 6. Fenêtre temporelle : la plus petite année A telle que les marchés hôpitaux x labos notifiés de A à aujourd'hui font >= 95 % du total
an = con.execute("""WITH y AS (SELECT year(dn) a, count(DISTINCT marche_id) n FROM mh WHERE type_acheteur IN ('hopital','hopital_sirene') GROUP BY 1)
  SELECT max(a) FILTER (WHERE cum >= 0.95), max(a) FROM (SELECT a, sum(n) OVER (ORDER BY a DESC) / sum(n) OVER () AS cum FROM y)""").fetchone()
A0, A1 = an
print(f"Fenêtre des versements TS : {A0} à {A1} (années où sont notifiés 95 % des marchés hôpitaux x labos retenus)")

# 7. Sortie 1 : par acheteur x titulaire
SOMMES = f"""count(DISTINCT a.marche_id) AS nb_marches,
   count(DISTINCT a.marche_id) FILTER (WHERE a.montant_declare >= {GROS}) AS nb_marches_100meur_et_plus,
   round(sum(a.montant_part) FILTER (WHERE coalesce(a.montant_declare,0) < {GROS})) AS montant_hors_marches_100meur_eur,
   round(sum(a.montant_part)) AS somme_plafonds_declares_eur,
   round(max(a.montant_declare)) AS plus_gros_plafond_declare_eur"""
con.execute(f"""COPY (SELECT a.type_acheteur AS type_acheteur, a.ach AS acheteur_siren, a.acheteur_nom AS acheteur,
   g.labo AS labo_ts, a.tit AS titulaire_siren, min(a.nom_sirene) AS titulaire, min(a.methode) AS appariement,
   {SOMMES},
   count(DISTINCT a.marche_id) FILTER (WHERE a.accord_cadre) AS dont_accords_cadres,
   round(100.0*count(*) FILTER (WHERE a.cpv LIKE '33%')/count(*),0) AS pct_marches_cpv33_medical,
   min(a.dn) AS premiere_notification, max(a.dn) AS derniere_notification
 FROM mh a JOIN labo_groupes g USING (cle) GROUP BY ALL ORDER BY type_acheteur, montant_hors_marches_100meur_eur DESC NULLS LAST)
 TO '{sql_chemin(OUT / 'marches_hopitaux_labos.csv')}' (HEADER, DELIMITER ',')""")

# 8. Sortie 2 : par paire hôpital x labo : € reçus (TS net, lignes rattachées en fiable, fenêtre A0-A1) et marchés
# les lignes TS portent leur struct_id dans data/travail.duckdb (lecture seule) ; on retire les conventions exécutées
# par des versements liés (même règle que ts_net) en retrouvant identifiant_unique via l'id de la ligne dans `ts`.
con.execute(f"""CREATE TABLE lig AS
SELECT l.struct_id, l.raison_sociale, l.montant, l.date FROM trav.lignes l
WHERE l.struct_id IS NOT NULL AND year(l.date) BETWEEN {A0} AND {A1}
  AND l.id NOT IN (SELECT t.id FROM ts t SEMI JOIN read_parquet('{sql_chemin(RACINE / 'data/ext/conventions_liees.parquet')}') c
                   ON t.lien_interet='convention' AND c.entreprise_id=t.entreprise_id AND c.identifiant_unique=t.identifiant_unique)""")
con.execute(f"""CREATE TABLE ts_paire AS
SELECT h.siren, {cle_sql('l.raison_sociale')} AS cle, sum(l.montant) AS recu_ts, count(*) AS nb_versements,
       min(l.date) AS d0, max(l.date) AS d1
FROM lig l JOIN hop h USING (struct_id) GROUP BY ALL""")
con.execute(f"""CREATE TABLE mp AS SELECT ach AS siren, cle, count(DISTINCT marche_id) nb_marches,
   count(DISTINCT marche_id) FILTER (WHERE montant_declare >= {GROS}) nb_gros,
   sum(montant_part) FILTER (WHERE coalesce(montant_declare,0) < {GROS}) montant_hors_gros,
   sum(montant_part) somme_plafonds, max(montant_declare) plus_gros,
   min(dn) AS m0, max(dn) AS m1, count(*) FILTER (WHERE methode='nom')>0 AS apparie_par_nom
 FROM mh WHERE type_acheteur IN ('hopital','hopital_sirene') GROUP BY ach, cle""")
con.execute("CREATE TABLE paires AS SELECT * FROM ts_paire t JOIN mp m USING (siren, cle) WHERE t.recu_ts > 0")
con.execute(f"""COPY (SELECT p.siren AS hopital_siren, coalesce(h.nom_officiel, s.nom) AS hopital,
   p.cle AS cle_labo, g.labo AS labo,
   round(p.recu_ts) AS recu_du_labo_ts_net_eur_{A0}_{A1}, p.nb_versements AS nb_versements_ts,
   p.d0 AS ts_premier_versement, p.d1 AS ts_dernier_versement,
   p.nb_marches, p.nb_gros AS nb_marches_100meur_et_plus,
   round(p.montant_hors_gros) AS marches_hors_100meur_eur, round(p.somme_plafonds) AS somme_plafonds_declares_eur,
   round(p.plus_gros) AS plus_gros_plafond_declare_eur,
   p.m0 AS marches_premiere_notification, p.m1 AS marches_derniere_notification,
   p.apparie_par_nom AS apparie_par_nom_seulement_possible
 FROM paires p
 LEFT JOIN (SELECT siren, min(nom_officiel) nom_officiel FROM hop GROUP BY siren) h ON h.siren=p.siren
 LEFT JOIN sir s ON s.siren=p.siren LEFT JOIN labo_groupes g ON g.cle=p.cle
 ORDER BY p.recu_ts DESC)
 TO '{sql_chemin(OUT / 'hopitaux_finances_et_acheteurs.csv')}' (HEADER, DELIMITER ',')""")

p = lambda q: print(con.execute(q).df().to_string())
print(f"== SIREN de labo portant plusieurs clés : {n_multi} avant, {n_multi_apres} après (une clé par SIREN) ; titulaires DECP à plusieurs clés : {n_tit_multi}")
print("== période / volume DECP"); p("SELECT count(*) nb_lignes, count(DISTINCT marche_id) marches, count(DISTINCT id_decp) enregistrements_decp, min(dn), max(dn) FROM marches")
print("== dates futures (écartées)"); p("SELECT count(DISTINCT marche_id) marches_hop_labos_date_future, max(dn) FROM mh_tout WHERE date_future")
print("== dédoublonnage des plafonds répétés"); p("SELECT count(*) FILTER (WHERE nb_tit_groupe>1) lignes_partagees, round(sum(montant_declare)/1e6,1) meur_avant, round(sum(montant_part)/1e6,1) meur_apres FROM mh WHERE type_acheteur IN ('hopital','hopital_sirene')")
print("== marchés hôpitaux x labos par type d'acheteur"); p(f"""SELECT type_acheteur, count(DISTINCT ach) acheteurs, count(DISTINCT marche_id) marches,
   count(DISTINCT marche_id) FILTER (WHERE montant_declare >= {GROS}) marches_100meur_et_plus,
   round(sum(montant_part) FILTER (WHERE coalesce(montant_declare,0) < {GROS})/1e6,1) meur_hors_100meur, round(sum(montant_part)/1e6,1) meur_somme_plafonds FROM mh GROUP BY 1""")
print("== par méthode d'appariement"); p(f"SELECT type_acheteur, methode, count(DISTINCT marche_id) marches, round(sum(montant_part) FILTER (WHERE coalesce(montant_declare,0) < {GROS})/1e6,1) meur_hors_100meur FROM mh GROUP BY 1,2")
print(f"== paires hôpital x labo avec les deux flux (reçu TS net > 0 sur {A0}-{A1}, au moins un marché)")
p("""SELECT count(*) paires, count(DISTINCT siren) hopitaux, count(DISTINCT cle) labos, round(sum(recu_ts)/1e6,2) ts_meur,
   sum(nb_marches) marches, sum(nb_gros) dont_100meur_et_plus, round(sum(montant_hors_gros)/1e6,1) marches_hors_100meur_meur,
   round(sum(somme_plafonds)/1e6,1) somme_plafonds_meur, count(*) FILTER (WHERE apparie_par_nom) paires_appariees_par_nom FROM paires""")
print("== 10 premières paires (par euros reçus)")
p("""SELECT p.siren, coalesce(min(h.nom_officiel), min(s.nom))[:40] hopital, p.cle, round(p.recu_ts) recu_ts, p.nb_marches, p.nb_gros,
   round(p.montant_hors_gros) hors_100meur, round(p.somme_plafonds) plafonds FROM paires p LEFT JOIN hop h ON h.siren=p.siren LEFT JOIN sir s ON s.siren=p.siren
   GROUP BY p.siren, p.cle, p.recu_ts, p.nb_marches, p.nb_gros, p.montant_hors_gros, p.somme_plafonds ORDER BY p.recu_ts DESC LIMIT 10""")
